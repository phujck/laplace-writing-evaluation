"""The promised-but-absent detector — a mechanical panel member (his catch,
ARMING_2026-07-16: "does it look like a paper?"; the orchestrator's own read of
falqon found 0 figures against 3 promised, cross-references to nothing, plots
named as "registered TODOs").

A finished artefact must not CLAIM the existence of a thing it does not CONTAIN.
This gate parses the assembled manuscript for existence claims — figure/table/
plot promises, cross-references, citations, section/appendix pointers — and diffs
each against what the artefact actually carries, emitting one typed finding per
broken promise. It is the conjugate of the scaffold-wipe (which proves no
construction debris SURVIVED); this proves nothing was PROMISED that never got
built.

The design constraint that keeps it low-false-positive is the *artefact-state
gate* on float promises: the bare word "figure" routinely means a numeric value
in a physics paper ("every cost figure is quoted against it"), so a naive scan
drowns in false hits. The gate only fires a ``promise-*-absent`` finding when the
artefact contains ZERO floats of that class — in which case ANY figure/plot/table
promise is unambiguously unkept — OR, when floats do exist, only on a NUMBERED
reference (``Figure~3``) that outruns the float count. Deictic prose ("the plot",
"every figure in this paper") is charged only under the zero-float branch.

The kinds and their owning stage (folded into ``schema.KIND_TO_WORK`` via
``register_component_kinds``):

* ``promise-figure-absent``   — prose promises a figure/plot the artefact lacks
* ``promise-table-absent``    — prose promises a table the artefact lacks
* ``promise-xref-dangling``   — a ``\\ref``/``\\eqref``/``\\cref`` resolves to no ``\\label``
* ``promise-citation-absent`` — a ``\\cite`` key is absent from the bibliography
* ``promise-section-absent``  — a "Section N"/"Appendix X" pointer names no such division

All figure/table/xref kinds route to ``figures``/``structural`` (the stage that
mints the missing object or wires the reference); the citation kind routes to
``prose`` (the citation is placed in prose). ``promise-section-absent`` routes to
``narrative`` (a structural/roadmap fault).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional, Union

from laplace.pipeline.graph import _gather_manuscript_text
from laplace.pipeline.apparatus_common import (
    line_quote,
    section_of,
    section_spans,
    summarise,
)

# --- the kinds this organ owns -> owning stage (the schema-wire manifest) ----
FINDING_KIND_STAGE: dict[str, str] = {
    "promise-figure-absent": "figures",     # a promised figure/plot with no float
    "promise-table-absent": "figures",      # a promised table with no float
    "promise-xref-dangling": "structural",  # \ref/\eqref to a missing \label
    "promise-citation-absent": "prose",     # a \cite key absent from the bib
    "promise-section-absent": "narrative",  # a Section/Appendix pointer to nothing
}


# --- the artefact's own contents ---------------------------------------------
_FLOAT_RE = re.compile(r"\\begin\{(figure|table)\*?\}")
_GRAPHIC_RE = re.compile(r"\\includegraphics\b")
_LABEL_RE = re.compile(r"\\label\{([^}]+)\}")
_XREF_RE = re.compile(r"\\(ref|eqref|autoref|cref|Cref|pageref|nameref)\{([^}]+)\}")
_CITE_RE = re.compile(r"\\cite[a-zA-Z]*\s*(?:\[[^\]]*\])*\{([^}]+)\}")
_SECTION_CMD_RE = re.compile(r"\\(sub)*section\*?\{")
_INPUT_RE = re.compile(r"\\(?:input|include)\{([^}]+)\}")
_APPENDIX_RE = re.compile(r"\\appendix\b")
_BIBITEM_RE = re.compile(r"\\bibitem(?:\[[^\]]*\])?\{([^}]+)\}")
_BIBKEY_RE = re.compile(r"^\s*@[A-Za-z]+\s*\{\s*([^,\s]+)", re.MULTILINE)

# --- the prose existence-claims ----------------------------------------------
# A NUMBERED float reference: "Figure 3", "Fig.~2", "Table 1". The number lets us
# check it against the float count even when floats exist.
_NUM_FIG_RE = re.compile(r"\b(?:Figure|Fig)\.?~?\s*(\d+)\b")
_NUM_TAB_RE = re.compile(r"\b(?:Table|Tab)\.?~?\s*(\d+)\b")
# DEICTIC float promises (charged only when zero floats of the class exist): a
# named plot/chart/diagram. The bare word "figure" is DELIBERATELY excluded — in a
# physics paper it overwhelmingly means a numeric value ("cost figure", "the
# overhead figure"), so the whole-paper claim (_EVERY_FIG_RE) and the numbered
# reference (_NUM_FIG_RE) carry the "figure" sense instead; only the unambiguous
# graphic nouns are matched deictically.
_PLOT_PROMISE_RE = re.compile(
    r"\b(?:the|a|this|our|each|both|two|following)\s+"
    r"(?:[\w-]+[- ]){0,3}(?:plot|subplot|chart|scatter(?:plot)?|histogram|heat-?map)\b",
    re.IGNORECASE)
_EVERY_FIG_RE = re.compile(r"\bevery figure in this paper\b", re.IGNORECASE)
# A pointer to a numbered/lettered division: "Section 9", "Appendix B".
_SECREF_RE = re.compile(r"\b(Section|Sec|Appendix|App)\.?~?\s*(\d+|[A-Z])\b")

# guards against the numeric-value sense of "figure/plot"
_NUMERIC_FIGURE_CTX = re.compile(
    r"\b(?:cost|resource|wall-?clock|headline|point|value|merit)\s+figure\b",
    re.IGNORECASE)


def _bib_keys(bib: Optional[Union[str, Path]], full: str) -> set[str]:
    """Every citation key the artefact can resolve: the .bib file's entry keys
    plus any ``\\bibitem`` in a rendered ``thebibliography``. An absent/unreadable
    bib yields the bibitem keys alone (possibly empty)."""
    keys = {m.group(1).strip() for m in _BIBITEM_RE.finditer(full)}
    if bib is not None:
        p = Path(bib)
        if p.is_file():
            txt = p.read_text(encoding="utf-8", errors="replace")
            keys |= {m.group(1).strip() for m in _BIBKEY_RE.finditer(txt)}
    return keys


def _division_census(target: Path, full: str) -> tuple[int, int]:
    """``(n_body_sections, n_appendix_sections)``. Robust across both the
    explicit-``\\section`` convention and the staged ``\\input``-fragment
    convention: count each and take the larger per side, split at ``\\appendix``.
    The raw main.tex (not the flattened text) carries the ``\\input`` structure the
    gatherer dissolves, so read it directly when present."""
    # (a) explicit \section headings in the flattened text
    ap_full = _APPENDIX_RE.search(full)
    sec_body = sec_app = 0
    for m in _SECTION_CMD_RE.finditer(full):
        if m.group(1):                          # a \subsection — not a top division
            continue
        if ap_full and m.start() >= ap_full.start():
            sec_app += 1
        else:
            sec_body += 1
    # (b) \input fragments in the raw main.tex, split at \appendix
    inp_body = inp_app = 0
    try:
        raw = target.read_text(encoding="utf-8", errors="replace")
    except Exception:
        raw = ""
    ap_raw = _APPENDIX_RE.search(raw)
    for m in _INPUT_RE.finditer(raw):
        stem = m.group(1).rsplit("/", 1)[-1]
        if stem in ("abstract",):               # front matter, not a numbered section
            continue
        if ap_raw and m.start() >= ap_raw.start():
            inp_app += 1
        else:
            inp_body += 1
    return max(sec_body, inp_body), max(sec_app, inp_app)


def _finding(where: str, issue: str, fix: str, kind: str,
             quote: Optional[str] = None) -> dict[str, Any]:
    rec: dict[str, Any] = {"where": where}
    if quote:
        rec["quote"] = quote[:240]
    rec["issue"] = issue
    rec["fix"] = fix
    rec["kind"] = kind
    rec["route"] = FINDING_KIND_STAGE.get(kind, "figures")
    return rec


def check_promises(target: Union[str, Path],
                   bib: Optional[Union[str, Path]] = None) -> dict[str, Any]:
    """Audit the assembled manuscript for existence claims the artefact does not
    honour. ``target`` is the main ``.tex``; ``bib`` is the bibliography source
    (defaults to ``<dir>/refs.bib`` when present). Returns
    ``{pass, findings, counts, present}`` where ``present`` is the artefact-content
    census the diff was taken against — the primary record, so a reviewer can see
    what the gate believed the artefact contained."""
    target = Path(target)
    full = _gather_manuscript_text(target)
    spans = section_spans(full)

    if bib is None:
        cand = target.parent / "refs.bib"
        bib = cand if cand.is_file() else None

    n_figs = len(_FLOAT_RE.findall(full))       # figure+table \begin count
    fig_envs = _FLOAT_RE.findall(full)
    n_figure = sum(1 for e in fig_envs if e == "figure")
    n_table = sum(1 for e in fig_envs if e == "table")
    n_graphics = len(_GRAPHIC_RE.findall(full))
    labels = {m.group(1).strip() for m in _LABEL_RE.finditer(full)}
    bibkeys = _bib_keys(bib, full)

    # section/appendix census. Two conventions coexist in the corpus: a paper may
    # carry explicit \section{} headings, OR (the staged-projection convention) a
    # main.tex that \inputs bare prose fragments with the sectioning implied by the
    # \input order split at \appendix. Count BOTH and take the larger per side, so
    # neither convention reads as "zero sections".
    n_body_sections, n_appendix_sections = _division_census(target, full)
    appendix_letters = {chr(ord("A") + i) for i in range(n_appendix_sections)}

    present = {
        "figures": n_figure, "tables": n_table, "graphics": n_graphics,
        "labels": len(labels), "bib_keys": len(bibkeys),
        "body_sections": n_body_sections, "appendices": n_appendix_sections,
    }

    findings: list[dict[str, Any]] = []
    seen_fig_absent = False       # dedupe the whole-paper figure verdict to once

    def _where(pos: int) -> str:
        slug, _t, _a = section_of(pos, spans)
        return slug or "?"

    # -- FIGURES / PLOTS --------------------------------------------------------
    # zero-float branch: any figure/plot promise is unkept. Numbered-float branch:
    # only a reference past the float count is unkept.
    if n_figure == 0 and n_graphics == 0:
        for m in _EVERY_FIG_RE.finditer(full):
            findings.append(_finding(
                _where(m.start()),
                "prose claims 'every figure in this paper' but the artefact "
                "contains no figure float and no \\includegraphics",
                "generate the figures and \\input them at their promise sites, "
                "or remove the claim",
                "promise-figure-absent", quote=line_quote(full, m.start())))
            seen_fig_absent = True
        for m in _PLOT_PROMISE_RE.finditer(full):
            frag = m.group(0)
            # skip the numeric-value sense ("cost figure") and the meta word "panel"
            # inside a math/algorithm context is rare here; keep the plot/figure/chart
            if _NUMERIC_FIGURE_CTX.search(line_quote(full, m.start())):
                continue
            if re.search(r"\bfigure\b", frag, re.IGNORECASE) and \
               re.search(r"\b(?:cost|resource|merit|value)\b",
                         line_quote(full, m.start()), re.IGNORECASE):
                continue
            findings.append(_finding(
                _where(m.start()),
                f"prose names '{frag.strip()}' but the artefact renders no "
                "figure/plot (zero floats, zero \\includegraphics)",
                "render the named plot and place it, or strike the reference",
                "promise-figure-absent", quote=line_quote(full, m.start())))
            seen_fig_absent = True
    else:
        for m in _NUM_FIG_RE.finditer(full):
            n = int(m.group(1))
            if n > n_figure:
                findings.append(_finding(
                    _where(m.start()),
                    f"prose references Figure {n} but the artefact contains only "
                    f"{n_figure} figure float(s)",
                    "add the missing figure or renumber the reference",
                    "promise-figure-absent", quote=line_quote(full, m.start())))

    # -- TABLES -----------------------------------------------------------------
    if n_table == 0:
        for m in _NUM_TAB_RE.finditer(full):
            findings.append(_finding(
                _where(m.start()),
                f"prose references Table {int(m.group(1))} but the artefact "
                "contains no table float",
                "add the table environment or strike the reference",
                "promise-table-absent", quote=line_quote(full, m.start())))
    else:
        for m in _NUM_TAB_RE.finditer(full):
            n = int(m.group(1))
            if n > n_table:
                findings.append(_finding(
                    _where(m.start()),
                    f"prose references Table {n} but the artefact contains only "
                    f"{n_table} table float(s)",
                    "add the missing table or renumber the reference",
                    "promise-table-absent", quote=line_quote(full, m.start())))

    # -- CROSS-REFERENCES -------------------------------------------------------
    for m in _XREF_RE.finditer(full):
        cmd = m.group(1)
        for key in (k.strip() for k in m.group(2).split(",")):
            if key and key not in labels:
                findings.append(_finding(
                    _where(m.start()),
                    f"\\{cmd}{{{key}}} resolves to no \\label — a dangling "
                    "cross-reference the reader hits as '??'",
                    "define the target \\label or remove the reference",
                    "promise-xref-dangling", quote=line_quote(full, m.start())))

    # -- CITATIONS --------------------------------------------------------------
    for m in _CITE_RE.finditer(full):
        for key in (k.strip() for k in m.group(1).split(",")):
            if key and key not in bibkeys:
                findings.append(_finding(
                    _where(m.start()),
                    f"\\cite{{{key}}} names a key absent from the bibliography — "
                    "the reference is promised but will render as '[?]'",
                    "add the entry to the .bib source or correct the key",
                    "promise-citation-absent", quote=line_quote(full, m.start())))

    # -- SECTION / APPENDIX POINTERS -------------------------------------------
    for m in _SECREF_RE.finditer(full):
        word, tgt = m.group(1), m.group(2)
        is_app = word.lower().startswith("app")
        if is_app:
            if tgt.isdigit() or tgt not in appendix_letters:
                findings.append(_finding(
                    _where(m.start()),
                    f"prose points to Appendix {tgt} but the artefact has "
                    f"{n_appendix_sections} appendix division(s) "
                    f"({''.join(sorted(appendix_letters)) or 'none'})",
                    "add the appendix or correct the pointer",
                    "promise-section-absent", quote=line_quote(full, m.start())))
        else:
            if tgt.isdigit() and int(tgt) > n_body_sections:
                findings.append(_finding(
                    _where(m.start()),
                    f"prose points to Section {tgt} but the artefact has "
                    f"{n_body_sections} top-level section(s)",
                    "add the section or correct the pointer",
                    "promise-section-absent", quote=line_quote(full, m.start())))

    return {
        "pass": not findings,
        "present": present,
        "findings": findings,
        "counts": summarise(findings),
    }


def finding_kinds_manifest() -> list[dict[str, str]]:
    """kind -> owning stage, the row shape ``register_component_kinds`` folds into
    ``schema.KIND_TO_WORK``."""
    return [{"kind": k, "stage": s} for k, s in FINDING_KIND_STAGE.items()]
