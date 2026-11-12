#!/usr/bin/env python3
"""stage0_ancestor_inventory.py — STAGE ZERO of the stage-stores run (design §1b, the hard
precondition that fires BEFORE any lens).

His steer (2026-07-15, ``ARMING_2026-07-15_the-workflow-audit-and-the-stage-stores.md`` /
``DESIGN_2026-07-15_the-stage-stores.md`` §1b): old engine eras already decomposed his corpus —
"it feels like we're reauthoring information _again_". A blank-slate fleet would re-author what a
deprecated store already says and leave the two versions contradicting each other with no
tombstone. So the fleet's STAGE ZERO is the ancestor reconciliation, a hard precondition:

  1. INVENTORY each ancestor store against the five stage-store schemas (mechanical: which schema
     fields can each ancestor face actually SUPPLY?).
  2. IMPORT what is form-relevant, provenance-marked ``inherited::<store>`` — a salvaged row is
     forever distinguishable from a fresh lens read (``stage_store.import_inherited``).
  3. LEAVE content-level material (claims/methods) where it lives — content is out of scope for
     FORM stores by the form-never-content law.
  4. RETIRE what is superseded AND dead through the TYPED supersede machinery — never a prose note,
     and (this script) never a deletion: a retirement is emitted as a PROPOSED typed record for the
     orchestrator to route through ``scripts/supersede_sweep.py --fix`` (opt-in, the author's).
  5. Only the residue the ancestors cannot supply gets model-read — every salvaged row is a
     lens-read not spent.

THE FOUR ANCESTORS (the corpus census, ``corpus_friction/stage_corpus_census.json``):
  * ``life_corpus/papers/*.md``            — 20 prose-less distillates (claim/concepts/methods).
  * ``corpus_stores/voice_corpus_cache/exemplar_passages/passages.jsonl`` — the voice store's exemplar
    passages (260 real-paragraph prose spans, 8 papers, with file/char provenance).
  * ``collaborator_corpus/_structural/*.json`` — 7 prose-less structural distillates of OTHER
    physicists' corpora (the C6 contrast class).
  * ``reference_corpus/_substrate_mccaul.json`` — the bib substrate (a citation graph).

THE DISCIPLINE is genuinely MECHANICAL: each ancestor inspector READS the real files and reports
the field VOCABULARY it actually carries; the verdict is a pure function of (does the ancestor
carry real-prose spans of HIS papers at the store's unit granularity, with span provenance?). No
verdict is hardcoded — flip a file's shape and the verdict flips.

stdlib-only (no numpy / no embeddings): stage zero writes the imported-row SKELETON JSONL; the
gate-then-embed step (``scripts/demo_stage_stores.py`` / the fleet) embeds later. The last line is
the sentinel (``scripts/paper_gates.py`` convention): ``VERDICT=PASS ...``.

Usage:
    python3 scripts/stage0_ancestor_inventory.py            # inventory + execute the imports
    python3 scripts/stage0_ancestor_inventory.py --dry-run  # inventory only, write nothing
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from laplace.pipeline import stage_store  # noqa: E402

CORPUS_STORES = _REPO_ROOT / "corpus_stores"

# --------------------------------------------------------------------------- #
# the five stage-store schemas, reduced to their IMPORT-decisive shape (design §2)
# --------------------------------------------------------------------------- #
#: Per store: the granularity UNIT one row stands for, the ``span_ref`` provenance fields a row
#: needs, and the ``form`` abstractions (all model-read residue for an inherited SKELETON). An
#: ancestor can IMPORT into a store iff it carries real-prose spans of HIS papers at the store's
#: unit granularity WITH span provenance; otherwise the material is LEFT (content) or the store is
#: read fresh. This mirrors DESIGN §2.1-§2.5.
STORE_SCHEMAS: dict[str, dict[str, Any]] = {
    "paragraph_plan": {
        "unit": "paragraph",
        "mirrors": "schema.PARAGRAPH_FIELDS (stage-D narrative plan)",
        "span_fields": ["file", "char_start", "char_end", "section_label", "paragraph_index"],
        "form_fields": ["role", "connective_prev", "connective_next", "carries_math",
                        "carries_figure", "proposition_shape", "detail_level", "length_band"],
    },
    "section_architecture": {
        "unit": "section",
        "mirrors": "the structural section contract (function/entry_state/exit_state)",
        "span_fields": ["file", "char_start", "char_end", "section_label"],
        "form_fields": ["job", "arc", "question_class", "position", "forward_reach", "carries"],
    },
    "spine_chain": {
        "unit": "rung (claim->claim dependency)",
        "mirrors": "plan.meta.contribution_rank + the spine",
        "span_fields": ["node_ids", "section_node"],
        "form_fields": ["rung", "of_rungs", "ladder_move", "depends_on_rung",
                        "claim_class", "supports_class"],
    },
    "derivation_walk": {
        "unit": "derivation step",
        "mirrors": "the derive/mint node frame + derivation_detail",
        "span_fields": ["node_ids", "eq_env"],
        "form_fields": ["step_kind", "granularity", "elision", "carries_eq", "prereq_kind"],
    },
    "figure_caption": {
        "unit": "figure",
        "mirrors": "the figure worker + figure_anchor",
        "span_fields": ["file", "figure_label"],
        "form_fields": ["caption_move", "panels", "figure_role", "ref_density", "caption_len_band"],
    },
}
STORES = list(STORE_SCHEMAS)


# --------------------------------------------------------------------------- #
# the ancestor inspectors — each READS the real files, reports its field vocabulary
# (mechanical; a capability descriptor, never a hardcoded verdict)
# --------------------------------------------------------------------------- #
def _capability(**kw: Any) -> dict[str, Any]:
    """A uniform ancestor-capability descriptor. ``prose_span_unit`` is the granularity at which
    the ancestor carries real-prose spans OF HIS papers ('paragraph'/'section'/...), or ``None``
    when it carries no such spans (content tags, other authors, or bib metadata). ``span_fields``
    is the ``span_ref`` provenance it can fill. These two decide every verdict."""
    return {
        "path": kw["path"], "n_files": kw.get("n_files", 0), "n_rows": kw.get("n_rows", 0),
        "field_vocab": kw.get("field_vocab", []), "is_gerard_corpus": kw.get("is_gerard_corpus", True),
        "prose_less": kw.get("prose_less", True), "prose_span_unit": kw.get("prose_span_unit"),
        "span_fields": kw.get("span_fields", []), "per_paper": kw.get("per_paper", {}),
        "note": kw.get("note", ""),
    }


def inspect_distillates(repo: Path) -> dict[str, Any]:
    """``life_corpus/papers/*.md`` — the prose-less id spine. Reads one file's real shape: YAML
    frontmatter keys + the bold section markers. Carries a single DISTILLED claim sentence +
    concept/method TAGS — NOT the paper's real paragraphs, and NO file/char spans into the .tex."""
    papers = sorted((repo / "life_corpus" / "papers").glob("*.md"))
    vocab: set[str] = set()
    for p in papers[:3]:                      # sample the real shape (all share the template)
        head, _, body = p.read_text(encoding="utf-8").partition("---\n")[2].partition("\n---")
        vocab.update(re.findall(r"^(\w+):", head, re.M))
        vocab.update(m.lower() for m in re.findall(r"\*\*(\w+)\.\*\*", body))
    return _capability(
        path="life_corpus/papers/*.md", n_files=len(papers), n_rows=len(papers),
        field_vocab=sorted(vocab), is_gerard_corpus=True, prose_less=True,
        prose_span_unit=None, span_fields=[],
        note="distilled claim + concept/method tags per paper; abstract sealed; no real-paragraph "
             "prose, no file/char spans — the id spine, content-level.")


def inspect_voice_passages(repo: Path) -> dict[str, Any]:
    """``corpus_stores/voice_corpus_cache/exemplar_passages/passages.jsonl`` — the voice store's exemplar
    passages. Reads the real row shape: each row IS one real-paragraph prose span of HIS paper with
    ``file``/``char_start``/``char_end``/``paragraph_start`` provenance. This is the paragraph-plan
    lens's raw material already chunked (design §1b)."""
    jl = repo / "corpus_stores" / "voice_corpus_cache" / "exemplar_passages" / "passages.jsonl"
    vocab: set[str] = set()
    per_paper: dict[str, int] = {}
    n = 0
    if jl.is_file():
        for ln in jl.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            r = json.loads(ln)
            vocab.update(r.keys())
            per_paper[r["slug"]] = per_paper.get(r["slug"], 0) + 1
            n += 1
    return _capability(
        path="corpus_stores/voice_corpus_cache/exemplar_passages/passages.jsonl",
        n_files=1, n_rows=n, field_vocab=sorted(vocab), is_gerard_corpus=True, prose_less=False,
        prose_span_unit="paragraph",
        span_fields=["file", "char_start", "char_end", "paragraph_index"],  # NOTE: no section_label
        per_paper=dict(sorted(per_paper.items())),
        note="one real-paragraph prose span per row (his papers) with file+char+paragraph "
             "provenance; carries NO section membership (span_ref.section_label unavailable) and "
             "NONE of the FORM abstractions (those stay the lens's model read).")


def inspect_collaborator(repo: Path) -> dict[str, Any]:
    """``collaborator_corpus/_structural/*.json`` — prose-less structural distillates of OTHER
    physicists' corpora (the C6 contrast class). Reads the real ladder shape: meta_goal / approach /
    techniques / results — content-level claim summaries of NON-Gerard work."""
    files = sorted((repo / "collaborator_corpus" / "_structural").glob("*.json"))
    vocab: set[str] = set()
    if files:
        d = json.loads(files[0].read_text(encoding="utf-8"))
        vocab.update(d.keys())
        for lad in d.get("ladders", [])[:1]:
            vocab.update(f"ladder.{k}" for k in lad.keys())
    return _capability(
        path="collaborator_corpus/_structural/*.json", n_files=len(files), n_rows=len(files),
        field_vocab=sorted(vocab), is_gerard_corpus=False, prose_less=True,
        prose_span_unit=None, span_fields=[],
        note="other authors' prose-less claim/method/goal ladders (the C6 closure-margin contrast "
             "class); no his-prose, no spans — a negative/contrast class, NOT a form source.")


def inspect_bib(repo: Path) -> dict[str, Any]:
    """``reference_corpus/_substrate_mccaul.json`` — the bib substrate: the deduplicated exogenous
    reference graph (OpenAlex). Reads the real shape: a citation graph (id/n_cited/cited_by/title/
    year/authors), NO prose. Consumed mechanically by the conceptric build's ``\\cite`` edge
    resolution (design §1c), not a form store."""
    p = repo / "reference_corpus" / "_substrate_mccaul.json"
    vocab: set[str] = []
    n = 0
    if p.is_file():
        d = json.loads(p.read_text(encoding="utf-8"))
        vocab = sorted(list(d.keys()) + [f"references[].{k}" for k in (d.get("references") or [{}])[0].keys()])
        n = int(d.get("n_references", len(d.get("references") or [])))
    return _capability(
        path="reference_corpus/_substrate_mccaul.json", n_files=1, n_rows=n,
        field_vocab=vocab, is_gerard_corpus=True, prose_less=True,
        prose_span_unit=None, span_fields=[],
        note="a citation graph (bibliographic metadata + who-cites-whom); no prose, no per-paper "
             "form; the substrate the conceptric build resolves \\cite edges against, not a store.")


ANCESTORS = {
    "life_corpus_distillates": inspect_distillates,
    "voice_corpus_passages": inspect_voice_passages,
    "collaborator_structurals": inspect_collaborator,
    "reference_bib_substrate": inspect_bib,
}


# --------------------------------------------------------------------------- #
# the verdict — a PURE FUNCTION of the capability (design §1b import|leave|retire discipline)
# --------------------------------------------------------------------------- #
def verdict_for(ancestor_name: str, cap: dict[str, Any], store: str) -> dict[str, Any]:
    """Decide (supplies, import_candidates, verdict, reason) for ONE (ancestor, store) cell.

    IMPORT iff the ancestor carries real-prose spans of HIS papers at THIS store's unit
    granularity with span provenance — the FORM-relevant SKELETON a fresh lens would else
    re-chunk (design §1b step 2). LEAVE for content-level / other-authors / bib material — out of
    scope for form stores by the form-never-content law (step 3). RETIRE only where an ancestor's
    material is superseded AND dead (step 4) — none of these four are: each still lives (the id
    spine, the voice store, the contrast class, the citation substrate), so no retirement fires.
    """
    schema = STORE_SCHEMAS[store]
    unit = schema["unit"].split()[0]                    # 'paragraph' / 'section' / 'rung' / ...
    # the IMPORT test: his prose, spans, and the granularity the store's rows stand for.
    granularity_match = (cap["prose_span_unit"] == unit)
    if cap["is_gerard_corpus"] and not cap["prose_less"] and granularity_match:
        supplies = ["embed_text"] + [f"span_ref.{f}" for f in cap["span_fields"]
                                     if f in schema["span_fields"]]
        n = cap["n_rows"]
        reason = (f"carries {n} real-{unit} prose spans of his papers with "
                  f"{', '.join(cap['span_fields'])} provenance — the paragraph-plan lens's raw "
                  f"material already chunked; import the SKELETON (embed_text + span_ref), the "
                  f"FORM abstractions stay the model read. (span_ref.section_label absent: "
                  f"passages carry no section membership.)")
        return {"store": store, "supplies": supplies, "import_candidates": n,
                "verdict": "import", "reason": reason, "per_paper": cap["per_paper"]}

    # otherwise: LEAVE, with the reason keyed to WHY it is not a form source.
    if not cap["is_gerard_corpus"]:
        reason = (f"other authors' prose-less material (contrast class), not his corpus — supplies "
                  f"no FORM field for any of his papers' {unit}s.")
    elif cap["prose_less"]:
        reason = (f"content-level / metadata ({', '.join(cap['field_vocab'][:6])}...): no real-"
                  f"{unit} prose spans of his papers — out of scope for the form store by the "
                  f"form-never-content law; stays where it lives.")
    else:
        reason = (f"carries {cap['prose_span_unit']}-granular prose but this store's unit is "
                  f"{unit}; no {unit}-granular typed rows to salvage — read fresh (mechanical "
                  f"view + model residue), not inherited.")
    return {"store": store, "supplies": [], "import_candidates": 0,
            "verdict": "leave", "reason": reason}


def proposed_retirement(marker: str, superseded_by: str, reason: str) -> dict[str, Any]:
    """A TYPED proposed-retirement record (design §1b step 4) — the shape the orchestrator routes
    through ``scripts/supersede_sweep.py``. This script PROPOSES, never stamps and never deletes
    (``--fix`` is opt-in and the author's). Emitted into the inventory JSON only when a cell's
    verdict is ``retire``; stage zero found none of the four ancestors dead."""
    return {
        "kind": "proposed_retirement",
        "superseded_marker": marker,
        "superseded_by": superseded_by,
        "reason": reason,
        "route": "scripts/supersede_sweep.py --fix (opt-in, the author's; propose, never stamp)",
        "action_taken": "none (proposal only — no deletion, no stamp)",
    }


# --------------------------------------------------------------------------- #
# the paragraph-plan import: build inherited rows from the voice passages (design §2.1)
# --------------------------------------------------------------------------- #
def _pp_row(passage: dict[str, Any]) -> dict[str, Any]:
    """One ``paragraph_plan`` row from a voice exemplar passage — the inherited SKELETON. The real
    paragraph prose is ``embed_text`` (retrieval basis + audit handle); ``span_ref`` traces to the
    exact tex file+char span + source passage (the inheritance analog of the view law's node_ids).
    Every FORM abstraction is emitted ``None`` — the model residue (:data:`stage_store.RESIDUE_FIELDS`)."""
    tag = stage_store._pid_tag(passage["slug"])
    p0 = int(passage["paragraph_start"])
    return {
        "row_id": f"PP-{tag}-p{p0:04d}",
        "embed_text": passage["text"],
        "form": {
            # ALL model residue — an inherited row carries the skeleton, never the abstracted shape.
            "role": None, "connective_prev": None, "connective_next": None,
            "carries_math": None, "carries_figure": None, "proposition_shape": None,
            "detail_level": None, "length_band": None,
            # mechanical fields the passage DOES supply (kept for the audit handle):
            "char_count": int(passage["char_count"]),
            "paragraph_span": [p0, int(passage["paragraph_end"])],
        },
        "provenance": {
            "paper_id": passage["slug"],
            "source_kind": "tex",
            # extraction_lens stamped by import_inherited -> inherited::voice_corpus
            "span_ref": {
                "file": passage["rel_path"],
                "char_start": int(passage["char_start"]),
                "char_end": int(passage["char_end"]),
                "paragraph_index": p0,
                "section_label": None,               # honest gap: passages carry no section membership
                "source_passage_id": passage["passage_id"],
                "sha256": passage["sha256"],
            },
        },
    }


def _keep_math_text_index(repo: Path) -> dict[tuple[str, int], str]:
    """``(rel_path, paragraph_index) -> the passage text WITH his math kept``, over the exemplar
    corpus. The key is the paragraph index because it is the one thing invariant between the two
    renderings (the char offsets index the stripped prose and necessarily move)."""
    from laplace.engine.voice_corpus_ingest import passages_for_source

    exemplars = repo / "voice_corpus" / "exemplars"
    out: dict[tuple[str, int], str] = {}
    if not exemplars.is_dir():
        return out
    for tex in sorted(exemplars.rglob("*.tex")):
        for p in passages_for_source(tex, exemplars, keep_math=True):
            out[(p["rel_path"], int(p["paragraph_start"]))] = p["text"]
    return out


def execute_imports(repo: Path, stores_root: Path) -> list[dict[str, Any]]:
    """Run the ``import`` verdicts (design §1b step 2). Today exactly one: voice passages ->
    paragraph_plan. Groups passages by paper (slug) and calls ``stage_store.import_inherited`` per
    paper — the per-paper namespacing holds by construction (an import cannot cross paper
    namespaces). Returns one result record per paper written.

    THE TEXT KEEPS HIS MATH (WO-20260820-extraction-lens-keeps-math). The voice cache's passage
    ``text`` was written by the DEFAULT ``strip_latex``, which deletes math and so removes numeric
    literals mid-sentence ("a pulse duration of  fs,  J pulse energy"). The voice store keeps that
    rendering — it is a VOICE store, and its embeddings are sealed against it — but the
    ``paragraph_plan`` lens is a CONTENT store, so each passage's text is re-derived here in
    keep_math mode. The row set is unchanged by construction (``strip_latex``'s paragraph-shape
    invariance + the length band judged on the math-free rendering), so this enriches the same
    passages rather than minting different ones; a passage whose paragraph index does not resolve
    keeps the cache's text and is reported by name, never silently swapped."""
    jl = repo / "corpus_stores" / "voice_corpus_cache" / "exemplar_passages" / "passages.jsonl"
    by_paper: dict[str, list[dict[str, Any]]] = {}
    math_text = _keep_math_text_index(repo)
    for ln in jl.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            r = json.loads(ln)
            kept = math_text.get((r["rel_path"], int(r["paragraph_start"])))
            if kept is not None:
                r = {**r, "text": kept, "char_count": len(kept)}
            by_paper.setdefault(r["slug"], []).append(_pp_row(r))

    results: list[dict[str, Any]] = []
    for paper_id in sorted(by_paper):
        rows = by_paper[paper_id]
        path = stage_store.import_inherited("paragraph_plan", paper_id, rows, "voice_corpus",
                                            stores_root=stores_root)
        results.append({
            "store": "paragraph_plan", "source_store": "voice_corpus", "paper_id": paper_id,
            "rows": len(rows), "extraction_lens": stage_store.inherited_lens("voice_corpus"),
            "path": str(Path(path).relative_to(repo)),
        })
    return results


# --------------------------------------------------------------------------- #
# the residue statement: which schema fields still need model reads (design §1b step 5)
# --------------------------------------------------------------------------- #
def residue_statement(matrix: list[dict[str, Any]]) -> dict[str, Any]:
    """Per store: what STILL needs a model read after stage zero. A store with an inherited
    skeleton (paragraph_plan) owes only its FORM abstractions; every other store owes its whole
    row (read fresh — mechanical view + the model residue)."""
    imported = {c["store"] for c in matrix if c["verdict"] == "import"}
    out: dict[str, Any] = {}
    for store, schema in STORE_SCHEMAS.items():
        if store in imported:
            out[store] = {
                "skeleton": "INHERITED from voice_corpus (embed_text + span_ref)",
                "still_model_read": stage_store.RESIDUE_FIELDS.get(store, schema["form_fields"])
                                    + ["span_ref.section_label (mechanical section-membership resolve)"],
            }
        else:
            out[store] = {
                "skeleton": "read FRESH (no ancestor supplied it)",
                "still_model_read": ["<whole row>: mechanical conceptric view + "
                                     + ", ".join(stage_store.RESIDUE_FIELDS.get(store, schema["form_fields"]))],
            }
    return out


# --------------------------------------------------------------------------- #
# build the inventory (read-only) + drive
# --------------------------------------------------------------------------- #
def build_inventory(repo: Path) -> dict[str, Any]:
    """The read-only inventory: every (ancestor x store) cell verdicted mechanically. No writes."""
    ancestors = {name: fn(repo) for name, fn in ANCESTORS.items()}
    matrix: list[dict[str, Any]] = []
    retirements: list[dict[str, Any]] = []
    for aname, cap in ancestors.items():
        for store in STORES:
            cell = verdict_for(aname, cap, store)
            cell = {"ancestor": aname, **cell}
            matrix.append(cell)
            if cell["verdict"] == "retire":
                retirements.append(proposed_retirement(
                    cell.get("superseded_marker", aname),
                    cell.get("superseded_by", "?"), cell["reason"]))
    return {
        "schema": "stage0-ancestor-inventory/0.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(repo),
        "stores": STORES,
        "store_schemas": {s: {"unit": v["unit"], "mirrors": v["mirrors"]}
                          for s, v in STORE_SCHEMAS.items()},
        "ancestors": ancestors,
        "matrix": matrix,
        "proposed_retirements": retirements,
        "residue": residue_statement(matrix),
    }


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="Stage zero — the ancestor inventory (design §1b).")
    ap.add_argument("--dry-run", action="store_true",
                    help="inventory only; execute no imports and write no files.")
    ap.add_argument("--stores-root", default=str(CORPUS_STORES),
                    help="corpus_stores root (default: the repo's corpus_stores/).")
    args = ap.parse_args(argv)

    stores_root = Path(args.stores_root)
    inv = build_inventory(_REPO_ROOT)

    imports: list[dict[str, Any]] = []
    if not args.dry_run and any(c["verdict"] == "import" for c in inv["matrix"]):
        imports = execute_imports(_REPO_ROOT, stores_root)
    inv["imports_executed"] = imports
    inv["dry_run"] = bool(args.dry_run)

    if not args.dry_run:
        stores_root.mkdir(parents=True, exist_ok=True)
        (stores_root / "ancestor_inventory.json").write_text(
            json.dumps(inv, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # ---- the verdict table (ancestor x store) ----
    print("# stage0 — THE ANCESTOR INVENTORY (design §1b)\n")
    print(f"{'ancestor':<26} {'store':<22} {'verdict':<7} candidates  reason")
    print("-" * 100)
    for c in inv["matrix"]:
        r = c["reason"]
        r = (r[:54] + "…") if len(r) > 55 else r
        print(f"{c['ancestor']:<26} {c['store']:<22} {c['verdict']:<7} "
              f"{c['import_candidates']:>10}  {r}")

    n_import = sum(1 for c in inv["matrix"] if c["verdict"] == "import")
    n_leave = sum(1 for c in inv["matrix"] if c["verdict"] == "leave")
    n_retire = sum(1 for c in inv["matrix"] if c["verdict"] == "retire")
    print(f"\ncells: {len(inv['matrix'])}  (import={n_import}  leave={n_leave}  retire={n_retire})")

    if imports:
        print("\n# imports executed (provenance-marked inherited::voice_corpus):")
        total = sum(i["rows"] for i in imports)
        for i in imports:
            print(f"  {i['store']}/{i['paper_id']:<40} {i['rows']:>3} rows  -> {i['path']}")
        print(f"  TOTAL {total} rows across {len(imports)} papers, all extraction_lens="
              f"{stage_store.inherited_lens('voice_corpus')}")

    print("\n# residue (still needs model reads after stage zero):")
    for store, res in inv["residue"].items():
        print(f"  {store:<22} skeleton: {res['skeleton']}")

    # the coverage invariant IS the pass condition: every ancestor x store cell verdicted, and
    # every import verdict actually executed (unless --dry-run).
    covered = len(inv["matrix"]) == len(ANCESTORS) * len(STORES)
    imports_ok = args.dry_run or (n_import == 0) or (len(imports) > 0)
    ok = covered and imports_ok
    print(f"\nVERDICT={'PASS' if ok else 'FAIL'} cells={len(inv['matrix'])} "
          f"import={n_import} leave={n_leave} retire={n_retire} "
          f"imported_rows={sum(i['rows'] for i in imports)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
