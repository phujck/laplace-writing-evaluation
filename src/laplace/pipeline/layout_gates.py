"""The figure-layout review gates — three mechanical surfaces the pipeline was
missing (his hold-out review, 2026-07-10: *create independent surfaces*).

The existing figure apparatus (:mod:`figure_audit`, :mod:`caption_audit`,
:mod:`table_audit`) reads the manuscript SOURCE — labels, refs, captions, column
class — and never looks at the compiled artefact as a physical page. Three real
defects on the r2 SSG whitepaper slipped through every source-level gate because
they only exist in the RENDERED object:

  * **G1 — the final-size visual gate** (release blocker). A figure scaled to fit
    the column drags its embedded text down with it: matplotlib panels set at a
    nominal 8pt land on the page at ~1.2pt, far below the 6pt legibility floor.
    Source parsing cannot see this — only measuring the *rendered glyph height* in
    the compiled PDF can. G1 measures every character's physical loose-box height
    (via pypdfium2's ``FPDFText_GetLooseCharBox`` in the isolated ``uv`` subprocess
    the visual gate already proved out), counts sub-6pt characters per page, flags
    Type-3 fonts (the matplotlib default — non-embeddable, illegible when scaled),
    and flags glyphs clipped past the page mediabox. HARD at release.

  * **G2 — the semantic float gate**. A float's *reading contract* is that it lands
    where the prose invokes it. ``figure_audit`` measures the mention-to-float
    distance in SECTIONS; G2 measures it in PAGES (from the ``.aux`` label pages +
    ``synctex`` ref-line resolution), so it catches a figure that floats a whole
    page-backlog past its first mention, an orphan the body never ``\\ref``s, and —
    the severe case — a body figure shipped out at or past the conclusion / appendix
    boundary, where the reader meets it with the argument already closed.

  * **G3 — the figure contract registry**. One structured record per figure
    ``{hero_claim, evidence_type, panel_labels, caption_coverage, first_ref_page,
    landing_page, data_key, limitation}`` extracted from the figure environment, its
    caption, and the rendered asset. Its enforcement is AGREEMENT: the panels the
    ASSET actually draws must match the panels the CAPTION covers and the panels the
    BODY prose describes. A five-panel asset whose caption only narrates three panels
    is a silent coverage hole no source gate sees, because the source is internally
    consistent — the disagreement is between the source and the rendered asset.

Each gate is a ``check_*`` function returning the pipeline's audit shape
``{"pass": bool, "clean": bool, "findings": [...], "counts": {...}, ...}`` (``pass``
matches the Phase-C audit idiom; ``clean`` is the same value under the release
idiom). Findings carry ``{where, issue, fix, kind, route}``. The gates REUSE, never
re-derive: the ``uv``/pypdfium2 subprocess pattern and the ``synctex`` label→page
resolution from :mod:`visual_gate`, the flattened-manuscript text from
:mod:`laplace.pipeline.graph`, and the ``\\ref``/``\\label`` index from
:mod:`apparatus_common`. They are READ-ONLY w.r.t. the manuscript: they read the
PDF, ``.aux`` and ``.tex`` and never write a source byte.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional, Union

from laplace.pipeline.graph import _gather_manuscript_text
from laplace.pipeline import visual_gate as _vg
from laplace.pipeline.apparatus_common import (
    section_of, section_spans, summarise,
)

# ---------------------------------------------------------------------------
# finding shape + routing (local — these kinds are this module's vocabulary; the
# Phase-F schema wiring folds them in the same way it folds the visual_gate kinds,
# but this module stays self-contained and routes its own kinds so a caller never
# re-derives the owning stage).
# ---------------------------------------------------------------------------

#: kind -> owning stage. Size/render defects land on ``document`` (the render leg,
#: same as the visual gate); float placement is ``structural`` (the same owner as
#: ``figure-misplaced`` / ``figure-unreferenced`` in ``apparatus_common``); panel /
#: caption coverage is ``figures`` (the caption sub-layer's owner).
LAYOUT_KIND_STAGE: dict[str, str] = {
    # G1 — final-size visual
    "layout-text-undersize": "document",   # rendered glyphs below the 6pt floor
    "layout-type3-font":     "document",   # non-embeddable Type-3 fonts (matplotlib)
    "layout-clipped-glyph":  "document",   # a glyph clipped past the page mediabox
    # G2 — semantic float
    "float-backlog":         "structural", # lands > N pages past its first mention
    "float-orphan":          "structural", # never \ref'd in the body
    "float-past-boundary":   "structural", # body figure lands at/after conclusion/appendix
    # G3 — figure contract registry
    "figure-panel-uncovered":    "figures",   # asset draws a panel the caption never covers
    "figure-panel-body-mismatch": "figures",  # caption panels != body-described panels
    "figure-contract-orphan":    "structural",# registry note: figure has no body ref
}


def _finding(where: str, issue: str, fix: Optional[str], kind: str,
             quote: Optional[str] = None, **extra: Any) -> dict[str, Any]:
    """One finding in the pipeline's standard shape, routed from
    :data:`LAYOUT_KIND_STAGE`. ``extra`` carries the load-bearing measurement
    (counts, pages) so a downstream re-author reads the number, not the prose."""
    rec: dict[str, Any] = {"where": where}
    if quote:
        rec["quote"] = quote[:240]
    rec["issue"] = issue
    rec["fix"] = fix
    rec["kind"] = kind
    rec["route"] = LAYOUT_KIND_STAGE.get(kind, "document")
    rec.update(extra)
    return rec


def _result(findings: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    """Assemble the audit-shape result. ``pass`` follows the Phase-C idiom;
    ``clean`` is the same value under the release idiom, so a caller in either
    world reads the gate correctly."""
    ok = not findings
    out: dict[str, Any] = {"pass": ok, "clean": ok, "findings": findings,
                           "counts": summarise(findings)}
    out.update(extra)
    return out


# ---------------------------------------------------------------------------
# .aux resolution — figure/section label -> page (the reused \label/page map)
# ---------------------------------------------------------------------------

def _read_braced(s: str, i: int) -> tuple[str, int]:
    """Read a balanced ``{...}`` group starting at ``s[i] == '{'``; return
    (inner_content, index_after_closing_brace). A LaTeX ``.aux`` caption field
    nests braces several levels deep, so a fixed regex miscounts it — walk the
    braces."""
    assert s[i] == "{"
    depth = 0
    j = i
    while j < len(s):
        c = s[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
        j += 1
    return s[i + 1:], len(s)


_NEWLABEL_RE = re.compile(r"\\newlabel\s*\{")


def _parse_aux_labels(aux_path: Union[str, Path]
                      ) -> tuple[dict[str, dict[str, Any]], bool]:
    """As :func:`parse_aux_labels`, but also returns ``readable``: False when the
    ``.aux`` exists yet cannot be read (OSError). The gates thread that flag into
    their denominator honesty — an unreadable aux silently empties the figure set,
    which would otherwise read as a clean pass over zero figures."""
    aux_path = Path(aux_path)
    try:
        text = aux_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}, False
    out: dict[str, dict[str, Any]] = {}
    for m in _NEWLABEL_RE.finditer(text):
        i = m.end() - 1                       # at the '{' of the key
        key, i = _read_braced(text, i)
        # skip to the second top-level arg (the {{num}{page}...} block)
        while i < len(text) and text[i] not in "{":
            if text[i] == "\n":
                break
            i += 1
        if i >= len(text) or text[i] != "{":
            continue
        body, _ = _read_braced(text, i)
        # body == "{num}{page}{caption}{anchor}{}" — read its first two sub-groups
        num = page = None
        k = 0
        subs: list[str] = []
        while k < len(body) and len(subs) < 2:
            if body[k] == "{":
                val, k = _read_braced(body, k)
                subs.append(val)
            else:
                k += 1
        if subs:
            num = subs[0]
        if len(subs) > 1:
            try:
                page = int(subs[1].strip())
            except (ValueError, AttributeError):
                page = None
        out[key] = {"number": num, "page": page}
    return out, True


def parse_aux_labels(aux_path: Union[str, Path]) -> dict[str, dict[str, Any]]:
    """Every ``\\newlabel{key}{{number}{page}{...}...}`` in a compiled ``.aux`` ->
    ``{key: {"number": <str>, "page": <int|None>}}``. The page is the second inner
    group (where the counter stood at ``\\label`` — for a float that is its shipout
    page, the page the reader sees it on). Brace-balanced so a caption field carrying
    ``$...$`` and nested groups never derails the parse."""
    return _parse_aux_labels(aux_path)[0]


def _figure_labels(aux: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The ``fig:*`` labels (label -> {number, page}) from a parsed aux map."""
    return {k: v for k, v in aux.items() if k.startswith("fig:")}


