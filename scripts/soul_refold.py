"""soul_refold.py - the mechanical fold for a re-distilled soul tranche.

Implements two laws with no model in the loop (the 2026-08-21 redo of the June
machinery): the locator law (every item an object carrying its source citation)
and the citation-consistency check (each quoted excerpt is confirmed to appear at
its cited line range, the way a copy-editor checks a quotation's page reference -
an item whose excerpt does not resolve keeps a flag; nothing is dropped).

Fold and apex are UNION + DEDUP only - no summarisation, no rewriting; content
carries verbatim under the repo's unseal (2026-07-12). stdout is counts only, so
the calling layer never carries content.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

FIELDS_PARTNER = ("voice", "history", "relations")
FIELDS_GERARD = ("voice", "history", "relations", "generator")
LOC_RE = re.compile(r"^([^:]+):L(\d+)(?:-L?(\d+))?", re.I)
SIM = 0.93
SLACK = 2


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def _hard(s: str) -> str:
    """Aggressive fold for excerpt matching: WhatsApp exports carry narrow no-break
    spaces, curly quotes and emoji the agents transcribed variably - measured 16/300
    recoveries from unicode folding alone."""
    import unicodedata
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", s or "").lower())


def _content_of(item: dict) -> str:
    return str(item.get("content") or item.get("statement") or item.get("nature") or "")



def _resolve_window(fname: str, raw_dir: Path):
    """Resolve a cited window filename tolerantly: the floor agents wrote variant
    basenames (suffix dropped, .txt doubled or halved, case drift). Exact first,
    then suffix variants, then unique-prefix, then a normalised unique match."""
    cands = [fname, fname + ".txt", fname.rsplit(".txt", 1)[0] + ".txt"]
    for c in cands:
        p = raw_dir / c
        if p.is_file():
            return p.read_text(encoding="utf-8", errors="replace").splitlines()
    names = [q.name for q in raw_dir.iterdir() if q.is_file()]
    stem = fname.rsplit(".txt", 1)[0]
    pref = [n for n in names if n.startswith(stem)]
    if len(pref) == 1:
        return (raw_dir / pref[0]).read_text(encoding="utf-8", errors="replace").splitlines()
    normal = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
    nf = normal(fname)
    close = [n for n in names if normal(n) == nf or normal(n).startswith(nf) or nf.startswith(normal(n))]
    if len(close) == 1:
        return (raw_dir / close[0]).read_text(encoding="utf-8", errors="replace").splitlines()
    return None


def check_citation(item: dict, raw_dir: Path, cache: dict) -> None:
    """Confirm the item's quoted excerpt appears at its cited line range."""
    loc = item.get("locator")
    if not loc or not isinstance(loc, str):
        item["verified"] = False
        item["flag"] = "null-locator"
        return
    m = LOC_RE.match(loc.strip())
    src = _norm(item.get("source") or "")
    if not m or not src:
        item["verified"] = False
        item["flag"] = "unparseable-locator" if not m else "no-source-excerpt"
        return
    fname, a, b = m.group(1), int(m.group(2)), int(m.group(3) or m.group(2))
    if fname not in cache:
        cache[fname] = _resolve_window(fname, raw_dir)
    lines = cache[fname]
    if lines is None:
        item["verified"] = False
        _family_repair(item, fname, src, raw_dir, cache)
        return
    lo, hi = max(0, a - 1 - SLACK), min(len(lines), b + SLACK)
    window = _norm(" ".join(lines[lo:hi]))
    item["verified"] = src in window
    if not item["verified"]:
        _family_repair(item, fname, src, raw_dir, cache)



def _family_repair(item, fname: str, src: str, raw_dir: Path, cache: dict) -> None:
    """The floor agents often cited the person's chat FILE, not their window - a prefix
    matching every window of that person. Mechanical repair: search the excerpt across
    the family; on a hit, rewrite the locator to the window and lines where it actually
    resolves (flag locator-repaired). An excerpt found nowhere keeps excerpt-unfound -
    the honest confabulation marker."""
    if "__names__" not in cache:
        cache["__names__"] = sorted(q.name for q in raw_dir.iterdir() if q.is_file() and q.name != "_manifest.json")
    stem = fname.rsplit(".txt", 1)[0]
    hstem = _hard(stem)
    # containment, not prefix: half the floor agents dropped the disk-name prefix
    # ('WhatsApp_Chat_with_X' vs 'archive_soul_dump_raw_chat_logs_X_WhatsApp_...');
    # empty family falls back to the whole corpus with the crossfile flag.
    fam = [n for n in cache["__names__"] if stem in n or (hstem and hstem in _hard(n))]
    crossfile = False
    if not fam:
        fam = cache["__names__"]
        crossfile = True
    hsrc = _hard(item.get("source") or "")
    hits = []
    for name in fam:
        key = f"__lines__{name}"
        if key not in cache:
            cache[key] = (raw_dir / name).read_text(encoding="utf-8", errors="replace").splitlines()
        lines = cache[key]
        nl = [_hard(x) for x in lines]
        joined = "".join(nl)
        pos = joined.find(hsrc) if hsrc else -1
        if pos < 0:
            continue
        # map char offset -> line span via prefix sums (hard-norm join has no separator)
        acc, a = 0, 0
        for i, s in enumerate(nl):
            if acc + len(s) > pos:
                a = i
                break
            acc += len(s)
        b = a
        need = pos + len(hsrc)
        while acc + len(nl[b]) < need and b + 1 < len(nl):
            acc += len(nl[b])
            b += 1
        hits.append((name, a + 1, b + 1))
        if len(hits) > 1:
            break
    if hits:
        name, a, b = hits[0]
        item["locator"] = f"{name}:L{a}-L{b}"
        item["verified"] = True
        item["flag"] = ("locator-repaired-crossfile" if crossfile
                        else "locator-repaired" if len(hits) == 1 else "locator-repaired-multi")
    else:
        item["flag"] = "excerpt-unfound"


