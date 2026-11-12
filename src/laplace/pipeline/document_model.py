"""Stage F — the document model (rebuild mandate §9) + §11.4 prose fidelity.

A backend-neutral, DERIVED view of the rendered manuscript: headings,
paragraph blocks (joined to their prose-provenance records), equations,
figure/table references, citations and cross-references, in the true
``\\input`` reading order. Derivation keeps the fragments as the working
surface (the storyboard's marker machinery reads them) while giving
validation and the viewer one typed object:
``<manuscript_dir>/document_model.json``.

§11.4 (prose fidelity) runs here because the model and the provenance
sidecars meet here: every generated paragraph traces to its paragraph plan,
no plan is silently dropped, no citation appears that the contract does not
carry.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from laplace.pipeline import narrative, pathsafe, registry, schema

_ENV_RE = re.compile(
    r"\\begin\{(equation\*?|align\*?|figure\*?|table\*?|ruledtabular)\}"
    r".*?\\end\{\1\}", re.DOTALL)


def _fragment_blocks(text: str) -> list[str]:
    """Prose paragraph blocks: comment lines out, display environments lifted
    (they anchor, they are not prose), then blank-line splitting. A block
    counts as prose when it carries real words — description-list bodies and
    other command-opening blocks with sentence content count; bare command
    lines do not."""
    no_comments = "\n".join(l for l in text.splitlines()
                            if not l.lstrip().startswith("%"))
    no_envs = _ENV_RE.sub("\n\n", no_comments)
    no_heads = re.sub(r"\\(sub)*section\*?\{[^}]*\}|\\label\{[^}]*\}", "", no_envs)
    blocks = []
    for b in re.split(r"\n\s*\n", no_heads):
        b = b.strip()
        if not b:
            continue
        words = re.findall(r"(?<![\\{])\b[A-Za-z]{3,}\b", b)
        if len(words) >= 5:
            blocks.append(b)
    return blocks


def parse_fragment(text: str, sid: str) -> dict[str, Any]:
    # equation anchors: any \label inside a display-mathematics environment
    # (the house convention labels equations by their owning node's id, so no
    # prefix filter — eq:/thm:/ds:/irf: all anchor)
    eq_labels = [lab for m in _ENV_RE.finditer(text)
                 if m.group(1).startswith(("equation", "align"))
                 for lab in re.findall(r"\\label\{([^}]+)\}", m.group(0))]
    return {
        "section_id": sid,
        "headings": re.findall(r"\\(?:part|chapter|(?:sub)*section)\*?\{([^}]+)\}", text),
        "paragraph_blocks": _fragment_blocks(text),
        "equation_labels": eq_labels,
        "figure_refs": sorted(set(re.findall(r"\\ref\{(fig:[^}]+)\}", text))),
        "citations": sorted({k.strip() for grp in re.findall(r"\\cite[tp]?\{([^}]+)\}", text)
                             for k in grp.split(",") if k.strip()}),
        "cross_refs": sorted(set(re.findall(
            r"\\(?:ref|eqref|autoref|cref|Cref)\{([^}]+)\}", text))),
        "nodes_marked": [nid for m in schema.NODES_MARKER_RE.finditer(text)
                         for nid in m.group(1).split()],
    }


def provenance_path(project: str, sid: str,
                    repo_root: Path | None = None) -> Path | None:
    proj = registry.resolve(project, repo_root=repo_root)
    base = proj.stage_path("provenance", repo_root) if proj else None
    return (base / f"{pathsafe.encode_sid_for_path(sid)}.json") if base else None


def _sidecar_records(p: Path | None, field: str, diagnostics: list[str] | None) -> list[dict] | None:
    """Keep malformed historical bytes at their owner; never infer a partial exact join."""
    if p is None or not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        records = data.get(field) if isinstance(data, dict) else data
        if not isinstance(records,list) or any(not isinstance(row,dict) for row in records):
            raise ValueError("records must be a list of objects")
        for row in records:
            if "spec_id" in row and not isinstance(row["spec_id"],str):
                raise ValueError("spec_id must be a string")
            for key in ("spec_ids","nodes_realised"):
                if key in row and (not isinstance(row[key],list) or any(not isinstance(value,str) for value in row[key])):
                    raise ValueError(key+" must be a list of strings")
        return records
    except (OSError, ValueError) as exc:
        if diagnostics is not None:diagnostics.append("Malformed or unavailable "+field+" sidecar "+p.name+": "+str(exc))
        return None


def load_provenance(project: str, sid: str,
                    repo_root: Path | None = None, *, diagnostics: list[str] | None = None) -> list[dict] | None:
    return _sidecar_records(provenance_path(project,sid,repo_root),"paragraphs",diagnostics)


def load_decisions(project: str, sid: str,
                   repo_root: Path | None = None, *, diagnostics: list[str] | None = None) -> list[dict] | None:
    """The weld's decision sidecar for a section (``decisions/<sid>.json``) — the
    forks a generating stage surfaced against a paragraph. Parallel to
    :func:`load_provenance`; absent until the weld has run (returns None)."""
    proj = registry.resolve(project, repo_root=repo_root)
    base = proj.stage_path("decisions", repo_root) if proj else None
    p = (base / f"{pathsafe.encode_sid_for_path(sid)}.json") if base else None
    return _sidecar_records(p,"decisions",diagnostics)


def _record_spec_ids(record: dict[str, Any]) -> list[str]:
    return [str(pid) for pid in (record.get("spec_ids") or [record.get("spec_id")]) if pid]


def _obligations(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    return list(value) if isinstance(value, (list, tuple, set)) else [value]


def build_document_model(project: str, repo_root: Path | None = None,
                         write: bool = True) -> dict[str, Any]:
    """Build from the selected edition's recursive ``\\input`` order."""
    proj = registry.resolve(project, repo_root=repo_root)
    if proj is None:
        return {"error": f"unknown project {project!r}"}
    from laplace.manuscript import manuscript_source
    selected = manuscript_source.resolve(project, repo_root=repo_root)
    if selected.get("status") in {"resolved", "empty"} and selected.get("root"):
        root_name = selected["root"]
    elif selected.get("status") == "ambiguous":
        return {"error": "ambiguous manuscript source", "source": selected}
    else:
        # Last-resort compatibility for a registry row with no source candidate.
        tex_dir = proj.resolved_target_dir(repo_root)
        main = (tex_dir / "main.tex") if tex_dir else None
        if main is None or not main.is_file():
            return {"error": "no resolved manuscript source", "source": selected}
        root = Path(repo_root) if repo_root is not None else registry._repo_root()
        try:
            root_name = main.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            root_name = str(main)
    tree = manuscript_source.traversal(root_name, repo_root=repo_root)

    # The \input arg is a PATH stem (the portable projection, e.g. ``sec_abstract``);
    # the TRUE sid (``sec:abstract``) lives in the plan. Resolve the id from the
    # plan by matching the stem through the encoder — NEVER decode a sid from the
    # filename (pathsafe rule 2). Fall back to the raw stem for a fragment the plan
    # doesn't name (a stray \input), which is already path-safe by construction.
    plan = proj.read_plan(repo_root) or {}
    stem_to_sid = {pathsafe.encode_sid_for_path(s): s
                   for s in (sec.get("id") for sec in schema.plan_sections(plan))
                   if s}

    sections = []
    for source in tree.get("sources", []):
        name = str(source.get("file") or "")
        sid = stem_to_sid.get(Path(name).stem, Path(name).stem)
        entry: dict[str, Any] = {"section_id": sid, "file": name, "exists": True,
                                 "order": source.get("order"), "parent": source.get("parent"),
                                 "include_line": source.get("include_line"),
                                 "span": {key: source.get(key) for key in
                                          ("line_start", "line_end", "byte_start", "byte_end")}}
        entry.update(parse_fragment(str(source.get("text") or ""), sid))
        prov = load_provenance(project, sid, repo_root)
        entry["provenance"] = prov if prov is not None else []
        sections.append(entry)

    model = {"project": project, "main": root_name, "source": selected,
             "input_order": [entry["file"] for entry in sections], "sections": sections,
             "includes": tree.get("includes", []), "diagnostics": tree.get("diagnostics", [])}
    if write and not selected.get("read_only"):
        out = proj.stage_path("document_model", repo_root)
        if out is not None:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(model, ensure_ascii=False, indent=1) + "\n",
                           encoding="utf-8")
    elif write and selected.get("read_only"):
        model["write_skipped"] = "selected source is foreign/read-only"
    return model