def _boundary_pages(aux: dict[str, dict[str, Any]],
                    tex_root: Path) -> tuple[Optional[int], Optional[int]]:
    """(conclusion_boundary_page, appendix_boundary_page).

    The conclusion boundary is the FIRST page of the concluding section — the last
    non-appendix ``sec:*`` in reading order (a body figure landing at/after it meets
    the reader with the argument closed). The appendix boundary is the first
    ``app:*`` page (or the earliest label after ``\\appendix``). Either is ``None``
    when the manuscript declares no such section."""
    # appendix boundary: the smallest page among app:* labels.
    app_pages = [v["page"] for k, v in aux.items()
                 if k.startswith("app:") and isinstance(v.get("page"), int)]
    appendix = min(app_pages) if app_pages else None

    # conclusion boundary: the last sec:* whose page is BEFORE the appendix (or the
    # last sec:* outright when there is no appendix). Ordered by page.
    sec_pages = sorted(
        (v["page"], k) for k, v in aux.items()
        if k.startswith("sec:") and isinstance(v.get("page"), int))
    conclusion = None
    for page, _k in sec_pages:
        if appendix is not None and page >= appendix:
            continue
        conclusion = page
    return conclusion, appendix


# ---------------------------------------------------------------------------
# .tex resolution — first body \ref of a label (file, line, source position)
# ---------------------------------------------------------------------------

_XREF_TMPL = r"\\(?:ref|eqref|autoref|cref|Cref|pageref)\{%s\}"


def _first_ref_location(tex_root: Path, label: str) -> Optional[tuple[str, int]]:
    """The (file relative to root, 1-based line) of the FIRST ``\\ref`` (or
    autoref/cref/…) of ``label`` in reading order (files in sorted / \\input order,
    then by line). ``None`` when the label is never referenced — an orphan."""
    pat = re.compile(_XREF_TMPL % re.escape(label))
    for f, rel in _vg._tex_files(tex_root):
        try:
            for i, ln in enumerate(f.read_text(encoding="utf-8", errors="replace")
                                   .splitlines(), start=1):
                if pat.search(ln):
                    return rel, i
        except OSError:
            continue
    return None


def _ref_page_via_synctex(pdf_path: Path, tex_root: Path, label: str,
                          synctex_bin: str = "synctex") -> Optional[int]:
    """The page a label's first ``\\ref`` lands on, resolved by mapping its source
    (file, line) through ``synctex`` — the exact page the mention prints on. Returns
    ``None`` when there is no ref or synctex cannot place it (a stale/missing
    ``.synctex.gz``); the caller then falls back to the section-page estimate."""
    loc = _first_ref_location(tex_root, label)
    if not loc:
        return None
    reg = _vg.synctex_region(
        pdf_path, loc[0], loc[1], label=label, synctex_bin=synctex_bin)
    return reg.page if reg else None


# ---------------------------------------------------------------------------
# the isolated pypdfium2 / pikepdf subprocesses (reuse visual_gate's pattern)
# ---------------------------------------------------------------------------

