#!/usr/bin/env python3
"""resolve_paragraph_sections.py — the paragraph section-membership resolve (the named honest gap).

The inherited ``paragraph_plan`` store carries his real paragraph prose + its char-span provenance,
but the 8 sonnet readers noted that many rows' ``span_ref.section_label`` was synthesized or missing
(the inherited chunker works in ``strip_latex`` offset space, which does not carry section
boundaries). This closes that gap MECHANICALLY, additively, and only where it can be done
UNAMBIGUOUSLY:

  * build each paper's full-fidelity conceptric through the SAME section bridge the four-lens stage
    uses (``pipeline.section_bridge.bridged_network``) — so the section node ids are exactly the
    ones the section_architecture store already uses;
  * reconstruct each section's FULL (untruncated) prose with the bridge's own ``strip_latex`` +
    whitespace-normalisation, keyed by the net's own section ids;
  * for each paragraph row, probe its normalised ``embed_text`` (a start slice, then a mid slice)
    as a SUBSTRING into every section's full prose. If EXACTLY ONE section contains the probe, the
    row resolves — write the section's conceptric node id as ``span_ref.section_node`` (a NEW,
    ADDITIVE field; the readers' ``section_label`` is NEVER overwritten). Zero or ambiguous matches
    stay UNRESOLVED and are counted honestly.

BYTE-PRESERVATION IS MECHANICAL. A resolved row is re-serialised with the SAME ``json.dumps(...,
ensure_ascii=False)`` the store was written with (verified byte-stable across all 260 rows), so the
ONLY byte change is the appended ``section_node`` field. An unresolved row is written back
VERBATIM (its original line), so it is byte-identical. The merged ``_index.json`` gains the same
additive field on its matching rows (its ``indent=2`` serialisation is likewise byte-stable);
nothing else in the store is touched (``embeddings.json`` / ``_role_taxonomy.json`` /
``gate_verdict.json`` / the caveats + defective_rows are untouched).

Papers the bridge cannot lift (``polaron-imposters``, ``superoscillations`` — no inline ``\\section``)
have no section prose to match into, so every one of their rows stays unresolved, reported by name.

Usage:
    .venv/bin/python scripts/resolve_paragraph_sections.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from laplace.engine.voice_corpus_ingest import strip_latex  # noqa: E402
from laplace.pipeline.section_bridge import SectionBridgeError, bridged_network  # noqa: E402

CENSUS = _REPO_ROOT / "corpus_friction" / "stage_corpus_census.json"
PP_DIR = _REPO_ROOT / "corpus_stores" / "paragraph_plan"

# the bridge's own section-split regexes (matched here so the reconstructed prose keys the net's ids)
_SEC_RX = re.compile(r"(?m)^\s*\\section\*?\s*\{")
_LABEL_RX = re.compile(r"\\label\{([^}]+)\}")
_INPUT_RX = re.compile(r"\\input\{([^}]+)\}")
_COMMENT_RX = re.compile(r"(?<!\\)%.*")


def _sid_of_block(block: str, stem: str) -> str:
    """The section id the atomiser/bridge mint for a ``\\section`` block: its first ``sec:`` label,
    else ``sec:<stem>`` — the exact rule ``section_bridge._section_enrichment`` uses, so the id
    matches the net's own section node id."""
    lab = next((l for l in _LABEL_RX.findall(block) if l.startswith("sec:")), None)
    return lab or f"sec:{stem}"


def _full_section_prose(tex_path: Path, net: dict[str, Any]) -> dict[str, str]:
    """Reconstruct each section's FULL (untruncated) normalised prose, keyed by the net's own
    section node ids. Handles both bridge paths: inline ``\\section`` (split the document body) and
    ``\\input`` pass-through (read each section file in place). Only sids present as section nodes in
    ``net`` are kept (a mechanical cross-validation against the conceptric)."""
    sec_nodes = {nid for nid, n in net["nodes"].items() if n.get("kind") == "section"}
    text = tex_path.read_text(encoding="utf-8", errors="ignore")
    out: dict[str, str] = {}

    if not net.get("bridged", True):
        # pass-through: sections live in \input'd files
        src_dir = tex_path.parent
        stripped = _COMMENT_RX.sub("", text)
        for inc in _INPUT_RX.findall(stripped):
            path = src_dir / inc
            if path.suffix != ".tex":
                path = path.with_suffix(".tex")
            if not path.is_file():
                continue
            block = path.read_text(encoding="utf-8", errors="ignore")
            if not _SEC_RX.search(block):
                continue
            sid = _sid_of_block(block, path.stem)
            if sid in sec_nodes:
                out[sid] = " ".join(strip_latex(block).split())
        return out

    # inline: split the document body on \section starts (the bridge's own split)
    m = re.search(r"\\begin\{document\}", text)
    doc_start = m.end() if m else 0
    doc_end = text.find(r"\end{document}")
    body = text[doc_start:(doc_end if doc_end != -1 else len(text))]
    starts = [mm.start() for mm in _SEC_RX.finditer(body)]
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else len(body)
        block = body[s:e]
        sid = _sid_of_block(block, f"sec{i:02d}")
        if sid in sec_nodes:
            out[sid] = " ".join(strip_latex(block).split())
    return out


