"""ingest_soul_dump.py - land the distilled soul-dump tranche as tracked conceptric nodes.

Stage 1-2 of canon://workflow/soul_ingestion, made mechanical (no LLM here - the distillation
already happened in sealed sub-Eigens; only the typed distillates rose). This reads the committed
distillate MANIFESTS (life_corpus/_manifest.json, soul_corpus/_manifest.json) and writes the
human-readable, shard-able node files:

  life_corpus/papers/<slug>.md   - one EPISODIC node per published paper (indexed, not compressed)
  life_corpus/people/<slug>.md   - one node per RECURRING collaborator (>=2 shared papers)
  soul_corpus/voice/<slug>.md    - one TASTE node per voice-primitive (the compressed generator)
  concept_corpus/themes/<id>.md  - one CONCEPT theme (grade 1), reduced UP from the paper atoms
  concept_corpus/pillars/<id>.md - one CONCEPT pillar (grade 2), the apex of the conceptual map

The RAW (archive/soul_dump/, 26M of PDFs/text) stays gitignored - never tracked, never loaded by
the orchestrator. Each node carries a `provenance` pointer back to the gitignored raw, the firewall
pattern of archive/transcripts/README.md: the raw is the record we can fold a stub back against.

Idempotent: re-running overwrites the node files from the manifest (the manifest is authoritative).
Deterministic: no clock, no randomness. The COARSE conceptual map (the grade-1 themes + grade-2
pillars) IS written here from `concept_corpus/_manifest.json` - but only because it is itself the
output of a separate, judged, certified pass (the keeper's upward reduce + a builder!=judge
adjudication, the first production sweep of Stage 4). The manifest stays authoritative; this lays it
down as wired nodes. With `--fire`, each concept node lights the running brain scanner as it is born.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def slugify(name: str) -> str:
    """A person's name -> a stable node slug. Drop single-letter initials and punctuation."""
    toks = [t for t in re.split(r"[^A-Za-z0-9]+", name.lower()) if len(t) > 1]
    return "-".join(toks) or re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _frontmatter(d: dict) -> str:
    lines = ["---"]
    for k, v in d.items():
        if isinstance(v, list):
            lines.append(f"{k}: [{', '.join(str(x) for x in v)}]")
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines)


def write_paper_nodes(life: dict) -> list[str]:
    out = []
    d = REPO / "life_corpus" / "papers"
    d.mkdir(parents=True, exist_ok=True)
    for p in life["papers"]:
        fm = _frontmatter({
            "kind": "paper", "slug": p["slug"], "year": p["year"],
            "venue": p["venue"] or "(preprint)", "gerard_position": p["gerard_position"],
            "faithfulness": p["faithfulness"], "provenance": p["source_txt"],
        })
        body = [
            fm, "", f"# {p['title']}", "",
            f"**Claim.** {p['claim']}", "",
            f"**Authors.** {', '.join(p['authors'])}", "",
            f"**Concepts.** {', '.join(p['concepts'])}  ", f"**Methods.** {', '.join(p['methods'])}",
            "",
            "> Episodic node (`life_corpus`): an indexed fact of the author's scientific record, "
            "not a compressed generator; closes by **retrieval**. The raw paper is sealed in "
            f"`{p['source_txt']}` (gitignored) - this is the distilled trace.",
        ]
        if p["issue"]:
            body += ["", f"<!-- provenance note ({p['faithfulness']}): {p['issue']} -->"]
        (d / f"{p['slug']}.md").write_text("\n".join(body) + "\n", encoding="utf-8")
        out.append(f"life_corpus/papers/{p['slug']}.md")
    return out