_MEASURE_SCRIPT = r'''
import sys, json, re, ctypes
import pypdfium2 as pdfium
import pypdfium2.raw as C
pdf_path, min_pt = sys.argv[1], float(sys.argv[2])
COMMON = ("that", "this", "with", "from", "which", "have", "been", "these",
          "filtered", "effective", "coefficient", "floor", "spectral", "surface")
WORD = re.compile(r"[a-z]{4,}")
def _ctrl(t):
    return sum(1 for c in t if ord(c) < 0x20 and c not in "\t\n\r\f\x0b") + t.count("\ufffd")
doc = pdfium.PdfDocument(pdf_path)
N = len(doc)
pages = []
doc_words = 0
common_seen = set()
for pno in range(1, N + 1):
    page = doc[pno - 1]
    tp = page.get_textpage()
    n = tp.count_chars()
    mb = page.get_mediabox()          # (x0, y0, x1, y1) in pt
    sub = 0; mn = None; beyond = 0
    for i in range(n):
        rect = C.FS_RECTF()
        if not C.FPDFText_GetLooseCharBox(tp.raw, i, ctypes.byref(rect)):
            continue
        # Loose character boxes are axis-aligned. A rotated y-axis label puts
        # the glyph's physical height mostly along x, so using only top-bottom
        # falsely classifies an ordinary 10 pt ``l`` as a 2--3 pt glyph. The
        # major box extent is the rotation-invariant conservative proxy.
        h = max(abs(rect.top - rect.bottom), abs(rect.right - rect.left))
        if h <= 0:
            continue
        if h < min_pt:
            sub += 1
            mn = h if mn is None else min(mn, h)
        if (rect.left < mb[0] - 2 or rect.right > mb[2] + 2 or
                rect.bottom < mb[1] - 2 or rect.top > mb[3] + 2):
            beyond += 1
    # text-layer extraction sanity (machine-readability): the ratio of ascii-letter
    # ink and of control-char garbage in the page's extracted text.
    txt = tp.get_text_bounded()
    nonspace = sum(1 for c in txt if not c.isspace())
    letters = sum(1 for c in txt if c.isascii() and c.isalpha())
    words = WORD.findall(txt.lower())
    doc_words += len(words)
    low = txt.lower()
    for w in COMMON:
        if w in low:
            common_seen.add(w)
    pages.append({"page": pno, "nchars": n, "sub_count": sub,
                  "min_height": (round(mn, 3) if mn is not None else None),
                  "beyond_mediabox": beyond,
                  "text_nonspace": nonspace, "text_words": len(words),
                  "letter_ratio": round(letters / max(1, nonspace), 4),
                  "control_ratio": round(_ctrl(txt) / max(1, len(txt)), 5)})
    tp.close(); page.close()
# font scan (best-effort — an honest gap, not a false pass, if pikepdf is absent):
#   * Type-3 fonts (matplotlib default; non-embeddable, illegible when scaled),
#   * Type-3 fonts lacking a ToUnicode map (extraction garbles their glyphs),
#   * standard TEXT fonts (Type1/TrueType/Type0) lacking ToUnicode (unindexable).
type3 = []; type3_no_tu = 0; text_no_tu = []; t3err = None; font_skipped = 0
try:
    import pikepdf
    _TEXT = {"/Type1", "/TrueType", "/Type0", "/MMType1"}
    with pikepdf.open(pdf_path) as pk:
        for obj in pk.objects:
            try:
                if not (isinstance(obj, pikepdf.Dictionary) and "/Type" in obj
                        and str(obj.Type) == "/Font"):
                    continue
                st = str(obj.get("/Subtype", ""))
                base = str(obj.get("/BaseFont", obj.get("/Name", st or "font")))
                has_tu = "/ToUnicode" in obj
                if st == "/Type3":
                    type3.append(base)
                    if not has_tu:
                        type3_no_tu += 1
                elif st in _TEXT and not has_tu:
                    text_no_tu.append(base)
            except Exception:
                font_skipped += 1
                continue
except Exception as e:
    t3err = repr(e)
print(json.dumps({"n_pages": N, "pages": pages,
                  "type3_fonts": sorted(set(type3)),
                  "type3_no_tounicode": type3_no_tu,
                  "text_fonts_no_tounicode": sorted(set(text_no_tu)),
                  "doc_words": doc_words,
                  "common_words_present": sorted(common_seen),
                  "type3_error": t3err, "font_skipped": font_skipped}))
'''

_PANELS_SCRIPT = r'''
import sys, json, re
import pypdfium2 as pdfium
# a panel label is an isolated "(x)" token (subplot title), not an inline "(a)".
PANEL = re.compile(r'(?:^|[\s])\(([a-h])\)(?:[\s]|$)', re.M)
out = {}
for path in sys.argv[1:]:
    try:
        doc = pdfium.PdfDocument(path)
        txt = ""
        for i in range(len(doc)):
            tp = doc[i].get_textpage()
            txt += tp.get_text_bounded() + "\n"
            tp.close()
        out[path] = sorted(set(PANEL.findall(txt)))
    except Exception as e:
        out[path] = {"error": repr(e)}
print(json.dumps(out))
'''

_RENDER_TIMEOUT = 600


def _run_uv(script: str, args: list[str], *, withs: list[str],
            uv_bin: str = _vg.DEFAULT_UV, timeout: int = _RENDER_TIMEOUT) -> Any:
    """Run ``script`` in an isolated ``uv run --with ...`` subprocess (the same
    isolation the visual gate uses so the main venv is never perturbed) and parse
    its JSON manifest from the last stdout line. Raises ``RuntimeError`` on any
    failure — a broken measurement is a loud signal, never a silent empty pass."""
    import shutil
    if not shutil.which(uv_bin) and not Path(uv_bin).is_file():
        raise RuntimeError(f"uv not found at {uv_bin!r}; set LAPLACE_UV_BIN")
    with_args: list[str] = []
    for w in withs:
        with_args += ["--with", w]
    with tempfile.NamedTemporaryFile(
            "w", suffix=".py", delete=False, encoding="utf-8") as tf:
        tf.write(script)
        spath = tf.name
    try:
        proc = subprocess.run(
            [uv_bin, "run", "--no-project", *with_args, "python", spath, *args],
            capture_output=True, encoding="utf-8", errors="replace", timeout=timeout)
    finally:
        try:
            os.unlink(spath)
        except OSError:
            pass
    if proc.returncode != 0:
        raise RuntimeError(f"uv subprocess failed (rc={proc.returncode}): "
                           f"{(proc.stderr or proc.stdout)[-800:]}")
    lines = (proc.stdout or "").strip().splitlines()
    if not lines:
        raise RuntimeError(f"uv subprocess produced no manifest: {proc.stderr[-800:]}")
    return json.loads(lines[-1])