def validate_fidelity(project: str, sid: str,
                      repo_root: Path | None = None) -> dict[str, Any]:
    """§11.4 — the rendered fragment against its narrative specification:

    - a provenance sidecar exists and every paragraph plan id appears in it;
      merged paragraphs carry several ids and split plans may repeat an id;
    - every provenance record resolves to a rendered prose block (a plan never
      silently vanishes, while the writer remains free to merge or split);
    - every citation in the fragment is carried by the packet (contract refs);
    - every equation anchor named by a plan appears in the fragment;
    - the ``% NODES`` markers cover every input node the plans name.
    """
    proj = registry.resolve(project, repo_root=repo_root)
    if proj is None:
        return {"pass": None, "error": f"unknown project {project!r}"}
    packet = narrative.narrative_packet(project, sid, repo_root)
    if packet is None:
        return {"pass": False, "error": f"no narrative packet for {sid}"}
    tex_dir = proj.resolved_target_dir(repo_root)
    frag = (tex_dir / f"{pathsafe.encode_sid_for_path(sid)}.tex") if tex_dir else None
    if frag is None or not frag.is_file():
        return {"pass": False, "missing": f"{pathsafe.encode_sid_for_path(sid)}.tex"}
    fragment_text = frag.read_text(encoding="utf-8", errors="replace")
    parsed = parse_fragment(fragment_text, sid)
    prov = load_provenance(project, sid, repo_root)

    issues: list[dict[str, str]] = []
    plans = packet["paragraphs"]
    plan_ids = [p.get("paragraph_id") for p in plans]
    if prov is None:
        issues.append({"where": sid, "issue": "no prose-provenance sidecar"})
        realised = []
    else:
        realised = [pid for record in prov for pid in _record_spec_ids(record)]
        from laplace.manuscript import projection_viewer
        marker_groups = [span.get("spec_ids") or []
                         for span in projection_viewer.parse_paragraphs(fragment_text)]
        provenance_groups = [_record_spec_ids(record) for record in prov]
        if marker_groups != provenance_groups:
            issues.append({
                "where": sid,
                "issue": "fragment paragraph markers differ from provenance records",
            })
        for pid in plan_ids:
            n = realised.count(pid)
            if n == 0:
                issues.append({"where": pid, "issue": "paragraph plan not realised"})
        for record in prov:
            spec_ids = _record_spec_ids(record)
            if not spec_ids:
                issues.append({"where": sid, "issue": "provenance paragraph has no plan id"})
            elif record.get("spec_id") and record["spec_id"] != spec_ids[0]:
                issues.append({"where": record["spec_id"],
                               "issue": "primary spec_id differs from first spec_ids entry"})
            for pid in spec_ids:
                if pid not in set(plan_ids):
                    issues.append({"where": pid, "issue": "unknown paragraph plan id"})

        records_by_plan = {
            pid: [record for record in prov if pid in _record_spec_ids(record)]
            for pid in plan_ids
        }
        for plan in plans:
            pid = plan.get("paragraph_id")
            records = records_by_plan.get(pid, [])
            nodes = {node for record in records for node in (record.get("nodes_realised") or [])}
            equations = {eq for record in records for eq in (record.get("equations") or [])}
            qualifications = [item for record in records
                              for item in (record.get("qualifications") or [])]
            citations = {cite for record in records for cite in (record.get("citations") or [])}
            for node in plan.get("input_nodes") or []:
                if node not in nodes:
                    issues.append({"where": pid, "issue": f"input node {node!r} absent from provenance"})
            anchor = plan.get("equation_anchor")
            if anchor and anchor not in equations:
                issues.append({"where": pid, "issue": f"equation anchor {anchor!r} absent from provenance"})
            for qualification in _obligations(plan.get("qualification")):
                if qualification not in qualifications:
                    issues.append({"where": pid, "issue": "required qualification absent from provenance"})
            for citation in _obligations(plan.get("citations")):
                if citation not in citations:
                    issues.append({"where": pid, "issue": f"required citation {citation!r} absent from provenance"})

    if prov is not None and len(parsed["paragraph_blocks"]) < len(prov):
        issues.append({"where": sid,
                       "issue": f"{len(parsed['paragraph_blocks'])} prose blocks "
                                f"for {len(prov)} provenance records"})

    allowed_cites = set(packet["citations"])
    for key in parsed["citations"]:
        if key not in allowed_cites:
            issues.append({"where": sid, "issue": f"citation {key!r} not carried "
                                                  "by the plan section's refs"})

    frag_eqs = set(parsed["equation_labels"]) | set(parsed["cross_refs"])
    for p in plans:
        anchor = p.get("equation_anchor")
        if anchor and anchor not in frag_eqs:
            issues.append({"where": p.get("paragraph_id"),
                           "issue": f"equation anchor {anchor!r} absent from fragment"})

    marked = set(parsed["nodes_marked"])
    wanted = {nid for p in plans for nid in (p.get("input_nodes") or [])}
    for nid in sorted(wanted - marked):
        issues.append({"where": sid, "issue": f"% NODES markers missing {nid}"})

    return {"pass": not issues, "section": sid, "issues": issues,
            "plans": len(plans), "blocks": len(parsed["paragraph_blocks"])}
