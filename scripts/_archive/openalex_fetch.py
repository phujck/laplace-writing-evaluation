"""openalex_fetch.py - reliable literature fetch via the OpenAlex API (no auth, verified metadata).

The reference tool for the Laplace soul-ingest enrichment AND for building references for any project.
Fires off verified paper metadata + the reference graph (``referenced_works`` = the bib-substrate) for
an author, a co-authorship pair, or a topic. No cookies, no Chrome, no hallucination - the data is the
API's, not the model's. Polite-pool (mailto) so it stays fast and reliable.

CLI:
  python openalex_fetch.py resolve "Name" [--anchor <mccaul_id>]   # author id (co-author disambiguated)
  python openalex_fetch.py scope                                   # size the enrichment corpus
  python openalex_fetch.py works <author_id> [--out file.json]     # an author's works + refs + abstracts
  python openalex_fetch.py coauthored <id_a> <id_b> [--out f.json] # works by both
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

OA = "https://api.openalex.org/"
MAILTO = "gerard.mccaul@gmail.com"
MCCAUL = "A5007680441"  # Gerard McCaul's OpenAlex author id
COLLABORATORS = [
    "Denys Bondar", "Kurt Jacobs", "George Booth", "William Handley",
    "Juan Sebastian Totero Gongora", "Christian Arenz", "Alicia Magann",
    "Viktor Ivady", "Alexander Balanov", "Tapio Ala-Nissila",
]


def _get(path: str, **params):
    params.setdefault("mailto", MAILTO)
    url = OA + path + "?" + urllib.parse.urlencode(params)
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001 - retry transient API hiccups
            last = e
            time.sleep(1.0 + attempt)
    raise last


def reconstruct_abstract(inv: dict | None) -> str:
    """OpenAlex stores abstracts as an inverted index {word: [positions]}; rebuild the text."""
    if not inv:
        return ""
    pos: dict[int, str] = {}
    for w, ps in inv.items():
        for p in ps:
            pos[p] = w
    return " ".join(pos[i] for i in sorted(pos))


def _short(wid: str) -> str:
    return wid.split("/")[-1]


def resolve_author(name: str, anchor: str | None = None) -> dict | None:
    """Resolve a name to an OpenAlex author. If ``anchor`` (another author id) is given, prefer the
    candidate who has co-authored with the anchor - the reliable disambiguation for a collaborator."""
    res = _get("authors", search=name, per_page=8).get("results", [])
    if not res:
        return None
    if anchor:
        for a in res:
            n = _get("works", filter=f"author.id:{_short(a['id'])},author.id:{anchor}",
                     per_page=1).get("meta", {}).get("count", 0)
            if n > 0:
                a["_coauthored_with_anchor"] = n
                return a
    return res[0]


def works_for(author_id: str, max_works: int = 400) -> list[dict]:
    out: list[dict] = []
    cursor = "*"
    sel = "id,title,publication_year,doi,referenced_works,authorships,abstract_inverted_index"
    while cursor and len(out) < max_works:
        d = _get("works", filter=f"author.id:{author_id}", per_page=50, cursor=cursor, select=sel)
        rows = d.get("results", [])
        out += rows
        cursor = d.get("meta", {}).get("next_cursor")
        if not rows:
            break
    return out[:max_works]


def coauthored(a: str, b: str, max_works: int = 200) -> list[dict]:
    sel = "id,title,publication_year,doi,referenced_works,authorships,abstract_inverted_index"
    d = _get("works", filter=f"author.id:{a},author.id:{b}", per_page=max_works, select=sel)
    return d.get("results", [])


def _slim(w: dict) -> dict:
    return {
        "id": _short(w["id"]),
        "title": w.get("title") or "",
        "year": w.get("publication_year"),
        "doi": w.get("doi"),
        "authors": [au["author"]["display_name"] for au in w.get("authorships", [])],
        "n_refs": len(w.get("referenced_works", [])),
        "referenced_works": [_short(r) for r in w.get("referenced_works", [])],
        "abstract": reconstruct_abstract(w.get("abstract_inverted_index")),
    }


def cmd_scope() -> int:
    print(f"McCaul = {MCCAUL}")
    mc = works_for(MCCAUL)
    mc_refs = set()
    for w in mc:
        mc_refs |= {_short(r) for r in w.get("referenced_works", [])}
    print(f"McCaul works: {len(mc)} | unique referenced works (his substrate): {len(mc_refs)}")
    print()
    print(f"{'collaborator':30s} {'id':14s} {'works':>5s} {'co-McCaul':>9s}")
    grand = set(mc_refs)
    for name in COLLABORATORS:
        a = resolve_author(name, anchor=MCCAUL)
        if not a:
            print(f"  {name:28s} NOT FOUND")
            continue
        aid = _short(a["id"])
        co = coauthored(MCCAUL, aid)
        for w in co:
            grand |= {_short(r) for r in w.get("referenced_works", [])}
        print(f"  {a['display_name']:28s} {aid:14s} {a['works_count']:5d} {len(co):9d}")
    print()
    print(f"unique references across McCaul + all co-authored papers (bib-substrate estimate): {len(grand)}")
    return 0


def cmd_substrate(author_id: str, out: str) -> int:
    """Build the bib-substrate: an author's works + the deduplicated reference graph (each reference a
    node carrying who-cites-it, so the repeated references become shared hubs - the deepest grade,
    dormant, dragged up on demand). The exogenous literature his work stands on."""
    works = works_for(author_id)
    cited_by: dict[str, list[str]] = {}
    for w in works:
        wid = _short(w["id"])
        for r in w.get("referenced_works", []):
            cited_by.setdefault(_short(r), []).append(wid)
    ref_ids = list(cited_by)
    meta: dict[str, dict] = {}
    for i in range(0, len(ref_ids), 50):
        batch = ref_ids[i:i + 50]
        d = _get("works", filter="openalex_id:" + "|".join(batch), per_page=50,
                 select="id,title,publication_year,authorships")
        for w in d.get("results", []):
            meta[_short(w["id"])] = {
                "title": w.get("title") or "",
                "year": w.get("publication_year"),
                "authors": [a["author"]["display_name"] for a in w.get("authorships", [])][:6],
            }
    refs = [dict(id=rid, n_cited=len(cited_by[rid]), cited_by=cited_by[rid],
                 **meta.get(rid, {"title": "(metadata unavailable)", "year": None, "authors": []}))
            for rid in ref_ids]
    refs.sort(key=lambda r: -r["n_cited"])
    index = {
        "_about": "bib-substrate: the deduplicated exogenous reference graph of the author's corpus "
                  "(OpenAlex). Each reference carries who-cites-it; the heavily-repeated refs are the "
                  "deep spine. Dormant - surfaced on demand when a goal needs the literature.",
        "author": author_id, "n_works": len(works), "n_references": len(refs),
        "references": refs,
        "works": [_slim(w) for w in works],
    }
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"works: {len(works)} | unique references (bib-substrate): {len(refs)} -> {out}")
    print("top-cited reference hubs (the repeated refs = the deep spine his work stands on):")
    for r in refs[:12]:
        au = (r["authors"][0].split()[-1] + " et al." if r["authors"] else "?")
        print(f"  {r['n_cited']:2d}x  {r.get('year') or '????'}  {au:18s} {r['title'][:62]}")
    return 0


def cmd_works(author_id: str, out: str | None) -> int:
    ws = [_slim(w) for w in works_for(author_id)]
    if out:
        Path(out).write_text(json.dumps(ws, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{len(ws)} works -> {out}")
    else:
        print(json.dumps(ws, ensure_ascii=False, indent=1))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("resolve"); r.add_argument("name"); r.add_argument("--anchor", default=MCCAUL)
    sub.add_parser("scope")
    s = sub.add_parser("substrate"); s.add_argument("author_id"); s.add_argument("--out", required=True)
    w = sub.add_parser("works"); w.add_argument("author_id"); w.add_argument("--out")
    c = sub.add_parser("coauthored"); c.add_argument("a"); c.add_argument("b"); c.add_argument("--out")
    args = ap.parse_args()
    if args.cmd == "resolve":
        a = resolve_author(args.name, anchor=args.anchor)
        print(json.dumps({"id": _short(a["id"]), "name": a["display_name"],
                          "works": a["works_count"]} if a else {"error": "not found"}))
        return 0
    if args.cmd == "scope":
        return cmd_scope()
    if args.cmd == "substrate":
        return cmd_substrate(args.author_id, args.out)
    if args.cmd == "works":
        return cmd_works(args.author_id, args.out)
    if args.cmd == "coauthored":
        ws = [_slim(w) for w in coauthored(args.a, args.b)]
        (Path(args.out).write_text(json.dumps(ws, ensure_ascii=False, indent=1), encoding="utf-8")
         if args.out else print(json.dumps(ws, ensure_ascii=False, indent=1)))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