def measure_pdf_text(pdf_path: Union[str, Path], *, min_pt: float = 6.0,
                     uv_bin: str = _vg.DEFAULT_UV) -> dict[str, Any]:
    """Measure a compiled PDF at its ACTUAL physical dimensions: per page, the
    number of characters whose rendered loose-box height is below ``min_pt`` and the
    smallest such height, the count of glyphs clipped past the page mediabox, plus
    the document's Type-3 font list. Runs in the isolated pypdfium2/pikepdf
    subprocess. The physical glyph height (not the nominal font size) is the
    load-bearing measure: a matplotlib panel scaled to the column reports a nominal
    8pt but lands on the page at ~1.2pt, and only the loose box sees that."""
    return _run_uv(_MEASURE_SCRIPT, [str(Path(pdf_path).resolve()), str(min_pt)],
                   withs=["pypdfium2", "pikepdf"], uv_bin=uv_bin)


def extract_asset_panels(asset_paths: list[Path],
                         uv_bin: str = _vg.DEFAULT_UV) -> dict[str, list[str]]:
    """Panel labels an asset PDF actually draws — the isolated ``(a)``/``(b)``/…
    subplot tokens in its rendered text, per asset. This is the ASSET side of the
    panel-agreement contract (the caption/body sides come from the source)."""
    paths = [str(p.resolve()) for p in asset_paths if p.is_file()]
    if not paths:
        return {}
    raw = _run_uv(_PANELS_SCRIPT, paths, withs=["pypdfium2"], uv_bin=uv_bin)
    out: dict[str, list[str]] = {}
    for p, v in raw.items():
        out[Path(p).name] = v if isinstance(v, list) else []
    return out


# ===========================================================================
# G1 — the final-size visual gate (release blocker)
# ===========================================================================

#: below this rendered glyph height a character is grossly sub-6pt — illegible,
#: not a conventional deep math subscript. CALIBRATED, not guessed: on the r2 SSG
#: whitepaper every body page bottoms out at >= 3.96pt (a 5pt math script's loose
#: box), while every figure-bearing page reaches <= 3.15pt (a scaled-down embedded
#: graphic). 3.5pt sits in the empty gap between the two populations, so the gate
#: fires on mis-scaled figure text and never on conventional body scripting.
_ILLEGIBLE_FLOOR_PT = 3.5

#: a page carrying at least this many sub-6pt characters is a defect regardless of
#: how small — a backstop for a page dense with 4-5pt text (min above the floor).
#: Observed body-page maximum on r2 is 44 sub-6pt characters, so 150 never fires on
#: conventional scripting.
_PAGE_CLUSTER = 150

#: text-layer machine-readability thresholds. CALIBRATED, not guessed: the r2 clean
#: text layer (Type-1 CM with ToUnicode) extracts at letter_ratio >= 0.73 and
#: control_ratio <= 0.011 on every text-bearing page, with common English words
#: intact; a Type-3 text layer with no ToUnicode map extracts as control-char
#: garbage — letter_ratio 0.0, control_ratio ~1.0, zero words. The floors sit in the
#: wide gap between the two.
_TEXT_MIN_CHARS = 200          # below this a page is figure-only/blank — not judged
_LETTER_RATIO_FLOOR = 0.5      # below this the extracted text is garbage
_CONTROL_RATIO_CEIL = 0.10     # above this the page extracts control-char garbage
_MIN_COMMON_WORDS = 3          # a text-bearing doc must surface this many common words


def _text_layer_findings(manifest: dict[str, Any]) -> tuple[list[dict[str, Any]],
                                                             dict[str, Any]]:
    """The text-layer machine-readability findings (submission systems, indexing,
    accessibility) + a summary. Fires ``layout-text-unextractable`` on a page whose
    extracted text is garbled (low letter ratio / control-char garbage / no words),
    or on a text-bearing document that surfaces too few common English words; and
    ``layout-text-font-unmapped`` when garbling coincides with fonts that carry no
    ToUnicode map (the mechanism). A Type-3 figure font that leaves body-text
    extraction intact (the r2 case) is NOT a text-layer defect and is not flagged
    here — the extraction symptom, not the mere presence of Type-3, is the gate."""
    findings: list[dict[str, Any]] = []
    garbled: list[dict[str, Any]] = []
    for pg in manifest["pages"]:
        ns = pg.get("text_nonspace", 0)
        if ns < _TEXT_MIN_CHARS:
            continue                                  # figure-only / blank page
        lr = pg.get("letter_ratio", 1.0)
        cr = pg.get("control_ratio", 0.0)
        words = pg.get("text_words", 0)
        if lr < _LETTER_RATIO_FLOOR or cr > _CONTROL_RATIO_CEIL or words == 0:
            garbled.append(pg)
            findings.append(_finding(
                f"p{pg['page']}",
                f"text layer does not extract as readable words "
                f"(letter-ratio {lr:g}, control-char ratio {cr:g}, "
                f"{words} 4+-letter words in {ns} glyphs)",
                "recompile with a Unicode-mapped text font (lmodern / Type-1 CM "
                "with a ToUnicode map) so the text layer is machine-readable",
                "layout-text-unextractable",
                page=pg["page"], letter_ratio=lr, control_ratio=cr,
                text_words=words))

    doc_words = manifest.get("doc_words", 0)
    common = manifest.get("common_words_present", []) or []
    if doc_words >= 100 and len(common) < _MIN_COMMON_WORDS:
        findings.append(_finding(
            "document text layer",
            f"a text-bearing document ({doc_words} extractable words) surfaces only "
            f"{len(common)} common English words {common} — the text layer is not "
            "machine-readable",
            "recompile with a Unicode-mapped text font so extraction/indexing works",
            "layout-text-unextractable", common_words=common, doc_words=doc_words))

    # the font mechanism, surfaced ONLY when extraction is actually garbled (so the
    # benign r2 figure Type-3 fonts, which leave body text extractable, never fire).
    t3_no_tu = manifest.get("type3_no_tounicode", 0)
    text_no_tu = manifest.get("text_fonts_no_tounicode", []) or []
    if garbled and (t3_no_tu or text_no_tu):
        findings.append(_finding(
            "document fonts",
            f"{t3_no_tu} Type-3 and {len(text_no_tu)} standard text fonts carry no "
            "ToUnicode map — the cause of the unextractable text layer",
            "embed a ToUnicode CMap for every text font (recompile with lmodern)",
            "layout-text-font-unmapped",
            type3_no_tounicode=t3_no_tu, text_fonts_no_tounicode=text_no_tu[:8]))

    summary = {
        "clean": not findings,
        "garbled_pages": [g["page"] for g in garbled],
        "type3_no_tounicode": t3_no_tu,
        "text_fonts_no_tounicode": len(text_no_tu),
        "doc_words": doc_words,
        "common_words_present": common,
    }
    return findings, summary


