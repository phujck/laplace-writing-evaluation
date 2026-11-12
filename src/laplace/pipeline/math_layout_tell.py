"""BITE A2 — the MECHANICAL tell for the math-layout WIDENING pathology.

The ruling this mechanises (his, 2026-07-10, evidence-backed): the old fixing
middle produced *detector-satisfying, object-worsening* fixes — an overfull
display was made to fit by WIDENING it (``\\resizebox``/``\\scalebox`` around the
math or table) or by FONT-SHRINKING it (a bare ``\\small`` / ``\\footnotesize`` /
``\\scriptsize`` / ``\\tiny`` wrapping the display), and full-width ``\\rule``
separators were drawn to paper over reflow. The overfull-box detector then read
CLEAN (there is no overfull box once the content is shrunk) while the object got
worse. The r1 PDF's pages 3/20/27 carry the forms; the r2 table
``tables_tex/tab_dp-price.tex`` still carries the ``\\small``-inside-``ruledtabular``
tell.

The OBJECT-CORRECT policy (carried verbatim into the fix brief by
:mod:`harnessed_stage`): *overfull displays are SPLIT across lines
(aligned/multline), never widened, never font-shrunk; tables rebuilt at correct
width.* This module is the falsifiable counterpart — the re-detect gains a tell
that FIRES on the widening forms, so a pass that "fixed" an overfull by shrinking
is caught as a regression even though the overfull count fell to zero.

Design law — GENERIC and false-positive-shy:
  * ``font=\\small`` inside a TikZ/pgf node style key is LEGITIMATE and MUST NOT
    trip — the discriminator is the leading ``font=`` (a pgfkey), which excludes
    it. A *bare* size command (its own token, no ``font=``) is the tell.
  * a size command is only the tell INSIDE (or immediately before) a display-math
    or tabular/table environment — a ``\\small`` around a paragraph of prose is a
    different (non-math-layout) matter and is not this pathology.
  * ``\\resizebox`` / ``\\scalebox`` / ``adjustbox`` count only when they WRAP a
    tabular/array/display — a scaled *figure* is A3's (vision) concern, not this.
  * a full-width ``\\rule`` (``\\linewidth`` / ``\\textwidth`` / ``\\columnwidth``)
    is a rule-width separator line — the paper-over form.

Nothing here pours through the ledger door (an unregistered widening kind would
route nowhere); the driver reads :func:`detect_widening` as a first-class
re-detect SIGNAL and compares its count pre/post pass. That keeps the tell
additive — it touches no shared gate, schema, or router.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

# size commands that shrink-to-fit (the font-shrink pathology).
_SIZE_CMDS = ("small", "footnotesize", "scriptsize", "tiny")
_SIZE_RE = re.compile(r"\\(" + "|".join(_SIZE_CMDS) + r")\b")

# a display / tabular environment whose interior a size command must never shrink,
# and which a scale wrapper must never widen. (Prose environments are excluded by
# design — the pathology is math/table layout, not paragraph sizing.)
_DISPLAY_ENVS = (
    "tabular", "tabular*", "tabularx", "array", "ruledtabular",
    "table", "table*", "longtable",
    "equation", "equation*", "align", "align*", "alignat", "alignat*",
    "multline", "multline*", "gather", "gather*", "eqnarray", "eqnarray*",
)
_BEGIN_RE = re.compile(r"\\begin\{([A-Za-z*]+)\}")
_END_RE = re.compile(r"\\end\{([A-Za-z*]+)\}")

# scale-to-fit wrappers; each counts only when a tabular/array/display opener
# follows within a short window (so a scaled figure/tikz is not swept in).
_SCALE_RE = re.compile(r"\\(resizebox|scalebox)\b|\\begin\{adjustbox\}")
_SCALE_TARGET_RE = re.compile(
    r"\\begin\{(?:tabular\*?|tabularx|array|ruledtabular|longtable)\}"
    r"|\\\[|\$\$|\\begin\{(?:equation\*?|align\*?|multline\*?|gather\*?)\}")

# a full-width rule used as a separator line (the paper-over form).
_RULE_RE = re.compile(r"\\rule\s*(?:\[[^\]]*\])?\s*\{\s*\\(linewidth|textwidth|columnwidth)\b")


def _strip_line_comment(line: str) -> str:
    """Drop a trailing LaTeX comment (an unescaped ``%``) but keep the code before
    it, so a commented-out ``\\small`` never trips the tell yet an inline note
    after real code does not hide it."""
    out = []
    prev = ""
    for ch in line:
        if ch == "%" and prev != "\\":
            break
        out.append(ch)
        prev = ch
    return "".join(out)


def _preceded_by_fontkey(line: str, at: int) -> bool:
    """True when the size command at column ``at`` is the VALUE of a pgf ``font=``
    key (``font=\\small`` in a TikZ node style) — the one legitimate use, excluded
    from the tell. Tolerates whitespace: ``font = \\small``."""
    head = line[:at].rstrip()
    return head.endswith("font=") or head.rstrip("=").rstrip().endswith("font")


def detect_widening(source: "str | Iterable[tuple[str, str]]") -> list[dict[str, Any]]:
    """The widening tell over LaTeX source.

    ``source`` is either the whole assembled text (one ``str``) or an iterable of
    ``(name, text)`` fragments — the fragment form gives each hit a ``file`` so the
    fix brief can name it. Returns a list of hit dicts, each::

        {"pathology": "widening", "kind": <subtype>, "file": <name|"">,
         "line": <1-based>, "quote": <offending line>, "issue": <what>,
         "fix": <the object-correct remedy>}

    Deterministic and side-effect-free. An empty list means no widening form is
    present (the object-correct state)."""
    if isinstance(source, str):
        fragments: list[tuple[str, str]] = [("", source)]
    else:
        fragments = list(source)

    hits: list[dict[str, Any]] = []
    for name, text in fragments:
        hits.extend(_scan_fragment(name, text))
    return hits


_SPLIT_FIX = ("SPLIT the display across lines (align/aligned/multline) — never "
              "widen, never font-shrink")
_TABLE_FIX = ("REBUILD the table at the correct column width (wrap long cells with "
              "a p{}/parbox column) — never \\small, never \\resizebox")
_RULE_FIX = ("remove the full-width \\rule separator — object-correct layout draws "
             "no paper-over separator line")


def _scan_fragment(name: str, text: str) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    raw_lines = text.splitlines()
    lines = [_strip_line_comment(l) for l in raw_lines]

    # environment stack: are we inside a display/tabular env right now?
    stack: list[str] = []
    # look-ahead helper: does a display/tabular opener appear within the next
    # `win` non-blank lines from index i (inclusive)?
    def _opener_ahead(i: int, win: int = 2) -> bool:
        seen = 0
        for j in range(i, min(len(lines), i + 8)):
            lj = lines[j]
            m = _BEGIN_RE.search(lj)
            if m and m.group(1) in _DISPLAY_ENVS:
                return True
            if lj.strip():
                seen += 1
                if seen > win:
                    break
        return False

    for i, line in enumerate(lines):
        in_display = any(e in _DISPLAY_ENVS for e in stack)

        # (1) font-shrink: a BARE size command inside — or immediately before — a
        #     display/table. font=\small (pgfkey) is excluded.
        for m in _SIZE_RE.finditer(line):
            if _preceded_by_fontkey(line, m.start()):
                continue
            if in_display or _opener_ahead(i):
                in_table = any(e in ("tabular", "tabular*", "tabularx", "array",
                                     "ruledtabular", "table", "table*", "longtable")
                               for e in stack) or _table_opener_ahead(lines, i)
                hits.append({
                    "pathology": "widening",
                    "kind": "table-fontshrink" if in_table else "display-fontshrink",
                    "file": name, "line": i + 1, "quote": raw_lines[i].strip(),
                    "issue": (f"bare \\{m.group(1)} shrinks a "
                              + ("table" if in_table else "display")
                              + " to fit (font-shrink pathology)"),
                    "fix": _TABLE_FIX if in_table else _SPLIT_FIX})
                break   # one hit per line is enough to flag it

        # (2) scale-to-fit wrapper around a tabular/array/display.
        sm = _SCALE_RE.search(line)
        if sm:
            window = "\n".join(lines[i:i + 6])
            if _SCALE_TARGET_RE.search(window):
                in_table = bool(re.search(
                    r"\\begin\{(?:tabular\*?|tabularx|array|ruledtabular|longtable)\}",
                    window))
                hits.append({
                    "pathology": "widening",
                    "kind": "table-scalebox" if in_table else "display-scalebox",
                    "file": name, "line": i + 1, "quote": raw_lines[i].strip(),
                    "issue": ("\\resizebox/\\scalebox widens a "
                              + ("table" if in_table else "display")
                              + " to fit (scale-to-fit pathology)"),
                    "fix": _TABLE_FIX if in_table else _SPLIT_FIX})

        # (3) full-width rule separator.
        rm = _RULE_RE.search(line)
        if rm:
            hits.append({
                "pathology": "widening", "kind": "rule-width-separator",
                "file": name, "line": i + 1, "quote": raw_lines[i].strip(),
                "issue": f"full-width \\rule{{\\{rm.group(1)}}} separator line",
                "fix": _RULE_FIX})

        # env stack maintenance (after the checks, so a line that both opens an
        # env and carries a size command reads as "before the opener").
        for bm in _BEGIN_RE.finditer(line):
            if bm.group(1) in _DISPLAY_ENVS:
                stack.append(bm.group(1))
        for em in _END_RE.finditer(line):
            if em.group(1) in _DISPLAY_ENVS and stack:
                # pop the matching env if present (tolerant of interleaving)
                if em.group(1) in stack:
                    # pop from the top down to the matching name
                    while stack and stack[-1] != em.group(1):
                        stack.pop()
                    if stack:
                        stack.pop()
    return hits


def _table_opener_ahead(lines: list[str], i: int, win: int = 2) -> bool:
    seen = 0
    for j in range(i, min(len(lines), i + 8)):
        if re.search(r"\\begin\{(?:tabular\*?|tabularx|array|ruledtabular|"
                     r"longtable|table\*?)\}", lines[j]):
            return True
        if lines[j].strip():
            seen += 1
            if seen > win:
                break
    return False


def widening_summary(hits: list[dict[str, Any]]) -> dict[str, Any]:
    """A compact rollup of :func:`detect_widening` hits for a stage evidence file:
    total count + per-kind counts + the distinct files touched."""
    by_kind: dict[str, int] = {}
    for h in hits:
        by_kind[h.get("kind", "?")] = by_kind.get(h.get("kind", "?"), 0) + 1
    return {"n": len(hits), "by_kind": by_kind,
            "files": sorted({h.get("file", "") for h in hits if h.get("file")})}
