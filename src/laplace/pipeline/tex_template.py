"""The template + compile pillar: the documentclass/preamble GATE and the
typography LINT.

Two responsibilities, both pure-string in / structured-dict out (matching the
`{"pass": bool, ...}` idiom used across ``laplace.pipeline``):

* :func:`check_template` - the GATE. Asserts a manuscript is built on the
  REVTeX4-2 base, carries the eigen house layer (``\\usepackage{eigen-revtex}``,
  see ``templates/eigen-revtex/``), and pulls the required packages. Nothing in
  the pipeline enforced the documentclass before this - a projection could
  silently compile as plain ``article``. This closes that gate.

* :func:`lint_typography` - the LINT. Parses a real pdflatex ``.log`` for the
  irritations that survive a compile (overfull/underfull boxes, undefined
  refs/citations, multiply-defined labels, missing figures/inputs, font
  substitutions, hyperref/float warnings) and, when given the ``.tex`` source,
  enforces the house no-titles-on-figures rule. Returns structured findings.

Neither function edits or imports verify/schema/propagate/storyboard. The gate
is exposed for an orchestrator to wire into the verify registry; a focused test
lives in ``tests/test_tex_template.py``.
"""
from __future__ import annotations

import re
from typing import Any, Optional

# --- the contract the gate enforces -----------------------------------------

BASE_CLASS = "revtex4-2"
HOUSE_LAYER = "eigen-revtex"          # templates/eigen-revtex/eigen-revtex.sty
LEGACY_LAYER = "eigenengine"          # the article-class predecessor being retired

#: packages the eigen-revtex layer pulls in; if the layer is present these are
#: satisfied transitively, so an orchestrator need only require the layer.
LAYER_PROVIDES = frozenset({
    "fontenc", "microtype", "amsmath", "amsfonts", "amssymb", "amsthm", "bm",
    "braket", "mathtools", "physics", "graphicx", "subfig", "booktabs",
    "xcolor", "hyperref", "orcidlink",
})

#: the hard-required subset (from profiles/typography/prx-revtex4-2.json).
REQUIRED_PACKAGES = ("amsmath", "graphicx", "xcolor", "hyperref", "booktabs")


def _finding(category: str, severity: str, message: str, **extra: Any) -> dict[str, Any]:
    f = {"category": category, "severity": severity, "message": message}
    f.update(extra)
    return f


def _strip_tex_comments(src: str) -> str:
    """Drop LaTeX comments (unescaped ``%`` to end of line), preserving ``\\%``."""
    out = []
    for line in src.splitlines():
        i = 0
        n = len(line)
        while i < n:
            if line[i] == "\\" and i + 1 < n:      # escaped char, keep the pair
                i += 2
                continue
            if line[i] == "%":
                break
            i += 1
        out.append(line[:i])
    return "\n".join(out)


# ---------------------------------------------------------------------------
# THE GATE
# ---------------------------------------------------------------------------

_DOCUMENTCLASS_RE = re.compile(r"\\documentclass\s*(?:\[([^\]]*)\])?\s*\{([^}]+)\}")
_USEPACKAGE_RE = re.compile(r"\\(?:usepackage|RequirePackage)\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}")