def check_text_layer(pdf_path: Union[str, Path], *,
                     uv_bin: str = _vg.DEFAULT_UV) -> dict[str, Any]:
    """The text-layer machine-readability gate on its own — extract the text layer
    and REJECT it if it does not extract as readable words, or if the text fonts
    carry no ToUnicode map (the Type-3-without-ToUnicode regression that garbles
    "filtered"/"effective"/"coefficient"/"floor" into control chars). Returns the
    audit shape plus the text-layer ``summary``. This is the focused surface; G1
    (:func:`check_final_size_visual`) folds these same findings in so it covers the
    text layer, not just the figures."""
    manifest = measure_pdf_text(pdf_path, uv_bin=uv_bin)
    findings, summary = _text_layer_findings(manifest)
    return _result(findings, summary=summary,
                   examined_n=len(manifest["pages"]),
                   skipped_n=manifest.get("font_skipped", 0))


def check_final_size_visual(pdf_path: Union[str, Path], *,
                            aux_path: Optional[Union[str, Path]] = None,
                            min_pt: float = 6.0,
                            illegible_floor_pt: float = _ILLEGIBLE_FLOOR_PT,
                            page_cluster: int = _PAGE_CLUSTER,
                            uv_bin: str = _vg.DEFAULT_UV) -> dict[str, Any]:
    """G1 — inspect the compiled PDF at ACTUAL physical dimensions and REJECT
    illegible layout. Fires on three rendered defects the source cannot show:

      * ``layout-text-undersize`` — a page whose smallest rendered glyph is below
        ``illegible_floor_pt`` (or which carries >= ``page_cluster`` sub-``min_pt``
        glyphs). Reports the sub-6pt count and the minimum height per page, and
        names the figure that lands there (from the ``.aux``).
      * ``layout-type3-font`` — the document embeds Type-3 fonts (the matplotlib
        default): non-embeddable, bitmap-rendered, illegible at scale.
      * ``layout-clipped-glyph`` — a glyph is clipped past the page mediabox.

    HARD at release. Returns the audit shape plus ``measurements`` (the per-page
    table) and ``release_blocker: True``. Raises ``RuntimeError`` if the rasteriser
    subprocess is unavailable — a gate that cannot measure is loud, never a pass."""
    pdf_path = Path(pdf_path)
    manifest = measure_pdf_text(pdf_path, min_pt=min_pt, uv_bin=uv_bin)
    pages = manifest["pages"]

    fig_by_page: dict[int, list[str]] = {}
    if aux_path is not None:
        for label, rec in _figure_labels(parse_aux_labels(aux_path)).items():
            if isinstance(rec.get("page"), int):
                tag = f"Fig{rec['number']}={label}" if rec.get("number") else label
                fig_by_page.setdefault(rec["page"], []).append(tag)

    findings: list[dict[str, Any]] = []
    for pg in pages:
        pno = pg["page"]
        sub = pg["sub_count"]
        mn = pg["min_height"]
        undersized = (mn is not None and mn < illegible_floor_pt) or sub >= page_cluster
        if undersized:
            figs = fig_by_page.get(pno, [])
            where = f"p{pno}" + (f" ({', '.join(figs)})" if figs else "")
            findings.append(_finding(
                where,
                f"{sub} rendered characters below {min_pt:g}pt on this page "
                f"(smallest {mn:g}pt) — text scaled to illegibility",
                "regenerate the figure at final on-page size so all text is >= 6pt "
                "(raise the asset's font size or give the float more width)",
                "layout-text-undersize",
                page=pno, sub_count=sub, min_height=mn, figures=figs))

    type3 = manifest.get("type3_fonts") or []
    if type3:
        findings.append(_finding(
            "document fonts",
            f"{len(type3)} Type-3 fonts embedded (matplotlib default) — bitmap "
            "glyphs that are non-embeddable and illegible when scaled",
            "regenerate the figures with a vector font backend "
            "(matplotlib pdf.fonttype=42, i.e. TrueType/Type-42)",
            "layout-type3-font",
            type3_count=len(type3), sample=type3[:8]))
    elif manifest.get("type3_error"):
        # pikepdf unavailable — record the honest gap, do not claim clean.
        findings.append(_finding(
            "document fonts",
            f"Type-3 font scan could not run ({manifest['type3_error']})",
            "install pikepdf in the measurement env to enforce the Type-3 check",
            "layout-type3-font", assessed=False))

    for pg in pages:
        if pg["beyond_mediabox"] > 0:
            findings.append(_finding(
                f"p{pg['page']}",
                f"{pg['beyond_mediabox']} glyphs clipped past the page mediabox",
                "keep all label text inside the page/figure bounds",
                "layout-clipped-glyph",
                page=pg["page"], clipped=pg["beyond_mediabox"]))

    # the text layer, not just the figures: fold in the machine-readability findings
    # (garbled extraction / unmapped Type-3 text fonts) so G1 gates both surfaces.
    text_findings, text_summary = _text_layer_findings(manifest)
    findings += text_findings

    return _result(findings, measurements=pages, n_pages=manifest["n_pages"],
                   type3_count=len(type3), text_layer=text_summary,
                   release_blocker=True, hard=True,
                   examined_n=manifest["n_pages"],
                   skipped_n=manifest.get("font_skipped", 0),
                   thresholds={"min_pt": min_pt,
                               "illegible_floor_pt": illegible_floor_pt,
                               "page_cluster": page_cluster})


# ===========================================================================
# G2 — the semantic float gate
# ===========================================================================