def dedup(items: list[dict]) -> tuple[list[dict], int]:
    """Union with near-duplicate collapse: normalised-identical or ratio>=SIM merge to
    the item with the longer excerpt; locators union into a list. Never rewrites."""
    kept: list[dict] = []
    collapsed = 0
    for it in items:
        c = _norm(_content_of(it))
        if not c:
            continue
        hit = None
        for k in kept:
            kc = k.get("_nc") if "_nc" in k else _norm(_content_of(k))
            k["_nc"] = kc
            if c == kc:
                hit = k
                break
            # cheap gates before the expensive ratio: length bound, then quick_ratio
            if abs(len(c) - len(kc)) > (1 - SIM) * max(len(c), len(kc)):
                continue
            sm = difflib.SequenceMatcher(None, c, kc)
            if sm.quick_ratio() < SIM:
                continue
            if sm.ratio() >= SIM:
                hit = k
                break
        if hit is None:
            it = dict(it)
            it["locators"] = [it.get("locator")] if it.get("locator") else []
            kept.append(it)
        else:
            collapsed += 1
            if len(str(it.get("source") or "")) > len(str(hit.get("source") or "")):
                for f in ("content", "statement", "nature", "source", "locator", "verified", "flag", "confidence", "primitive", "with"):
                    if f in it:
                        hit[f] = it[f]
            if it.get("locator") and it["locator"] not in hit.get("locators", []):
                hit.setdefault("locators", []).append(it["locator"])
    return kept, collapsed


def fold_fields(parts: list[dict], fields: tuple) -> tuple[dict, int, list[dict]]:
    ent: dict = {}
    collapsed = 0
    conjectural: list[dict] = []
    for f in fields:
        pool = [it for p in parts for it in (p.get(f) or []) if isinstance(it, dict)]
        kept, n = dedup(pool)
        collapsed += n
        firm = [it for it in kept if str(it.get("confidence", "")).lower() != "low"]
        conjectural += [dict(it, field=f) for it in kept if str(it.get("confidence", "")).lower() == "low"]
        ent[f] = firm
    return ent, collapsed, conjectural


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--partials-dir", required=True)
    ap.add_argument("--raw-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()
    pdir, rdir, odir = Path(args.partials_dir), Path(args.raw_dir), Path(args.out_dir)
    odir.mkdir(parents=True, exist_ok=True)

    partials = []
    for f in sorted(pdir.glob("*.json")):
        try:
            partials.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            print(f"unreadable-partial {f.name}", file=sys.stderr)

    cache: dict = {}
    stats = defaultdict(int)
    by_person: dict[str, list[dict]] = defaultdict(list)
    gerard_parts: list[dict] = []
    for p in partials:
        for side, fields in (("partner", FIELDS_PARTNER), ("gerard", FIELDS_GERARD)):
            blk = p.get(side) or {}
            for f in fields:
                for it in blk.get(f) or []:
                    if isinstance(it, dict):
                        check_citation(it, rdir, cache)
                        stats["n_items"] += 1
                        stats["n_verified" if it.get("verified") else "n_unverified"] += 1
                        fl = it.get("flag")
                        if fl:
                            stats[f"flag_{fl}"] += 1
                        if it.get("flag") == "null-locator":
                            stats["n_null_locator"] += 1
        by_person[p.get("person") or "(unknown)"].append(p.get("partner") or {})
        if p.get("gerard"):
            gerard_parts.append(p["gerard"])

    n_entities = 0
    safe = lambda s: re.sub(r"[^A-Za-z0-9_-]", "_", s)
    for person, parts in sorted(by_person.items()):
        ent, collapsed, conj = fold_fields(parts, FIELDS_PARTNER)
        stats["dedup_collapsed"] += collapsed
        for fl in ent.values():
            for it in fl:
                it.pop("_nc", None)
        for it in conj:
            it.pop("_nc", None)
        out = {"name": person, "is_author": False, **ent, "generator": [], "conjectural": conj}
        (odir / f"{safe(person)}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
        n_entities += 1
    ent, collapsed, conj = fold_fields(gerard_parts, FIELDS_GERARD)
    stats["dedup_collapsed"] += collapsed
    for fl in ent.values():
        for it in fl:
            it.pop("_nc", None)
    for it in conj:
        it.pop("_nc", None)
    (odir / "gerard.json").write_text(json.dumps(
        {"name": "Gerard", "is_author": True, **ent, "conjectural": conj},
        indent=1, ensure_ascii=False), encoding="utf-8")
    n_entities += 1

    stats_out = {"n_partials": len(partials), "n_people": len(by_person), "n_entities": n_entities, **stats}
    (odir / "_stats.json").write_text(json.dumps(stats_out, indent=1), encoding="utf-8")
    print(json.dumps(stats_out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