def check_template(tex_source: str) -> dict[str, Any]:
    """Assert a manuscript uses REVTeX4-2 + the eigen house layer + required packages.

    Returns a dict with ``pass`` plus the observed ``documentclass``/``options``,
    whether the ``house_layer`` is present, the ``packages`` seen, any
    ``missing_required`` packages, and per-fault ``findings``.
    """
    src = _strip_tex_comments(tex_source)
    findings: list[dict[str, Any]] = []

    m = _DOCUMENTCLASS_RE.search(src)
    documentclass: Optional[str] = None
    options: list[str] = []
    if not m:
        findings.append(_finding(
            "documentclass", "error",
            "no \\documentclass found - the preamble is missing or malformed"))
    else:
        options = [o.strip() for o in (m.group(1) or "").split(",") if o.strip()]
        documentclass = m.group(2).strip()
        if documentclass != BASE_CLASS:
            findings.append(_finding(
                "documentclass", "error",
                f"documentclass is {documentclass!r}; the base must be {BASE_CLASS!r} "
                f"(a projection must not compile as plain '{documentclass}')",
                found=documentclass, expected=BASE_CLASS))

    # every \usepackage / \RequirePackage, expanding comma lists
    packages: list[str] = []
    for pm in _USEPACKAGE_RE.finditer(src):
        packages.extend(p.strip() for p in pm.group(1).split(",") if p.strip())
    pkgset = set(packages)

    house_layer = HOUSE_LAYER in pkgset
    # An artefact bound for other people's hands may declare itself outbound
    # (his ruling 2026-08-06, the six-author foreign artefact: "put it in a
    # standard revtex template as it's going to others"). The declaration is a
    # visible marker comment in the source, never inferred.
    outbound = bool(re.search(r"%\s*template:\s*standard-revtex\s*\(outbound\)",
                              tex_source))
    if not house_layer:
        if LEGACY_LAYER in pkgset:
            findings.append(_finding(
                "house_layer", "error",
                f"uses the legacy article-class layer '{LEGACY_LAYER}'; migrate to "
                f"'{HOUSE_LAYER}' on the REVTeX4-2 base", found=LEGACY_LAYER))
        elif outbound:
            findings.append(_finding(
                "house_layer", "info",
                "outbound artefact on standard REVTeX (declared by marker); "
                "the eigen house layer is intentionally absent"))
        else:
            findings.append(_finding(
                "house_layer", "error",
                f"missing the eigen house layer '\\usepackage{{{HOUSE_LAYER}}}'"))

    # required packages: satisfied if present in source or provided by the layer
    available = set(pkgset)
    if house_layer:
        available |= LAYER_PROVIDES
    missing_required = [p for p in REQUIRED_PACKAGES if p not in available]
    for p in missing_required:
        findings.append(_finding(
            "required_package", "error",
            f"required package '{p}' is neither loaded nor provided by the house layer",
            package=p))

    passed = not any(f["severity"] == "error" for f in findings)
    return {
        "pass": passed,
        "documentclass": documentclass,
        "options": options,
        "house_layer": house_layer,
        "packages": sorted(pkgset),
        "missing_required": missing_required,
        "findings": findings,
    }


# ---------------------------------------------------------------------------
# THE LINT
# ---------------------------------------------------------------------------

# pdflatex wraps log lines at 79 columns (max_print_line). De-wrap so the tail
# of a warning (e.g. "on input line 18") is not split from its head.
_WRAP_WIDTH = 79


def _dewrap_log(log_text: str, width: int = _WRAP_WIDTH) -> str:
    """Rejoin physical lines that pdftex hard-wrapped at ``width`` columns."""
    lines = log_text.splitlines()
    out: list[str] = []
    buf = ""
    for ln in lines:
        buf += ln
        if len(ln) >= width:            # likely a wrap - keep accumulating
            continue
        out.append(buf)
        buf = ""
    if buf:
        out.append(buf)
    return "\n".join(out)


_LINT_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    # (category, severity, pattern) - each capture group 1 is the salient token
    ("overfull_hbox", "warning",
     re.compile(r"^Overfull \\hbox \(([\d.]+)pt too wide\)(?:.*?at lines (\d+--\d+))?")),
    ("overfull_vbox", "warning",
     re.compile(r"^Overfull \\vbox \(([\d.]+)pt too high\)(?:.*?at lines (\d+--\d+))?")),
    ("underfull_hbox", "info",
     re.compile(r"^Underfull \\hbox \(badness (\d+)\)(?:.*?at lines (\d+--\d+))?")),
    ("underfull_vbox", "info",
     re.compile(r"^Underfull \\vbox \(badness (\d+)\)(?:.*?at lines (\d+--\d+))?")),
    ("undefined_reference", "error",
     re.compile(r"Reference `([^']+)' on page \d+ undefined")),
    ("undefined_citation", "error",
     re.compile(r"Citation `([^']+)' on page \d+ undefined")),
    ("multiply_defined_label", "error",
     re.compile(r"Label `([^']+)' multiply defined")),
    ("missing_file", "error",
     re.compile(r"File `([^']+)' not found")),
    ("font_substitution", "warning",
     re.compile(r"Font shape `([^']+)' (?:undefined|in size <[^>]*> not available)")),
    ("hyperref_warning", "warning",
     re.compile(r"Package hyperref Warning: (.+)")),
    ("float_warning", "warning",
     re.compile(r"(?:`[htbp!]+' float specifier changed to `[htbp!]+'|Float too large for page)")),
]