def _resolve(embed_text: str, sections: dict[str, str]) -> str | None:
    """Resolve one paragraph's containing section, or ``None`` when the match is not UNAMBIGUOUS.
    Probe a distinctive slice of the normalised paragraph as a substring of each section's full
    prose: the start (up to 400 chars) first, then a mid slice (300 chars) as a fallback for a
    paragraph whose head straddles a strip-normalisation boundary. A probe resolves iff EXACTLY ONE
    section contains it."""
    p = " ".join((embed_text or "").split())
    if not p or not sections:
        return None
    probes = []
    probes.append(p if len(p) <= 400 else p[:400])
    if len(p) > 200:
        mid = p[len(p) // 3: len(p) // 3 + 300]
        if mid:
            probes.append(mid)
    for probe in probes:
        cands = [sid for sid, txt in sections.items() if probe in txt]
        if len(cands) == 1:
            return cands[0]
    return None


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

    census = json.loads(CENSUS.read_text(encoding="utf-8"))
    tex_of = {e["paper_id"]: _REPO_ROOT / e["tex_files"][0] for e in census["papers_tex"]}

    pp_papers = sorted(p.stem for p in PP_DIR.glob("*.jsonl"))
    print(f"# resolve_paragraph_sections — section-membership over {len(pp_papers)} paragraph_plan papers")

    resolved_by_row: dict[str, str] = {}      # row_id -> section_node (across all papers)
    per_paper: list[dict[str, Any]] = []

    for pid in pp_papers:
        jsonl = PP_DIR / f"{pid}.jsonl"
        lines = [ln for ln in jsonl.read_text(encoding="utf-8").splitlines() if ln.strip()]
        rows = [json.loads(ln) for ln in lines]

        tex_path = tex_of.get(pid)
        sections: dict[str, str] = {}
        bridge_status = "bridged"
        if tex_path is None or not tex_path.is_file():
            bridge_status = "no-tex-in-census"
        else:
            try:
                net = bridged_network(tex_path, pid)
                sections = _full_section_prose(tex_path, net)
            except SectionBridgeError as e:
                bridge_status = f"unbridgeable: {e}"

        out_lines: list[str] = []
        n_res = n_un = 0
        for raw, row in zip(lines, rows):
            sid = _resolve(row.get("embed_text", ""), sections) if sections else None
            if sid is None:
                out_lines.append(raw)                    # byte-identical: unresolved stays untouched
                n_un += 1
            else:
                row["provenance"].setdefault("span_ref", {})
                # ADDITIVE: append section_node; NEVER overwrite the readers' section_label
                row["provenance"]["span_ref"]["section_node"] = sid
                out_lines.append(json.dumps(row, ensure_ascii=False))
                resolved_by_row[row["row_id"]] = sid
                n_res += 1

        jsonl.write_text("".join(ln + "\n" for ln in out_lines), encoding="utf-8")
        per_paper.append({"paper_id": pid, "rows": len(rows), "resolved": n_res,
                          "unresolved": n_un, "sections_in_net": len(sections),
                          "bridge": bridge_status})
        print(f"  {pid:<42} rows={len(rows):<3} resolved={n_res:<3} unresolved={n_un:<3} "
              f"sections={len(sections):<2} [{bridge_status.split(':')[0]}]")

    # update the merged _index.json ADDITIVELY (indent=2 serialisation is byte-stable)
    index_path = PP_DIR / "_index.json"
    index_updated = 0
    if index_path.is_file():
        idx = json.loads(index_path.read_text(encoding="utf-8"))
        for r in idx.get("rows", []):
            sid = resolved_by_row.get(r.get("row_id"))
            if sid is not None:
                r.setdefault("provenance", {}).setdefault("span_ref", {})["section_node"] = sid
                index_updated += 1
        index_path.write_text(json.dumps(idx, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    total_rows = sum(p["rows"] for p in per_paper)
    total_res = sum(p["resolved"] for p in per_paper)
    total_un = sum(p["unresolved"] for p in per_paper)
    verdict = {
        "schema": "paragraph-section-membership-resolve/0.1",
        "method": ("mechanical substring of the normalised paragraph (start<=400 then mid 300) into "
                   "the bridged net's full per-section prose; resolve iff exactly one section "
                   "contains the probe — else UNRESOLVED"),
        "field_added": "provenance.span_ref.section_node (the conceptric section node id; ADDITIVE, "
                       "never overwrites the readers' section_label)",
        "papers": len(per_paper),
        "rows_total": total_rows,
        "resolved": total_res,
        "unresolved": total_un,
        "resolve_rate": round(total_res / total_rows, 4) if total_rows else 0.0,
        "index_rows_updated": index_updated,
        "per_paper": per_paper,
    }
    (PP_DIR / "section_membership_resolve.json").write_text(
        json.dumps(verdict, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("\n# ===== SECTION-MEMBERSHIP RESOLVE SUMMARY =====")
    print(json.dumps({"rows_total": total_rows, "resolved": total_res, "unresolved": total_un,
                      "resolve_rate": verdict["resolve_rate"],
                      "index_rows_updated": index_updated}, indent=2))
    print(f"\nwrote: corpus_stores/paragraph_plan/section_membership_resolve.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