def check_semantic_float(tex_root: Union[str, Path], *,
                         aux_path: Optional[Union[str, Path]] = None,
                         pdf_path: Optional[Union[str, Path]] = None,
                         backlog_pages: int = 1,
                         synctex_bin: str = "synctex") -> dict[str, Any]:
    """G2 — resolve each figure's first body ``\\ref`` page against its landing page
    and enforce the reading contract in PAGES:

      * ``float-orphan`` — the figure is never ``\\ref``'d in the body,
      * ``float-backlog`` — it lands more than ``backlog_pages`` pages past its first
        mention (the reader hits the mention with the figure pages away),
      * ``float-past-boundary`` — a body figure (referenced before the concluding
        section) lands on a later page than the conclusion / appendix boundary,
        where the argument is already closed. A same-page landing is recorded for
        visual review because page numbers alone cannot determine whether a
        top-of-page float precedes the heading.

    Landing pages come from the ``.aux`` (each figure's ``\\newlabel`` page = its
    shipout page). The first-mention page is resolved exactly via ``synctex`` when a
    PDF + ``.synctex.gz`` are available, else estimated from the mention's section
    page (aux) — reported per figure as ``ref_page_method``. Returns the audit shape
    plus a ``figures`` registry of every figure's resolved pages."""
    tex_root = Path(tex_root)
    if aux_path is None:
        cand = tex_root / "main.aux"
        aux_path = cand if cand.is_file() else None
    aux, aux_ok = _parse_aux_labels(aux_path) if aux_path else ({}, True)
    figs = _figure_labels(aux)
    conclusion, appendix = _boundary_pages(aux, tex_root)

    # the flattened manuscript + its section map, for the orphan/section fallback.
    target = tex_root / "main.tex" if (tex_root / "main.tex").is_file() else tex_root
    full = _gather_manuscript_text(target)
    spans = section_spans(full)
    # section slug -> aux page (a mention's section start page = the ref estimate).
    sec_page: dict[str, int] = {}
    for _s, _e, slug, title, _app in spans:
        # match the aux sec:* label page by the section number is indirect; instead
        # map by the section's own \label if it carries one near its start.
        pass
    # simpler, robust: build slug->page from the aux sec:* labels joined to spans by
    # order (both are in reading order).
    aux_secs = [v["page"] for k, v in sorted(
        ((k, v) for k, v in aux.items() if k.startswith("sec:")),
        key=lambda kv: (kv[1]["page"] if isinstance(kv[1].get("page"), int) else 1e9))
        if isinstance(v.get("page"), int)]

    findings: list[dict[str, Any]] = []
    registry: list[dict[str, Any]] = []
    same_page_boundaries: list[dict[str, Any]] = []
    pdf_path = Path(pdf_path) if pdf_path else None

    for label, rec in sorted(figs.items(),
                             key=lambda kv: (kv[1]["page"] or 1e9, kv[0])):
        landing = rec.get("page")
        number = rec.get("number")
        loc = _first_ref_location(tex_root, label)
        ref_page: Optional[int] = None
        method = "none"
        if loc is not None:
            # exact page via synctex when we have a PDF; else the section estimate.
            if pdf_path is not None and pdf_path.is_file():
                ref_page = _ref_page_via_synctex(pdf_path, tex_root, label, synctex_bin)
                if ref_page is not None:
                    method = "synctex"
            if ref_page is None:
                # section estimate: which section span the ref sits in -> that
                # section's aux page (reading-order join).
                pat = re.compile(_XREF_TMPL % re.escape(label))
                mref = pat.search(full)
                if mref is not None:
                    idx = None
                    for i, (s, e, _slug, _t, _a) in enumerate(spans):
                        if s <= mref.start() < e:
                            idx = i
                            break
                    if idx is not None and idx < len(aux_secs):
                        ref_page = aux_secs[idx]
                        method = "section-estimate"

        backlog = (landing - ref_page) if (isinstance(landing, int)
                                           and isinstance(ref_page, int)) else None
        entry = {"label": label, "number": number, "landing_page": landing,
                 "first_ref_page": ref_page, "ref_page_method": method,
                 "backlog": backlog, "orphan": loc is None}
        registry.append(entry)

        where = f"Fig{number}={label}" if number else label
        if loc is None:
            findings.append(_finding(
                where, f"figure '{label}' is never \\ref'd in the body — an orphan "
                       f"the reader meets with no prose hook (lands p{landing})",
                "reference the figure at the point the prose first invokes it, or drop it",
                "float-orphan", landing_page=landing))
            continue

        if backlog is not None and backlog > backlog_pages:
            findings.append(_finding(
                where, f"figure lands on p{landing} but is first mentioned on "
                       f"p{ref_page} — a {backlog}-page float backlog "
                       f"(> {backlog_pages})",
                "move the float toward its first mention, or add a nearer reference",
                "float-backlog", first_ref_page=ref_page, landing_page=landing,
                backlog=backlog, ref_page_method=method))

        # A body figure (mentioned before the concluding section) that ships out
        # on a LATER page than the conclusion or appendix boundary. Equal page
        # numbers do not encode vertical order: a figure* at the top of the page
        # can legitimately precede the heading. Surface those cases for visual
        # review rather than inventing a hard failure from page arithmetic.
        if isinstance(landing, int):
            crossed = None
            if conclusion is not None and landing > conclusion and (
                    ref_page is None or ref_page < conclusion):
                crossed = ("conclusion", conclusion)
            if appendix is not None and landing > appendix and (
                    ref_page is None or ref_page < appendix):
                crossed = ("appendix", appendix)   # the more severe boundary wins
            for name, bpage in (
                ("conclusion", conclusion),
                ("appendix", appendix),
            ):
                if (
                    bpage is not None
                    and landing == bpage
                    and (ref_page is None or ref_page < bpage)
                ):
                    same_page_boundaries.append({
                        "label": label,
                        "number": number,
                        "landing_page": landing,
                        "first_ref_page": ref_page,
                        "boundary": name,
                        "boundary_page": bpage,
                        "assessment": "visual-order-required",
                    })
            if crossed is not None:
                name, bpage = crossed
                findings.append(_finding(
                    where, f"body figure lands on p{landing}, at/after the "
                           f"{name} boundary (p{bpage}) — the reader meets it with "
                           f"the argument already closed",
                    f"pin the float before the {name}, near its p{ref_page} mention",
                    "float-past-boundary", landing_page=landing,
                    first_ref_page=ref_page, boundary=name, boundary_page=bpage))

    return _result(findings, figures=registry,
                   conclusion_boundary=conclusion, appendix_boundary=appendix,
                   same_page_boundaries=same_page_boundaries,
                   backlog_pages=backlog_pages,
                   examined_n=len(figs), skipped_n=0 if aux_ok else 1)


