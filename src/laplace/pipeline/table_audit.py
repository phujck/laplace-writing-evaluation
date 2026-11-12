"""C7 — the tables / algorithms gate (checklist cat 8, low urgency).

A node-kind check plus a basic structure gate for the two float kinds the
figure/caption modules do not cover as graphics: ``table`` and ``algorithm``
environments. SSG carries one table (``tab:dp-price``), so this is a small gate,
but it closes the float apparatus:

* ``table-uncaptioned``  — a table/algorithm float with no ``\\caption``,
* ``table-unreferenced`` — a labelled table/algorithm nothing ``\\ref``s,
* ``table-malformed``    — the ``tabular`` column count (from the row of body
  cells) exceeds the ``\\begin{tabular}{...}`` column spec, or the table has no
  rule/header at all.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Union

from laplace.pipeline.graph import _gather_manuscript_text
from laplace.pipeline.apparatus_common import (
    finding, section_spans, section_of, summarise, xref_positions,
)

_TABLE_RE = re.compile(r"\\begin\{(table|algorithm|algorithmic)(\*?)\}(.*?)\\end\{\1\2\}", re.DOTALL)
_CAPTION_RE = re.compile(r"\\caption\{")
_LABEL_RE = re.compile(r"\\label\{([^}]+)\}")
_TABULAR_RE = re.compile(r"\\begin\{tabular\}\{([^}]*)\}(.*?)\\end\{tabular\}", re.DOTALL)
_RULE_RE = re.compile(r"\\toprule|\\midrule|\\bottomrule|\\hline")


def _colspec_count(spec: str) -> int:
    """Column count from a ``tabular`` preamble: count l/c/r/p/m/b columns,
    ignoring ``|`` rules and ``@{}`` / ``p{..}`` argument braces."""
    spec = re.sub(r"[pmb]\{[^}]*\}", "P", spec)   # p{..} → one column token
    spec = re.sub(r"@\{[^}]*\}|\|", "", spec)
    return len(re.findall(r"[lcrP]", spec))


def check_tables_algorithms(target: Union[str, Path]) -> dict[str, Any]:
    """Audit table/algorithm floats on a compiled manuscript."""
    target = Path(target)
    full = _gather_manuscript_text(target)
    spans = section_spans(full)
    refs = xref_positions(full)

    findings: list[dict[str, Any]] = []
    n = 0
    for m in _TABLE_RE.finditer(full):
        env, _star, body = m.group(1), m.group(2), m.group(3)
        if env == "algorithmic":
            continue                          # inner env; the algorithm wrapper owns it
        n += 1
        pos = m.start()
        slug, _t, _a = section_of(pos, spans)
        lab_m = _LABEL_RE.search(body)
        label = lab_m.group(1) if lab_m else None
        where = f"{slug or '?'}:{label or f'{env}@{pos}'}"

        if not _CAPTION_RE.search(body):
            findings.append(finding(
                where, f"{env} float has no \\caption",
                "add a caption naming what the table/algorithm establishes",
                "table-uncaptioned"))
        if not label:
            findings.append(finding(
                where, f"{env} float has no \\label to reference it by",
                "add a \\label and reference it from the body",
                "table-unreferenced"))
        elif not refs.get(label):
            findings.append(finding(
                where, f"{env} '{label}' is never \\ref'd in the body",
                "reference the table/algorithm at its first mention",
                "table-unreferenced"))

        if env == "table":
            tab = _TABULAR_RE.search(body)
            if tab:
                cols = _colspec_count(tab.group(1))
                rows = [r for r in re.split(r"\\\\", tab.group(2)) if r.strip()]
                # widest body row's cell count (& separators + 1)
                widest = max((r.count("&") + 1 for r in rows), default=0)
                if cols and widest > cols:
                    findings.append(finding(
                        where,
                        f"a table row has {widest} cells but the column spec declares {cols}",
                        "align the row cell count with the \\begin{tabular} column spec",
                        "table-malformed", quote=tab.group(1)))
                if not _RULE_RE.search(body):
                    findings.append(finding(
                        where, "table has no rule/header (booktabs \\toprule or \\hline)",
                        "add a header rule so the columns read as a structured table",
                        "table-malformed"))

    return {
        "pass": not findings,
        "n_tables": n,
        "findings": findings,
        "counts": summarise(findings),
    }