# \caption{...} scanning for the no-titles-on-figures rule
_CAPTION_RE = re.compile(r"\\caption\b\s*(?:\[[^\]]*\])?\s*\{")
_LEAD_MARKUP_RE = re.compile(r"^\s*\\(?:textbf|textit|emph|textsc|underline)\s*\{")
# panel labels are allowed leads: (a), (1), a), Top:, Left:, Bottom-left: ...
_PANEL_LABEL_RE = re.compile(r"^\(?[A-Za-z0-9]{1,3}\)?[:.\)]?\s*$|^[A-Za-z][A-Za-z -]*:\s*$")


def _match_brace(src: str, open_idx: int) -> tuple[str, int]:
    """Given index of an opening ``{``, return (inner_text, index_after_close)."""
    depth = 0
    i = open_idx
    n = len(src)
    start = open_idx + 1
    while i < n:
        c = src[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[start:i], i + 1
        i += 1
    return src[start:], n


def _check_no_titles_on_figures(tex_source: str) -> list[dict[str, Any]]:
    """Flag captions that open with a title (a bold/italic lead that is not a
    panel label). The caption is the figure's only prose surface."""
    findings: list[dict[str, Any]] = []
    src = _strip_tex_comments(tex_source)
    for m in _CAPTION_RE.finditer(src):
        open_idx = m.end() - 1
        inner, _ = _match_brace(src, open_idx)
        lead = _LEAD_MARKUP_RE.match(inner)
        if not lead:
            continue
        titled, _ = _match_brace(inner, lead.end() - 1)
        titled = titled.strip()
        if _PANEL_LABEL_RE.match(titled):
            continue                      # (a), Top:, ... are legitimate panel labels
        line_no = src.count("\n", 0, m.start()) + 1
        findings.append(_finding(
            "no_titles_on_figures", "warning",
            f"figure caption opens with a title {titled!r}; the caption is the "
            f"figure's only prose surface (no titles on figures)",
            line=line_no, title=titled))
    return findings


def lint_typography(log_text: str, tex_source: Optional[str] = None) -> dict[str, Any]:
    """Lint a pdflatex ``.log`` (and, optionally, the ``.tex`` source).

    ``log_text`` is a real pdflatex log. ``tex_source``, when supplied, enables
    the source-level no-titles-on-figures rule. Returns a dict with ``pass``
    (no error-severity findings), ``clean`` (no findings at all), ``counts`` by
    category, and the structured ``findings`` list.
    """
    findings: list[dict[str, Any]] = []
    for logical in _dewrap_log(log_text).splitlines():
        for category, severity, pat in _LINT_PATTERNS:
            mt = pat.search(logical)
            if not mt:
                continue
            groups = [g for g in mt.groups() if g]
            detail = mt.group(0).strip()
            f = _finding(category, severity, detail)
            if groups:
                f["token"] = groups[0]
            if len(groups) > 1:
                f["lines"] = groups[1]
            findings.append(f)
            break                          # one category per logical line

    if tex_source is not None:
        findings.extend(_check_no_titles_on_figures(tex_source))

    # de-duplicate identical findings (e.g. a missing file reported by both the
    # LaTeX warning and the pdftex.def error line collapse to one).
    seen: set[tuple[Any, ...]] = set()
    deduped: list[dict[str, Any]] = []
    for f in findings:
        key = tuple(sorted(f.items()))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(f)
    findings = deduped

    counts: dict[str, int] = {}
    for f in findings:
        counts[f["category"]] = counts.get(f["category"], 0) + 1

    passed = not any(f["severity"] == "error" for f in findings)
    return {
        "pass": passed,
        "clean": not findings,
        "counts": counts,
        "findings": findings,
    }