# ===========================================================================
# G3 — the figure contract registry
# ===========================================================================

_FIG_ENV_RE = re.compile(
    r"\\begin\{(figure\*?)\}(.*?)\\end\{\1\}", re.DOTALL)
_GRAPHIC_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
_LABEL_RE = re.compile(r"\\label\{([^}]+)\}")
_SPEC_COMMENT_RE = re.compile(r"%\s*spec:\s*(\S+)\s*\(status:\s*([^)]*)\)")
_PANEL_TOKEN_RE = re.compile(r"[Pp]anel\s*\(([a-h])\)|\(([a-h])\)")
_DATA_KEY_RE = re.compile(r"data source[s]?\s+([A-Z][A-Za-z0-9]*-N?\d+[a-z]?)")
_LIMIT_RE = re.compile(
    r"((?:It|The figure|This figure|Tested)[^.]*?"
    r"(?:does not establish|not hardness|proof of principle|establishes nothing|"
    r"not obtained for free|not a property)[^.]*\.)", re.I)


def _extract_caption(body: str) -> Optional[str]:
    """The balanced-brace content of the first ``\\caption{...}`` in a float."""
    m = re.search(r"\\caption(?:\[[^\]]*\])?\{", body)
    if not m:
        return None
    inner, _ = _read_braced(body, m.end() - 1)
    return inner.strip()


def _panels_in(text: str) -> list[str]:
    """The sorted set of panel letters an explicit ``(x)`` / ``Panel (x)`` names."""
    got: set[str] = set()
    for a, b in _PANEL_TOKEN_RE.findall(text or ""):
        got.add(a or b)
    return sorted(got)


def _evidence_type(caption: str) -> str:
    """Classify a caption's evidence class from its own language (mechanical, from
    the caption's declared method — not a judgement)."""
    low = caption.lower()
    if "schematic" in low or "toy example" in low or "didactic" in low:
        return "schematic"
    if "tebd" in low:
        return "tebd-simulation"
    if "exact diagonal" in low or "exact spectral sum" in low:
        return "exact-computation"
    if "dynamic-programming" in low or "counting recursion" in low:
        return "computed-table"
    if "finite-shot" in low or "sampling" in low or "synthetic" in low:
        return "sampled-numeric"
    return "empirical"


def _hero_claim(caption: str) -> Optional[str]:
    """The caption's one load-bearing sentence — the ``supports the …`` statement
    when present, else the first sentence."""
    m = re.search(r"([^.]*\bsupports?\b[^.]*\.)", caption)
    if m:
        return m.group(1).strip()
    first = caption.split(".")
    return (first[0].strip() + ".") if first and first[0].strip() else None