def write_people_nodes(life: dict, min_papers: int = 2) -> list[str]:
    """A node per RECURRING collaborator (>=min_papers shared works) - the real collaboration graph
    of this corpus. One-off co-authors stay listed in their paper's Authors line, no separate node
    (recurrence is the admission rule, the same as for taste traits)."""
    coauth: dict[str, list[dict]] = defaultdict(list)
    for p in life["papers"]:
        for a in p["authors"]:
            if "mccaul" in a.lower():
                continue
            coauth[a].append(p)
    out = []
    d = REPO / "life_corpus" / "people"
    d.mkdir(parents=True, exist_ok=True)
    for name, papers in sorted(coauth.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        if len(papers) < min_papers:
            continue
        slug = slugify(name)
        fm = _frontmatter({"kind": "person", "slug": slug, "shared_works": len(papers)})
        links = "\n".join(f"- [[life_corpus/papers/{p['slug']}.md]]" for p in
                          sorted(papers, key=lambda x: x["year"]))
        body = [
            fm, "", f"# {name}", "",
            f"Collaborator of the author on **{len(papers)}** works in this corpus.", "",
            "> Episodic node (`life_corpus`, person): a de-identifiable public co-author; the edges "
            "are the shared works (the collaboration graph closes by retrieval).", "",
            "## Shared works", "", links,
        ]
        (d / f"{slug}.md").write_text("\n".join(body) + "\n", encoding="utf-8")
        out.append(f"life_corpus/people/{slug}.md")
    return out


def write_voice_nodes(soul: dict) -> list[str]:
    out = []
    d = REPO / "soul_corpus" / "voice"
    d.mkdir(parents=True, exist_ok=True)
    for v in soul["primitives"]:
        fm = _frontmatter({
            "kind": "taste", "type": v["type"], "slug": v["name"],
            "faithfulness": v["faithfulness"], "recurs_in": len(v["recurs_in"]),
        })
        body = [
            fm, "", f"# {v['name']}", "",
            f"*{v['type']}* — {v['essence']}", "",
            f"**Exhibited in.** {', '.join(v['recurs_in'])}  ", f"**Trace.** {v['evidence']}",
            "",
            "> Taste node (`soul_corpus`): a move of the author's lead-author voice — the generator, "
            "not the content; closes by **re-derivation** (a blind ghost given only the corpus must "
            "reproduce it). Distilled from gitignored raw prose; de-identified.",
        ]
        if v["faithfulness"] == "partial":
            body += ["", f"<!-- provenance note (partial): {v['issue']} -->"]
        (d / f"{v['name']}.md").write_text("\n".join(body) + "\n", encoding="utf-8")
        out.append(f"soul_corpus/voice/{v['name']}.md")
    return out


def write_concept_nodes(concept: dict, fire: bool = False) -> list[str]:
    """Write the CONCEPTUAL map (the 3rd soul map): grade-1 themes + grade-2 pillars - the coarse
    nodes reduced UP from the per-paper concept-atoms by the keeper (the upward operator, F23) and
    adjudicated builder != judge. Each theme wires DOWN to the life_corpus papers that exhibit it;
    each pillar wires down to its themes - so the conceptual map is a real graph, not a list. With
    ``fire`` the running brain scanner is lit per node, so the author WATCHES each concept born."""
    out: list[str] = []
    fired = None
    if fire:
        try:
            from laplace.web.scanner import client_fire as fired  # type: ignore
        except Exception:  # noqa: BLE001 - the watch is never required for the materialise
            fired = None

    dt = REPO / "concept_corpus" / "themes"
    dt.mkdir(parents=True, exist_ok=True)
    for t in concept.get("grade1_themes", []):
        rec = t.get("recurrence", len(t.get("papers", [])))
        fm = _frontmatter({"kind": "concept-theme", "slug": t["id"], "grade": 1,
                           "recurrence": rec, "faithfulness": t.get("faithfulness", "unadjudicated")})
        paper_links = "\n".join(f"- [[life_corpus/papers/{s}.md]]" for s in sorted(t.get("papers", [])))
        body = [fm, "", f"# {t['title']}", "", t["essence"], "",
                f"**Concepts.** {', '.join(t.get('concepts', []))}  "]
        if t.get("methods"):
            body.append(f"**Methods.** {', '.join(t['methods'])}  ")
        body += [f"**Recurs across {rec} of his papers.**", "", "## Exhibited in", "", paper_links, "",
                 "> Concept node (`concept_corpus`, grade-1 theme): a recurring theme of the author's "
                 "physics, reduced UP from the per-paper concept-atoms by the keeper and adjudicated "
                 "builder != judge. The structure of the thought, not the events; closes by **retrieval**."]
        if t.get("issue"):
            body += ["", f"<!-- adjudication note ({t.get('faithfulness')}): {t['issue']} -->"]
        (dt / f"{t['id']}.md").write_text("\n".join(body) + "\n", encoding="utf-8")
        out.append(f"concept_corpus/themes/{t['id']}.md")
        if fired:
            fired(t["title"], by="eigen")

    dp = REPO / "concept_corpus" / "pillars"
    dp.mkdir(parents=True, exist_ok=True)
    for p in concept.get("grade2_pillars", []):
        fm = _frontmatter({"kind": "concept-pillar", "slug": p["id"], "grade": 2,
                           "faithfulness": p.get("faithfulness", "unadjudicated")})
        theme_links = "\n".join(f"- [[concept_corpus/themes/{tid}.md]]" for tid in p.get("themes", []))
        body = [fm, "", f"# {p['title']}", "", p["essence"], "", "## Themes", "", theme_links, "",
                "> Concept node (`concept_corpus`, grade-2 pillar): a coarse pillar of the author's "
                "body of work - what his physics is fundamentally about. The apex of the conceptual map."]
        if p.get("issue"):
            body += ["", f"<!-- adjudication note ({p.get('faithfulness')}): {p['issue']} -->"]
        (dp / f"{p['id']}.md").write_text("\n".join(body) + "\n", encoding="utf-8")
        out.append(f"concept_corpus/pillars/{p['id']}.md")
        if fired:
            fired(p["title"], by="eigen")
    return out


def write_atom_nodes(atoms: dict, fire: bool = False) -> list[str]:
    """Write the grade-0 sub-grade BENEATH the themes: one node per paper holding the rich concept-
    atoms a sealed sub distilled from its FULL TEXT (mechanisms, derivations, detailed methods,
    results, internal relations) - the substance the abstract tags compress away. Each wires UP to
    its grade-1 theme and DOWN-anchors to its life_corpus paper. With ``fire`` lights the scanner."""
    out: list[str] = []
    fired = None
    if fire:
        try:
            from laplace.web.scanner import client_fire as fired  # type: ignore
        except Exception:  # noqa: BLE001
            fired = None
    d = REPO / "concept_corpus" / "atoms"
    d.mkdir(parents=True, exist_ok=True)
    for p in atoms.get("papers", []):
        kept = p.get("atoms", [])
        fm = _frontmatter({
            "kind": "concept-atoms", "slug": p["slug"], "grade": 0,
            "theme": p.get("theme", ""), "pillar": p.get("pillar", ""),
            "faithfulness": p.get("faithfulness", "unadjudicated"), "n_atoms": len(kept),
        })
        by_kind: dict[str, list] = {}
        for a in kept:
            by_kind.setdefault(a.get("kind", "concept"), []).append(a)
        body = [fm, "", f"# {p['slug']} — full-text sub-grade", "",
                f"**Core contribution.** {p.get('core_contribution', '')}", ""]
        for kind in ("mechanism", "concept", "method", "result", "relation"):
            items = by_kind.get(kind, [])
            if not items:
                continue
            body += [f"## {'Relations' if kind == 'relation' else kind.capitalize() + 's'}", ""]
            for a in items:
                loc = f"  _({a['locator']})_" if a.get("locator") else ""
                body.append(f"- **{a.get('name', '')}** — {a.get('statement', '')}{loc}")
            body.append("")
        if p.get("internal_relations"):
            body += ["## Idea-structure", ""] + [f"- {r}" for r in p["internal_relations"]] + [""]
        if p.get("beyond_abstract"):
            body += [f"**Beyond the abstract.** {p['beyond_abstract']}", ""]
        theme = p.get("theme", "")
        theme_wire = (f"- theme: [[concept_corpus/themes/{theme}.md]]" if theme
                      else "- theme: _(unclustered singleton — no recurring theme yet)_")
        body += ["## Wires", "", theme_wire,
                 f"- paper: [[life_corpus/papers/{p['slug']}.md]]", "",
                 "> Concept node (`concept_corpus`, grade-0 atoms): the fine conceptual substance of "
                 "one paper, distilled from its FULL TEXT by a sealed sub and adjudicated builder != "
                 "judge - the grade-0 layer beneath the grade-1 themes. Closes by **retrieval**."]
        (d / f"{p['slug']}.md").write_text("\n".join(body) + "\n", encoding="utf-8")
        out.append(f"concept_corpus/atoms/{p['slug']}.md")
        if fired:
            fired(f"{p.get('theme', '')} · {p['slug']} sub-grade", by="eigen")
    return out


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Materialise distilled soul-dump nodes from the committed manifests.")
    ap.add_argument("--only", choices=["all", "leaves", "concepts", "atoms"], default="all",
                    help="all = leaves + conceptual map + sub-grade; leaves = papers/people/voice; "
                         "concepts = themes/pillars; atoms = the grade-0 full-text sub-grade")
    ap.add_argument("--fire", action="store_true", help="light the running brain scanner per concept node (watch the birth)")
    args = ap.parse_args()

    written: dict[str, list[str]] = {}
    if args.only in ("all", "leaves"):
        life = json.loads((REPO / "life_corpus" / "_manifest.json").read_text(encoding="utf-8"))
        soul = json.loads((REPO / "soul_corpus" / "_manifest.json").read_text(encoding="utf-8"))
        written["papers"] = write_paper_nodes(life)
        written["people"] = write_people_nodes(life)
        written["voice"] = write_voice_nodes(soul)
    if args.only in ("all", "concepts"):
        cpath = REPO / "concept_corpus" / "_manifest.json"
        if cpath.exists():
            written["concepts"] = write_concept_nodes(
                json.loads(cpath.read_text(encoding="utf-8")), fire=args.fire)
    if args.only in ("all", "atoms"):
        apath = REPO / "concept_corpus" / "_atoms_manifest.json"
        if apath.exists():
            written["atoms"] = write_atom_nodes(
                json.loads(apath.read_text(encoding="utf-8")), fire=args.fire)

    for k, v in written.items():
        print(f"{k:9s}: {len(v)}")
    print(f"total nodes written: {sum(len(v) for v in written.values())}")
    if written.get("concepts"):
        print("\nconceptual map (the 3rd of the 6 maps):")
        for pth in written["concepts"]:
            print(f"  {pth}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
