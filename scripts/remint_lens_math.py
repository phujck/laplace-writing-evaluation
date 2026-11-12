#!/usr/bin/env python3
"""remint_lens_math.py — RE-MINT the two stripped lenses' ``embed_text`` so it keeps his math.

WO-20260820-extraction-lens-keeps-math. The ``section_architecture`` and ``paragraph_plan`` lenses
wrote ``embed_text`` through the DEFAULT ``voice_corpus_ingest.strip_latex``, which deletes every
math span. That deletion removes numeric literals MID-SENTENCE and leaves the sentence
grammatical, so nothing signals the loss:

    stored:  "This has a pulse duration of  fs,  J pulse energy and a  kHz repetition rate"
    paper:   "This has a pulse duration of $190$ fs, $400\\,\\mu$J pulse energy and a $50$ kHz …"

The ``derivation_walk`` lens already keeps raw LaTeX and reads correctly; the two lenses now match
it (``strip_latex(..., keep_math=True)`` — see :func:`laplace.engine.voice_corpus_ingest.strip_latex`).

WHY IN PLACE, not a rebuild. Both stores carry MODEL RESIDUE folded in by the reader merges
(``arc`` / ``question_class`` / ``normalized_job`` on section_architecture; ``role`` /
``connective_*`` / ``proposition_shape`` on paragraph_plan). Re-running the corpus drivers would
mint fresh mechanical skeletons and DESTROY that residue. This re-mint therefore refreshes exactly
one field per row — ``embed_text`` — from the row's OWN provenance, and touches nothing else
except the provenance stamps that describe the text (``offset_basis`` / ``text_render``) and, for
paragraph_plan, the mechanical ``char_count`` the text's length defines.

THE TWO RESOLUTION PATHS (each is the row's own provenance, never a re-derivation of the store):

  * ``section_architecture`` — ``span_ref.{file,char_start,char_end}`` are RAW tex offsets (the
    section bridge stamps the document-body span), so the block is read back verbatim and passed
    through the bridge's own enrichment rule.
  * ``paragraph_plan`` — ``span_ref.{file,paragraph_index}``; the char offsets index the STRIPPED
    prose, so the paragraph INDEX is the stable key. ``strip_latex``'s paragraph-shape invariance
    (display math is a paragraph break under both modes) makes index N name the same paragraph
    with and without math, which is what makes this re-mint safe.

THE SAFETY GATE. Before writing anything, every row is re-derived in the OLD (math-free) mode and
required to reproduce the STORED ``embed_text`` byte-for-byte. A row that fails that check is not
the row this script thinks it is — it is REPORTED and SKIPPED, never overwritten. Nothing is
written unless the store's own text is reproducible from its own provenance.

Usage:
    .venv/bin/python scripts/remint_lens_math.py --dry-run     # report only
    .venv/bin/python scripts/remint_lens_math.py               # re-mint + re-embed
    .venv/bin/python scripts/remint_lens_math.py --no-embed    # re-mint, leave embeddings stale
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from laplace.engine import voice_corpus_ingest as vci  # noqa: E402
from laplace.pipeline import section_bridge  # noqa: E402

STORES_ROOT = _REPO_ROOT / "corpus_stores"

#: The provenance stamp naming the render an ``embed_text`` was produced by. A row without it was
#: written by the math-deleting default (the defect this work order names).
TEXT_RENDER = "strip_latex(keep_math=True)"
OFFSET_BASIS_KEEP_MATH = "strip_latex(voice_corpus_ingest, keep_math=True)"


# --------------------------------------------------------------------------- #
# section_architecture — raw-tex span -> the bridge's own enrichment rule
# --------------------------------------------------------------------------- #
def _sa_text(block: str, keep_math: bool) -> str:
    """The bridge's ``_section_enrichment`` text rule, both modes. The NEW text goes through the
    bridge's own ``_prose_window`` so the re-mint can never drift from what the lens writes next
    time; the OLD text reproduces the demo's raw-character slice, which is what the stored rows
    were written by and what the safety gate checks against."""
    prose = " ".join(vci.strip_latex(block, keep_math=keep_math).split())
    if keep_math:
        return section_bridge._prose_window(prose)
    return (prose[:600] + " ... " + prose[-600:]) if len(prose) > 1300 else prose


def remint_section_architecture(row: dict[str, Any], sources: dict[str, str]) -> tuple[str, str]:
    """(old_text, new_text) for one section_architecture row, read back from its raw-tex span."""
    sr = row["provenance"]["span_ref"]
    text = sources[sr["file"]]
    block = text[int(sr["char_start"]):int(sr["char_end"])]
    return _sa_text(block, False), _sa_text(block, True)


# --------------------------------------------------------------------------- #
# paragraph_plan — the paragraph INDEX is the stable key
# --------------------------------------------------------------------------- #
def _pp_index(tex_rel: str, keep_math: bool) -> dict[int, dict[str, Any]]:
    """paragraph_index -> the passage record, for one source file under one render mode."""
    tp = _REPO_ROOT / tex_rel
    passages = vci.passages_for_source(tp, _REPO_ROOT / "voice_corpus" / "exemplars",
                                       keep_math=keep_math)
    return {int(p["paragraph_start"]): p for p in passages}


def remint_paragraph_plan(row: dict[str, Any], old_idx: dict[str, dict[int, dict[str, Any]]],
                          new_idx: dict[str, dict[int, dict[str, Any]]]) -> tuple[str, str] | None:
    """(old_text, new_text) for one paragraph_plan row, or None when its paragraph index no longer
    resolves (reported, never guessed)."""
    sr = row["provenance"]["span_ref"]
    f, p = sr["file"], int(sr["paragraph_index"])
    o, n = old_idx[f].get(p), new_idx[f].get(p)
    if o is None or n is None:
        return None
    return o["text"], n["text"]


# --------------------------------------------------------------------------- #
# the re-mint
# --------------------------------------------------------------------------- #
def _load(path: Path) -> list[dict[str, Any]]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _write(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def remint_store(store: str, *, dry_run: bool) -> dict[str, Any]:
    store_dir = STORES_ROOT / store
    files = sorted(p for p in store_dir.glob("*.jsonl"))
    report: dict[str, Any] = {"store": store, "papers": [], "rows": 0, "changed": 0,
                              "unreproducible": [], "unresolved": []}

    # per-store source caches (a paper's tex is read/parsed once)
    raw: dict[str, str] = {}
    old_idx: dict[str, dict[int, dict[str, Any]]] = {}
    new_idx: dict[str, dict[int, dict[str, Any]]] = {}

    for path in files:
        rows = _load(path)
        changed = 0
        for row in rows:
            report["rows"] += 1
            sr = row.get("provenance", {}).get("span_ref") or {}
            f = sr.get("file")
            if not f or not (_REPO_ROOT / f).is_file():
                report["unresolved"].append({"row_id": row.get("row_id"), "why": f"no source: {f}"})
                continue

            if store == "section_architecture":
                if f not in raw:
                    raw[f] = (_REPO_ROOT / f).read_text(encoding="utf-8", errors="ignore")
                old_text, new_text = remint_section_architecture(row, raw)
            else:
                if f not in old_idx:
                    old_idx[f] = _pp_index(f, False)
                    new_idx[f] = _pp_index(f, True)
                pair = remint_paragraph_plan(row, old_idx, new_idx)
                if pair is None:
                    report["unresolved"].append(
                        {"row_id": row.get("row_id"), "why": "paragraph index does not resolve"})
                    continue
                old_text, new_text = pair

            # THE SAFETY GATE: the stored text must be reproducible from the row's own provenance.
            if row.get("embed_text") != old_text:
                report["unreproducible"].append({"row_id": row.get("row_id"), "file": f})
                continue

            if new_text != old_text:
                changed += 1
            row["embed_text"] = new_text
            prov_sr = row["provenance"]["span_ref"]
            prov_sr["text_render"] = TEXT_RENDER
            if store == "paragraph_plan":
                prov_sr["offset_basis"] = OFFSET_BASIS_KEEP_MATH
                prov_sr["ancestor_sha256"] = prov_sr.get("ancestor_sha256", prov_sr.get("sha256"))
                row["form"]["char_count"] = len(new_text)

        report["changed"] += changed
        report["papers"].append({"paper": path.stem, "rows": len(rows), "changed": changed})
        if not dry_run and not report["unreproducible"]:
            _write(path, rows)
    return report


def reembed(store: str) -> dict[str, Any]:
    """Re-embed the re-minted store — ``embed_text`` moved, so ``embeddings.json`` is stale by
    construction. Uses the SAME local ONNX backend the stores were built with."""
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    import demo_stage_stores as demo  # noqa: E402  (the one embedding path, reused verbatim)
    from laplace.representation.embed_router import get_backend  # noqa: E402

    backend = get_backend()
    if backend is None:
        return {"store": store, "embedded": False, "why": "no local embedding backend"}
    rows: list[dict[str, Any]] = []
    for p in sorted((STORES_ROOT / store).glob("*.jsonl")):
        rows.extend(_load(p))
    emb = demo.embed_store(store, rows, backend)
    return {"store": store, "embedded": True, "rows": len(rows), "vectors": len(emb)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="report only; write nothing")
    ap.add_argument("--no-embed", action="store_true", help="skip the re-embed")
    ap.add_argument("--stores", nargs="*",
                    default=["section_architecture", "paragraph_plan"])
    args = ap.parse_args()

    print(f"# remint_lens_math — keep the math ({'DRY RUN' if args.dry_run else 'WRITING'})")
    reports = []
    for store in args.stores:
        rep = remint_store(store, dry_run=args.dry_run)
        reports.append(rep)
        print(f"\n{store}: {rep['rows']} rows, {rep['changed']} changed "
              f"({len(rep['unreproducible'])} unreproducible, {len(rep['unresolved'])} unresolved)")
        for p in rep["papers"]:
            print(f"  {p['paper']:<58} {p['changed']:>4}/{p['rows']}")
        for u in rep["unreproducible"][:10]:
            print(f"  ! UNREPRODUCIBLE {u['row_id']} ({u['file']})")
        for u in rep["unresolved"][:10]:
            print(f"  ! UNRESOLVED {u['row_id']}: {u['why']}")

    if not args.dry_run and not args.no_embed:
        for store in args.stores:
            print("\n" + json.dumps(reembed(store)))
    return 1 if any(r["unreproducible"] for r in reports) else 0


if __name__ == "__main__":
    raise SystemExit(main())