def build_figure_registry(tex_root: Union[str, Path], *,
                          aux_path: Optional[Union[str, Path]] = None,
                          pdf_path: Optional[Union[str, Path]] = None,
                          uv_bin: str = _vg.DEFAULT_UV,
                          resolve_asset_panels: bool = True,
                          scan: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    """One structured contract record per figure, extracted from the figure
    environment + caption + provenance comment (+ the rendered asset for panel
    labels): ``{label, number, spec_status, asset, evidence_type, hero_claim,
    panel_labels_caption, panel_labels_body, panel_labels_asset, caption_coverage,
    first_ref_page, landing_page, data_key, limitation}``. Read-only."""
    tex_root = Path(tex_root)
    if aux_path is None:
        cand = tex_root / "main.aux"
        aux_path = cand if cand.is_file() else None
    aux = parse_aux_labels(aux_path) if aux_path else {}
    figs_aux = _figure_labels(aux)

    target = tex_root / "main.tex" if (tex_root / "main.tex").is_file() else tex_root
    full = _gather_manuscript_text(target)

    # gather figure environments across the .tex fragments.
    records: list[dict[str, Any]] = []
    asset_paths: list[Path] = []
    pending: list[dict[str, Any]] = []
    examined_n = skipped_n = 0
    for f, _rel in _vg._tex_files(tex_root):
        try:
            body_text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            skipped_n += 1                         # a fragment lost -> its figures too
            continue
        examined_n += 1
        for m in _FIG_ENV_RE.finditer(body_text):
            env_body = m.group(2)
            lab_m = _LABEL_RE.search(env_body)
            if not lab_m:
                continue
            label = lab_m.group(1)
            caption = _extract_caption(env_body) or ""
            g = _GRAPHIC_RE.search(env_body)
            asset = g.group(1) if g else None
            spec = _SPEC_COMMENT_RE.search(env_body)
            cap_panels = _panels_in(caption)
            body_panels = _panels_in(_body_paragraph_of(full, label))
            data_keys = sorted(set(_DATA_KEY_RE.findall(caption)))
            limit_m = _LIMIT_RE.search(caption)
            rec = {
                "label": label,
                "number": figs_aux.get(label, {}).get("number"),
                "spec_status": spec.group(2).strip() if spec else None,
                "asset": asset,
                "evidence_type": _evidence_type(caption),
                "hero_claim": _hero_claim(caption),
                "panel_labels_caption": cap_panels,
                "panel_labels_body": body_panels,
                "panel_labels_asset": [],
                "caption_coverage": cap_panels,
                "first_ref_page": None,
                "landing_page": figs_aux.get(label, {}).get("page"),
                "data_key": data_keys,
                "limitation": limit_m.group(1).strip() if limit_m else None,
            }
            # resolve first-ref page (section estimate; synctex not needed for the
            # contract registry — the page is provenance, the panel check is the gate).
            loc = _first_ref_location(tex_root, label)
            rec["orphan"] = loc is None
            pending.append(rec)
            if asset:
                ap = (tex_root / asset)
                if not ap.suffix:
                    # \includegraphics without extension — prefer .pdf then .png
                    for ext in (".pdf", ".png", ".jpg"):
                        if (tex_root / (asset + ext)).is_file():
                            ap = tex_root / (asset + ext)
                            break
                if ap.is_file():
                    asset_paths.append(ap)
                    rec["_asset_path"] = ap.name

    panels_by_asset: dict[str, list[str]] = {}
    if resolve_asset_panels and asset_paths:
        try:
            panels_by_asset = extract_asset_panels(asset_paths, uv_bin=uv_bin)
        except RuntimeError:
            panels_by_asset = {}
    for rec in pending:
        an = rec.pop("_asset_path", None)
        if an and an in panels_by_asset:
            rec["panel_labels_asset"] = panels_by_asset[an]
        records.append(rec)
    if scan is not None:
        scan.update(examined_n=examined_n, skipped_n=skipped_n)
    return records


def _body_paragraph_of(full: str, label: str) -> str:
    """The prose paragraph containing the first ``\\ref`` of ``label`` — where the
    body narrates the figure's panels. Empty when the label is never referenced."""
    pat = re.compile(_XREF_TMPL % re.escape(label))
    m = pat.search(full)
    if not m:
        return ""
    start = full.rfind("\n\n", 0, m.start())
    start = 0 if start < 0 else start + 2
    end = full.find("\n\n", m.end())
    end = len(full) if end < 0 else end
    return full[start:end]


def check_figure_contract(tex_root: Union[str, Path], *,
                          aux_path: Optional[Union[str, Path]] = None,
                          pdf_path: Optional[Union[str, Path]] = None,
                          uv_bin: str = _vg.DEFAULT_UV,
                          resolve_asset_panels: bool = True) -> dict[str, Any]:
    """G3 — build the figure contract registry and enforce panel AGREEMENT across
    the three surfaces that must tell the same story:

      * ``figure-panel-uncovered`` — the ASSET draws a panel the CAPTION never
        covers (a five-panel graphic with a three-panel caption — a silent coverage
        hole no source gate sees, because the source is internally consistent),
      * ``figure-panel-body-mismatch`` — the CAPTION and the BODY prose name
        different panel sets (the two prose surfaces disagree on what is shown),
      * ``figure-contract-orphan`` — the figure has no body ``\\ref`` (registry note;
        G2 owns the placement finding).

    Returns the audit shape plus the ``registry`` (emit it as the structured
    artefact via :func:`write_registry`)."""
    scan: dict[str, Any] = {}
    registry = build_figure_registry(
        tex_root, aux_path=aux_path, pdf_path=pdf_path, uv_bin=uv_bin,
        resolve_asset_panels=resolve_asset_panels, scan=scan)
    findings: list[dict[str, Any]] = []
    for rec in registry:
        label = rec["label"]
        number = rec.get("number")
        where = f"Fig{number}={label}" if number else label
        asset = set(rec.get("panel_labels_asset") or [])
        cap = set(rec.get("panel_labels_caption") or [])
        body = set(rec.get("panel_labels_body") or [])

        uncovered = asset - cap
        if asset and uncovered:
            findings.append(_finding(
                where,
                f"asset draws panels {sorted(asset)} but the caption only covers "
                f"{sorted(cap)} — panel(s) {sorted(uncovered)} uncovered",
                "cover every asset panel in the caption, or drop the extra panels "
                "from the asset",
                "figure-panel-uncovered",
                panel_labels_asset=sorted(asset),
                panel_labels_caption=sorted(cap),
                uncovered=sorted(uncovered)))

        if cap and body and cap != body:
            findings.append(_finding(
                where,
                f"caption panels {sorted(cap)} disagree with the body-described "
                f"panels {sorted(body)}",
                "make the body prose and the caption name the same panel set",
                "figure-panel-body-mismatch",
                panel_labels_caption=sorted(cap),
                panel_labels_body=sorted(body)))

        if rec.get("orphan"):
            findings.append(_finding(
                where, f"figure '{label}' has no body \\ref (contract has no "
                       "reading hook)",
                "reference the figure where the prose first invokes it",
                "figure-contract-orphan", landing_page=rec.get("landing_page")))

    return _result(findings, registry=registry,
                   examined_n=scan.get("examined_n", 0),
                   skipped_n=scan.get("skipped_n", 0))


def write_registry(result_or_registry: Any, out_path: Union[str, Path]) -> str:
    """Emit the figure contract registry (a G3 result dict or a bare registry list)
    as a JSON artefact. Returns the written path."""
    reg = (result_or_registry.get("registry")
           if isinstance(result_or_registry, dict) else result_or_registry)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(reg, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    return str(out_path)


# ===========================================================================
# the release/panel seam — run all three gates over one compiled artefact
# ===========================================================================

def run_layout_gates(pdf_path: Union[str, Path], tex_root: Union[str, Path], *,
                     aux_path: Optional[Union[str, Path]] = None,
                     uv_bin: str = _vg.DEFAULT_UV,
                     size_gate: bool = True) -> dict[str, Any]:
    """Run G1 + G2 + G3 over one compiled artefact and return a combined result
    ``{clean, pass, gates: {size, float, contract}, findings, counts}`` fit to hand
    to ``release.build_bundle(gate_results=...)`` or a mechanical panel. ``size_gate``
    can be disabled to skip the render-dependent G1 where no rasteriser is available
    (G2/G3 are source+aux only). A gate that RAISES (e.g. G1 with no ``uv``) is
    recorded as ``{error: ...}`` rather than silently dropped — never a false pass."""
    tex_root = Path(tex_root)
    pdf_path = Path(pdf_path)
    if aux_path is None:
        cand = pdf_path.with_suffix(".aux")
        if not cand.is_file():
            cand = tex_root / "main.aux"
        aux_path = cand if cand.is_file() else None

    gates: dict[str, Any] = {}
    if size_gate:
        try:
            gates["size"] = check_final_size_visual(
                pdf_path, aux_path=aux_path, uv_bin=uv_bin)
        except RuntimeError as e:
            gates["size"] = {"pass": False, "clean": False, "error": str(e),
                             "findings": [], "counts": {}}
    gates["float"] = check_semantic_float(
        tex_root, aux_path=aux_path, pdf_path=pdf_path)
    gates["contract"] = check_figure_contract(
        tex_root, aux_path=aux_path, pdf_path=pdf_path, uv_bin=uv_bin)

    all_findings: list[dict[str, Any]] = []
    for g in gates.values():
        all_findings += g.get("findings", [])
    clean = all(g.get("pass", g.get("clean", False)) for g in gates.values())
    return {"clean": clean, "pass": clean, "gates": gates,
            "findings": all_findings, "counts": summarise(all_findings)}
