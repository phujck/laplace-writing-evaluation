"""Project-declared closure checks for an authored manuscript.

The generic crosslink audit catches dangling references, vague locational
language, and some symbol-level reliance.  This gate supplies the conjugate
project contract: the author declares which links carry the argument, and the
assembled manuscript must contain them in the sections where they are owed.

The contract also fixes the introduction roadmap as its final prose paragraph
and checks that every numbered equation and figure is both defined once and
cited in the text.  It is deliberately semantic configuration, not a prose
generator.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Union

from laplace.pipeline.graph import _gather_manuscript_text
from laplace.pipeline.apparatus_common import FINDING_KIND_STAGE, iter_paragraphs, section_spans


_XREF_RE = re.compile(r"\\(?:ref|eqref|autoref|cref|Cref|pageref)\{([^}]+)\}")
_LABEL_RE = re.compile(r"\\label\{([^}]+)\}")


def _finding(where: str, issue: str, fix: str, kind: str) -> dict[str, str]:
    return {
        "where": where,
        "issue": issue,
        "fix": fix,
        "kind": kind,
        "route": FINDING_KIND_STAGE[kind],
    }


def _section_text(full: str, section_id: str) -> str:
    for start, end, slug, _title, _appendix in section_spans(full):
        body = full[start:end]
        owned_labels = set(_LABEL_RE.findall(body))
        if (slug == section_id
                or f"sec:{section_id}" in owned_labels
                or f"app:{section_id}" in owned_labels):
            return body
    return ""


def _prose_paragraphs(section: str) -> list[str]:
    paragraphs: list[str] = []
    for _start, _end, para in iter_paragraphs(section):
        visible = "\n".join(
            line for line in para.splitlines()
            if line.strip() and not line.lstrip().startswith("%")
        ).strip()
        if not visible:
            continue
        if visible.startswith(("\\section", "\\subsection", "\\begin{figure",
                               "\\includegraphics", "\\caption", "\\label")):
            continue
        paragraphs.append(visible)
    return paragraphs


def _refs(text: str) -> list[str]:
    return [
        key.strip()
        for match in _XREF_RE.finditer(text)
        for key in match.group(1).split(",")
        if key.strip()
    ]


def check_authored_closure(
    target: Union[str, Path],
    contract: Union[str, Path],
) -> dict[str, Any]:
    """Check an assembled manuscript against its authored closure contract."""
    target = Path(target)
    contract_path = Path(contract)
    spec = json.loads(contract_path.read_text(encoding="utf-8"))
    full = _gather_manuscript_text(target)
    findings: list[dict[str, str]] = []

    roadmap = spec.get("roadmap", {})
    intro_id = roadmap.get("section")
    required_roadmap = roadmap.get("ordered_section_refs", [])
    intro = _section_text(full, intro_id) if intro_id else ""
    paragraphs = _prose_paragraphs(intro)
    if not intro:
        findings.append(_finding(
            str(intro_id), "roadmap section is absent",
            "define the contracted introduction section", "closure-roadmap-section"))
    elif not paragraphs:
        findings.append(_finding(
            str(intro_id), "roadmap section contains no prose paragraphs",
            "write the introduction before running the closure gate",
            "closure-roadmap-empty"))
    else:
        final_refs = _refs(paragraphs[-1])
        positions = []
        for label in required_roadmap:
            try:
                positions.append(final_refs.index(label))
            except ValueError:
                findings.append(_finding(
                    str(intro_id),
                    f"final introduction paragraph does not reference '{label}'",
                    "add the live section reference to the roadmap",
                    "closure-roadmap-missing"))
        if len(positions) == len(required_roadmap) and positions != sorted(positions):
            findings.append(_finding(
                str(intro_id),
                "final introduction paragraph does not give the contracted section order",
                "order the live section references by the argument's reading sequence",
                "closure-roadmap-order"))
        earlier = "\n\n".join(paragraphs[:-1])
        leaked = [label for label in required_roadmap if label in _refs(earlier)]
        if leaked:
            findings.append(_finding(
                str(intro_id),
                "the full section roadmap appears before the final introduction paragraph: "
                + ", ".join(leaked),
                "keep the ordered document map in the final introduction paragraph",
                "closure-roadmap-position"))

    for dependency in spec.get("dependency_links", []):
        source = dependency["source"]
        body = _section_text(full, source)
        present = set(_refs(body))
        for label in dependency.get("requires", []):
            if label not in present:
                findings.append(_finding(
                    source,
                    f"argument dependency '{label}' is not linked from this section",
                    "cite the defining equation, figure, section, or appendix where the "
                    "dependent claim is made",
                    "closure-dependency-unlinked"))
        for group in dependency.get("requires_one_of", []):
            if not present.intersection(group):
                findings.append(_finding(
                    source,
                    "argument requires one of these links but contains none: "
                    + ", ".join(group),
                    "add the most precise live reference at the point of reliance",
                    "closure-dependency-unlinked"))

    refs = _refs(full)
    labels = _LABEL_RE.findall(full)
    for object_label in spec.get("numbered_objects", []):
        count = labels.count(object_label)
        if count != 1:
            findings.append(_finding(
                object_label,
                f"numbered object is defined {count} times rather than once",
                "emit the object once from its ledger entry",
                "closure-object-definition"))
        if object_label not in refs:
            findings.append(_finding(
                object_label,
                "numbered object is never cited in manuscript prose",
                "link the equation or figure where the argument uses its result",
                "closure-object-orphan"))

    return {
        "pass": not findings,
        "contract": str(contract_path),
        "roadmap_section": intro_id,
        "dependency_count": len(spec.get("dependency_links", [])),
        "object_count": len(spec.get("numbered_objects", [])),
        "findings": findings,
        "counts": {
            kind: sum(1 for f in findings if f["kind"] == kind)
            for kind in sorted({f["kind"] for f in findings})
        },
    }
