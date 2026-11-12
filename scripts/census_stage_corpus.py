#!/usr/bin/env python3
"""census_stage_corpus.py — the mechanical corpus census for the STAGE-STORES arming.

The stage-stores design (DESIGN_2026-07-15_the-stage-stores.md) proposes decomposing
the author's PUBLISHED corpus through the pipeline's own intermediate representations
(five FORM lenses). Before the lensing fleet can fire, the design needs a MEASURED
census of what corpus actually exists in THIS repo/container — not the prose of the
arming ("~25 papers PDF, tex for a solid subset, + the physics corpus"), but the
counts on disk. View = mechanism: this script IS the census, and its JSON output is
the artefact the design's §(e)-(f) economics and demo-paper pick are derived from.

Four corpus faces, enumerated honestly:

  1. papers_tex   — the author's published papers WITH committed prose
                    (``voice_corpus/exemplars/<slug>/*.tex``). The ONLY face with
                    extractable prose today, so the ONLY face the five FORM lenses can
                    read now. Per paper: section / subsection / figure / equation /
                    paragraph counts (the structural-richness signal the demo pick uses).
  2. papers_pdf   — the 25 published PDFs (``my_papers.zip``), documented reference-only
                    in ``voice_corpus/exemplars/MANIFEST.md`` and NOT committed. Searched
                    for on disk and reported honestly (present vs documented). The
                    engine's OWN generated papers (paper_*/manuscript/main.pdf) are
                    explicitly NOT counted here — they are pipeline OUTPUT, not his
                    referee-validated PUBLISHED corpus.
  3. distillates  — ``life_corpus/papers/<slug>.md``: the prose-less metadata trace
                    (claim / concepts / methods; raw abstract sealed) of his published
                    corpus. The id spine that DOES travel; useful for the section /
                    spine ID layer, but carries no prose to lens.
  4. physics_corpus — ``collaborator_corpus/`` (7 collaborator author-corpora as
                    structural JSON) + ``reference_corpus/_substrate_mccaul.json``. The
                    prose-less structural distillates used as the C6 closure-margin
                    contrast class — NOT a form-exemplar source (no prose).

Stdlib only (no numpy, no third-party): the census must run on any clone, cold, with
no venv. Writes ``corpus_friction/stage_corpus_census.json`` and prints a summary.

Usage:
    python3 scripts/census_stage_corpus.py [--repo-root DIR] [--out PATH] [--quiet]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "stage-corpus-census/0.1"

_REPO_ROOT = Path(__file__).resolve().parents[1]

# --------------------------------------------------------------------------- #
# structural counters (crude by design — a signal, not a parser)
# --------------------------------------------------------------------------- #
_SECTION = re.compile(r"\\section\s*\{")
_SECTION_STAR = re.compile(r"\\section\s*\*\s*\{")
_SUBSECTION = re.compile(r"\\subsection\s*\{")
_FIGURE = re.compile(r"\\begin\s*\{figure\*?\}")
_EQUATION = re.compile(r"\\begin\s*\{(?:equation|align|gather|multline|eqnarray)\*?\}")


def _count(pat: re.Pattern[str], text: str) -> int:
    return len(pat.findall(text))


def _body(text: str) -> str:
    """The document body (between \\begin{document} and \\end{document}) when delimited,
    else the whole text. Bibliography tail cut. Mirrors voice_corpus_ingest.strip_latex's
    body isolation so the paragraph proxy sees prose, not preamble."""
    m = re.search(r"\\begin\{document\}", text)
    if m:
        text = text[m.end():]
    text = re.split(r"\\end\{document\}", text, maxsplit=1)[0]
    text = re.split(r"\\begin\{thebibliography\}|\\bibliography\b", text, maxsplit=1)[0]
    return text


def _paragraph_estimate(text: str) -> int:
    """A rough paragraph count: blank-line-separated blocks in the body that read as
    prose (>= 120 chars, not opening with a backslash-command). A PROXY for the
    paragraph-plan lens's expected row yield, not an exact figure — the real extraction
    is a model read, this is the mechanical floor."""
    body = _body(text)
    # drop full-line comments so they don't fragment blocks
    body = re.sub(r"(?m)^\s*%.*$", "", body)
    n = 0
    for block in re.split(r"\n\s*\n", body):
        b = " ".join(block.split())
        if len(b) >= 120 and not b.startswith("\\"):
            n += 1
    return n


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


# --------------------------------------------------------------------------- #
# face 1 — papers_tex (the extractable prose corpus)
# --------------------------------------------------------------------------- #
def _census_tex_dir(slug_dir: Path, source_kind: str, root: Path) -> dict[str, Any] | None:
    """One census record for a single paper's tex directory, or None if it holds no
    *.tex files. Shared by both sanctioned tex homes (see census_papers_tex)."""
    tex_files = sorted(slug_dir.rglob("*.tex"))
    if not tex_files:
        return None
    agg = {"bytes": 0, "sections": 0, "section_stars": 0, "subsections": 0,
           "figures": 0, "equations": 0, "paragraphs_est": 0}
    for tf in tex_files:
        text = tf.read_text(encoding="utf-8", errors="replace")
        # _SECTION (\section{) does NOT match \section*{ (the * sits before the
        # brace), so numbered and starred are counted independently — never
        # subtract one from the other. sections = numbered + starred boundaries.
        numbered = _count(_SECTION, text)
        starred = _count(_SECTION_STAR, text)
        agg["bytes"] += len(text.encode("utf-8"))
        agg["sections"] += numbered + starred
        agg["section_stars"] += starred
        agg["subsections"] += _count(_SUBSECTION, text)
        agg["figures"] += _count(_FIGURE, text)
        agg["equations"] += _count(_EQUATION, text)
        agg["paragraphs_est"] += _paragraph_estimate(text)
    # richness = the sum of the structural signals, one per FORM lens:
    # (sections+subsections)=section-architecture, figures=figure/caption,
    # equations=derivation-walk, paragraphs=paragraph-plan. Equal weight, so no
    # single lens dominates the demo pick; reproducible from this script.
    richness = (agg["sections"] + agg["subsections"] + agg["figures"]
                + agg["equations"] + agg["paragraphs_est"])
    return {
        "paper_id": slug_dir.name,
        "source_kind": source_kind,
        "tex_files": [_rel(tf, root) for tf in tex_files],
        **agg,
        "richness": richness,
    }


def census_papers_tex(root: Path) -> list[dict[str, Any]]:
    """One record per paper across BOTH sanctioned tex homes:

      - voice_corpus/exemplars/<slug>/  — his own supplied sources, ``source_kind: tex``
      - published_corpus/tex/<paper_id>/ — arXiv e-print sources fetched by
        scripts/acquire_paper_tex.py (DESIGN_2026-07-15_the-stage-stores.md §1c-a),
        ``source_kind: arxiv``

    A paper's tex files are ALL *.tex under its dir (superoscillations = main.tex +
    supplement.tex → one paper). paper_id is the immediate sub-directory name in
    either home; the two homes are disjoint by construction (acquire_paper_tex.py
    fuzzy-dedupes against voice_corpus/exemplars titles before ever writing a
    published_corpus/tex/ directory), so a paper_id collision here would itself be a
    signal worth surfacing rather than silently merging — the later (published_corpus)
    record wins if a clone somehow has one anyway, since dict insertion order below
    always lists voice_corpus first."""
    papers: dict[str, dict[str, Any]] = {}
    homes = [
        (root / "voice_corpus" / "exemplars", "tex"),
        (root / "published_corpus" / "tex", "arxiv"),
    ]
    for home_dir, source_kind in homes:
        if not home_dir.is_dir():
            continue
        for slug_dir in sorted(p for p in home_dir.iterdir() if p.is_dir()):
            record = _census_tex_dir(slug_dir, source_kind, root)
            if record is not None:
                papers[record["paper_id"]] = record
    return [papers[pid] for pid in sorted(papers)]


# --------------------------------------------------------------------------- #
# face 2 — papers_pdf (his published PDFs; documented reference-only)
# --------------------------------------------------------------------------- #
def census_papers_pdf(root: Path) -> dict[str, Any]:
    """The 25 published PDFs (my_papers.zip): documented in MANIFEST.md, kept
    reference-only, NOT committed. Search plausible traveled-cache locations and report
    honestly. The engine's OWN generated PDFs (paper_*/…/main.pdf) are EXCLUDED — they
    are pipeline output, not his published corpus."""
    documented = 25  # voice_corpus/exemplars/MANIFEST.md: "25 published PDFs"
    # plausible locations a "traveled PDF cache" of his published papers might live
    candidates: list[Path] = []
    # published_corpus/pdfs is THE home (his ruling, 2026-07-15: corpus material never
    # lives inside a tool's dot-directory — .codex is the Codex CLI's config dir; the
    # legacy paths stay searched so a stale checkout still censuses honestly).
    for sub in ("published_corpus/pdfs", "voice_corpus/published_pdfs", "voice_corpus/papers",
                ".codex/published_pdfs", ".codex/my_papers", "life_corpus/pdfs"):
        d = root / sub
        if d.is_dir():
            candidates.extend(sorted(d.rglob("*.pdf")))
    # any my_papers.zip archive on disk
    zips = [p for p in root.rglob("my_papers*.zip")
            if ".git" not in p.parts]
    present = [_rel(p, root) for p in candidates]
    return {
        "documented_reference_only": documented,
        "present_on_disk": len(present),
        "present_paths": present,
        "archive_present": [_rel(z, root) for z in zips],
        "note": ("my_papers.zip (25 published PDFs, ~30 MB) is documented reference-only "
                 "in voice_corpus/exemplars/MANIFEST.md and NOT committed; it does not "
                 "travel. The engine's own generated PDFs (paper_*/manuscript/main.pdf) "
                 "are pipeline OUTPUT, not the referee-validated PUBLISHED corpus, and "
                 "are excluded from this count. Until the PDFs are supplied+committed (or "
                 "PDF-text-extracted), the extractable corpus is papers_tex only."),
    }


# --------------------------------------------------------------------------- #
# face 3 — distillates (prose-less metadata trace; the id spine)
# --------------------------------------------------------------------------- #
def census_distillates(root: Path) -> list[dict[str, Any]]:
    d = root / "life_corpus" / "papers"
    out: list[dict[str, Any]] = []
    if not d.is_dir():
        return out
    for md in sorted(d.glob("*.md")):
        out.append({"slug": md.stem, "path": _rel(md, root), "source_kind": "distillate"})
    return out


# --------------------------------------------------------------------------- #
# face 4 — physics_corpus (collaborator structural distillates; contrast class)
# --------------------------------------------------------------------------- #
def census_physics_corpus(root: Path) -> dict[str, Any]:
    people_dir = root / "collaborator_corpus" / "people"
    struct_dir = root / "collaborator_corpus" / "_structural"
    authors: list[dict[str, Any]] = []
    if people_dir.is_dir():
        for md in sorted(people_dir.glob("*.md")):
            author = md.stem
            struct = struct_dir / f"{author}.json"
            authors.append({
                "author": author,
                "person": _rel(md, root),
                "structural": _rel(struct, root) if struct.is_file() else None,
                "source_kind": "structural",
            })
    substrate = root / "reference_corpus" / "_substrate_mccaul.json"
    return {
        "collaborator_authors": authors,
        "count": len(authors),
        "bib_substrate": _rel(substrate, root) if substrate.is_file() else None,
        "note": ("collaborator_corpus holds prose-less STRUCTURAL distillates of other "
                 "physicists' corpora (the C6 closure-margin contrast class). No prose → "
                 "NOT a form-exemplar source; useful only as a negative/contrast class "
                 "and for the section/spine ID layer."),
    }


# --------------------------------------------------------------------------- #
# demo pick + assembly
# --------------------------------------------------------------------------- #
def pick_demo_papers(papers_tex: list[dict[str, Any]], k: int = 2) -> list[str]:
    """The top-k papers_tex by mechanical richness, restricted to papers with clean
    \\section{} boundaries (sections >= 2) — the held-out-SECTION gate needs real section
    grain. Reproducible from this script; the design cites this pick."""
    eligible = [p for p in papers_tex if p["sections"] >= 2]
    ranked = sorted(eligible, key=lambda p: (-p["richness"], p["paper_id"]))
    return [p["paper_id"] for p in ranked[:k]]


def build_census(root: Path) -> dict[str, Any]:
    papers_tex = census_papers_tex(root)
    papers_pdf = census_papers_pdf(root)
    distillates = census_distillates(root)
    physics = census_physics_corpus(root)
    tex_file_count = sum(len(p["tex_files"]) for p in papers_tex)
    demo = pick_demo_papers(papers_tex)
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(root),
        "summary": {
            "papers_tex": len(papers_tex),
            "tex_files": tex_file_count,
            "papers_pdf_present": papers_pdf["present_on_disk"],
            "papers_pdf_documented": papers_pdf["documented_reference_only"],
            "distillates": len(distillates),
            "physics_corpus": physics["count"],
            "extractable_today": len(papers_tex),        # only tex has prose to lens
            "lens_reads_today": len(papers_tex) * 5,     # 5 FORM lenses
            "lens_reads_full": papers_pdf["documented_reference_only"] * 5,
        },
        "demo_papers": demo,
        "papers_tex": papers_tex,
        "papers_pdf": papers_pdf,
        "distillates": distillates,
        "physics_corpus": physics,
    }


def print_summary(census: dict[str, Any]) -> None:
    s = census["summary"]
    print("# STAGE-STORES corpus census")
    print(f"schema: {census['schema']}")
    print()
    print(f"papers_tex (extractable prose):   {s['papers_tex']}  ({s['tex_files']} .tex files)")
    print(f"papers_pdf (his published):       present={s['papers_pdf_present']}  "
          f"documented={s['papers_pdf_documented']} (reference-only, not committed)")
    print(f"distillates (life_corpus/papers): {s['distillates']}  (prose-less id spine)")
    print(f"physics_corpus (collaborators):   {s['physics_corpus']}  (structural, contrast class)")
    print()
    print(f"lens-reads TODAY (tex × 5 lenses): {s['lens_reads_today']}")
    print(f"lens-reads FULL  (25 × 5 lenses):  {s['lens_reads_full']}")
    print()
    print("papers_tex by richness (section/subsec/fig/eq/para → richness):")
    for p in sorted(census["papers_tex"], key=lambda p: -p["richness"]):
        mark = "  <- DEMO" if p["paper_id"] in census["demo_papers"] else ""
        print(f"  {p['paper_id']:<42} "
              f"sec={p['sections']:<3} sub={p['subsections']:<3} "
              f"fig={p['figures']:<3} eq={p['equations']:<4} "
              f"para={p['paragraphs_est']:<4} R={p['richness']}{mark}")
    print()
    print(f"DEMO papers (top-2 by richness, sections>=2): {', '.join(census['demo_papers'])}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo-root", default=str(_REPO_ROOT))
    ap.add_argument("--out", default=None,
                    help="census JSON path (default: <repo>/corpus_friction/stage_corpus_census.json)")
    ap.add_argument("--quiet", action="store_true", help="write the JSON, print nothing")
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])

    root = Path(args.repo_root).resolve()
    out = Path(args.out) if args.out else root / "corpus_friction" / "stage_corpus_census.json"

    census = build_census(root)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(census, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if not args.quiet:
        print_summary(census)
        print()
        print(f"wrote: {_rel(out, root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
