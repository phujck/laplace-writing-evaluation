"""A map of the curated literature corpus - what is in there, and where the gaps are.

`deep_corpus_scout` maps an UNKNOWN raw tree before reading it. This is the
counterpart for the KNOWN, curated store: a navigable overview of `corpus.bib`
read through the `keywords.yaml` taxonomy, so the librarian can answer "what do we
already hold on X, and what is missing?" before spending a search. It emits:

* the conceptric - theme -> cluster -> reference, with each record's year/status;
* the trust profile (established / borrowed / unverified / ...);
* the relation density - how richly the primitives are connected, and the
  most-connected hubs;
* the coverage worklist - the gaps a librarian acts on: thin clusters, primitives
  with no relations or no summary, references awaiting distillation/promotion, and
  per-project citation counts.

Stdlib + yaml, host-executed, in the structured-ledger style of the other scripts.

Usage:
    python corpus_map.py <corpus.bib> [--gaps]   # --gaps prints only the worklist
"""

import os
import re
import sys
from collections import Counter, defaultdict

REL_TYPES = {
    "extends", "refines", "generalizes", "specializes", "contests", "corroborates",
    "applies", "tests", "motivates", "background_for", "analogue_of", "method_for",
    "reviews",
}


def read_safe(path):
    for enc in ("utf-8", "utf-16"):
        try:
            with open(path, encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def parse_records(text):
    records = []
    for m in re.finditer(r"@\w+\s*\{\s*([^,\s]+)\s*,", text):
        key = m.group(1).strip()
        i = m.start() + text[m.start():].index("{") + 1
        depth, j = 1, i
        while j < len(text) and depth > 0:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
            j += 1
        body = text[m.end():j - 1]
        fields = {}
        for fm in re.finditer(
            r"(\w+)\s*=\s*(\{(?:[^{}]|\{[^{}]*\})*\}|\"[^\"]*\"|[^,\n]+)", body
        ):
            fields[fm.group(1).strip().lower()] = fm.group(2).strip().strip("{}").strip('"').strip()
        records.append((key, fields))
    return records


def _toks(v):
    return [t.strip() for t in (v or "").split(",") if t.strip()]


def _year(f):
    m = re.search(r"\d{4}", f.get("year", ""))
    return int(m.group(0)) if m else 0


def _rel_count(f):
    return sum(1 for chunk in (f.get("relations") or "").split(";")
               if chunk.strip() and chunk.split(":", 1)[0].strip() in REL_TYPES)


def load_taxonomy(path):
    kp = os.path.join(os.path.dirname(os.path.abspath(path)), "keywords.yaml")
    cluster_theme, theme_label, theme_order = {}, {}, []
    if os.path.exists(kp):
        try:
            import yaml

            data = yaml.safe_load(read_safe(kp)) or {}
            for tname, t in (data.get("themes") or {}).items():
                t = t or {}
                theme_label[tname] = t.get("label", tname)
                theme_order.append(tname)
                for c in t.get("clusters", []) or []:
                    cluster_theme[c] = tname
        except Exception:
            pass
    return cluster_theme, theme_label, theme_order


def build_map(path, gaps_only=False):
    if not os.path.exists(path):
        print(f"Error: {path} not found.")
        return 2
    records = parse_records(read_safe(path))
    if not records:
        print("No records.")
        return 2
    cluster_theme, theme_label, theme_order = load_taxonomy(path)

    by_cluster = defaultdict(list)
    for key, f in records:
        for c in _toks(f.get("cluster")) or ["unclustered"]:
            by_cluster[c].append((key, f))
    status_counts = Counter(f.get("status", "?").strip().lower() for _, f in records)
    rel_total = sum(_rel_count(f) for _, f in records)
    # most-connected hubs: in+out typed relations per key.
    deg = Counter()
    for key, f in records:
        for chunk in (f.get("relations") or "").split(";"):
            chunk = chunk.strip()
            if not chunk:
                continue
            m = re.match(r"([a-z_]+)\s*:\s*([^|]+)", chunk)
            if m and m.group(1).strip() in REL_TYPES:
                deg[key] += 1
                deg[m.group(2).strip()] += 1
    projects = Counter()
    for _, f in records:
        for p in _toks(f.get("provenance")):
            projects[p] += 1

    if not gaps_only:
        print(f"# Corpus map: {os.path.basename(path)}")
        print(f"\n{len(records)} references | {len([c for c in by_cluster])} clusters | "
              f"{len(theme_order)} themes | {rel_total} typed relations "
              f"({rel_total/max(1,len(records)):.1f} per record)")
        print("Trust profile: " + ", ".join(f"{s}: {n}" for s, n in status_counts.most_common()))
        print("Provenance: " + ", ".join(f"{p}: {n}" for p, n in projects.most_common()))

        print("\n## The conceptric (theme -> cluster -> reference)")
        seen_clusters = set()
        for tname in theme_order:
            tclusters = [c for c, th in cluster_theme.items() if th == tname and c in by_cluster]
            if not tclusters:
                continue
            print(f"\n### {theme_label.get(tname, tname)}")
            for c in tclusters:
                seen_clusters.add(c)
                refs = sorted(by_cluster[c], key=lambda r: _year(r[1]))
                spine = ", ".join(f"{k} ({_year(f) or '?'}, {f.get('status','?')[:4]})" for k, f in refs)
                print(f"- **{c}** [{len(refs)}]: {spine}")
        loose = [c for c in by_cluster if c not in seen_clusters]
        if loose:
            print(f"\n### (clusters outside the taxonomy)")
            for c in loose:
                print(f"- **{c}** [{len(by_cluster[c])}]: {', '.join(k for k,_ in by_cluster[c])}")

        if deg:
            print("\n## Most-connected primitives (relation hubs)")
            for key, d in deg.most_common(8):
                print(f"- `{key}`: {d} relations")

    # The worklist - what a librarian acts on.
    thin_clusters = sorted(c for c, rs in by_cluster.items() if len(rs) <= 1)
    no_rel = sorted(k for k, f in records if _rel_count(f) == 0)
    no_summary = sorted(k for k, f in records if not (f.get("summary") or "").strip()
                        or re.match(r"^\s*todo", f.get("summary", ""), re.I))
    unverified = sorted(k for k, f in records if f.get("status", "").strip().lower() in ("unverified", "open-gap"))
    print("\n## Coverage worklist (the librarian's to-do)")
    print(f"- Thin clusters (<=1 reference): {', '.join(thin_clusters) or 'none'}")
    print(f"- Unconnected primitives (no relations): {len(no_rel)}"
          + (f" - {', '.join(no_rel[:12])}{'...' if len(no_rel) > 12 else ''}" if no_rel else ""))
    print(f"- Missing/TODO summary: {', '.join(no_summary) or 'none'}")
    print(f"- Unverified (awaiting fetch-verified distillation + promotion): {len(unverified)}")
    return 0


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print("Usage: python corpus_map.py <corpus.bib> [--gaps]", file=sys.stderr)
        return 2
    return build_map(args[0], gaps_only="--gaps" in argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
