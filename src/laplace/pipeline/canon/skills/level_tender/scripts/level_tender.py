"""Locate a distilled stub in the conceptric, and judge its level.

The middle of the knowledge-digestion pipeline (canon://workflow/knowledge_digestion):
a stub out of transcript_digest is matched against the conceptric (the corpus + its
taxonomy), and this recommends an ACTION on the scale axis -

  * place  - it sits at the matched cluster's level; wire it in there.
  * lower  - it is a detail subsumed by one existing node; attach it beneath that node.
  * lift   - it cuts across several clusters; it is a candidate for a coarser node
             (a new or existing theme) that spans them.
  * new    - nothing matches; it opens a new region (place loose, propose a cluster).

This is the operational front of the growth rule (move knowledge between scales by
judgement, EIGEN_ARCHITECTURE Component 2). The backing computes the structural
signal (overlap with clusters and with individual references); the *decision* is the
level_tender's to confirm - recommend, never auto-mutate the store. The keeper of
local knowledge (the_librarian) applies it.

Stdlib + yaml. Usage:
    python level_tender.py "<stub text>" <corpus.bib> [--cluster <hint>] [--json]
    python level_tender.py --stub-file <f> <corpus.bib> [--json]
"""

import json
import os
import re
import sys

_STOP = set("the a an of for and to in with on is are be as by that this it its from at "
            "or not no we you i our your their they them his her he she but if then so a "
            "which what when where who how why into out up down over under than".split())


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
        for fm in re.finditer(r"(\w+)\s*=\s*(\{(?:[^{}]|\{[^{}]*\})*\}|\"[^\"]*\"|[^,\n]+)", body):
            fields[fm.group(1).strip().lower()] = fm.group(2).strip().strip("{}").strip('"').strip()
        records.append((key, fields))
    return records


def _toks(s):
    return {w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if w not in _STOP and len(w) > 2}


def load_taxonomy(corpus_path):
    kp = os.path.join(os.path.dirname(os.path.abspath(corpus_path)), "keywords.yaml")
    cluster_theme, theme_label = {}, {}
    if os.path.exists(kp):
        try:
            import yaml
            data = yaml.safe_load(read_safe(kp)) or {}
            for t, meta in (data.get("themes") or {}).items():
                theme_label[t] = (meta or {}).get("label", t)
                for c in (meta or {}).get("clusters", []) or []:
                    cluster_theme[c] = t
        except Exception:
            pass
    return cluster_theme, theme_label


def tend(stub, corpus_path, hint=None):
    records = parse_records(read_safe(corpus_path))
    cluster_theme, theme_label = load_taxonomy(corpus_path)
    stub_toks = _toks(stub)

    # Per-cluster token bag (label + member keywords + member claim tokens) and a
    # per-reference token bag (for the lower test).
    cluster_tokens, ref_tokens, cluster_members = {}, {}, {}
    for key, f in records:
        rtok = _toks(f.get("keywords", "")) | _toks(f.get("claim", "")) | _toks(f.get("title", ""))
        ref_tokens[key] = rtok
        for c in [x.strip() for x in (f.get("cluster") or "").split(",") if x.strip()]:
            cluster_tokens.setdefault(c, _toks(c))
            cluster_tokens[c] |= rtok
            cluster_members.setdefault(c, []).append(key)

    def score(bag):
        return len(stub_toks & bag) / (len(stub_toks) or 1)

    cl_scores = sorted(((score(b), c) for c, b in cluster_tokens.items()), reverse=True)
    ref_scores = sorted(((score(b), k) for k, b in ref_tokens.items()), reverse=True)
    if hint and hint in cluster_tokens:
        cl_scores = sorted(cl_scores, key=lambda x: (x[1] != hint, -x[0]))

    top = cl_scores[0] if cl_scores else (0.0, None)
    second = cl_scores[1] if len(cl_scores) > 1 else (0.0, None)
    top_ref = ref_scores[0] if ref_scores else (0.0, None)
    second_ref = ref_scores[1] if len(ref_scores) > 1 else (0.0, None)

    # The judgement (structural signal; the level_tender confirms). Order matters:
    # nothing-matches, then subsumed-by-one-node (lower), then cuts-across (lift),
    # else place. `lower` fires when ONE reference dominates - the stub is a detail
    # or near-restatement of it - regardless of how broad its cluster is.
    if top[0] == 0:
        action, target, why = "new", None, "no cluster shares vocabulary - opens a new region; place loose and propose a cluster."
    elif top_ref[0] >= 0.6 and top_ref[0] >= 1.3 * (second_ref[0] or 0.0):
        action, target, why = ("lower", top_ref[1],
            f"dominated by one node ({top_ref[1]}, overlap {top_ref[0]:.2f} vs next {second_ref[0]:.2f}) - "
            f"attach beneath it as a detail or merge.")
    elif second[0] >= 0.6 * top[0] and second[0] > 0 and top[0] > 0:
        spanned = [top[1], second[1]]
        theme = cluster_theme.get(top[1])
        action, target, why = ("lift", theme or spanned,
            f"cuts across {top[1]} and {second[1]} (scores {top[0]:.2f}/{second[0]:.2f}) - "
            f"candidate for a coarser node" + (f" under theme '{theme}'." if theme else " (a new theme)."))
    else:
        action, target, why = ("place", top[1],
            f"sits at the {top[1]} level (overlap {top[0]:.2f}) - wire it in there.")

    return {
        "stub": stub[:200],
        "action": action,
        "target": target,
        "rationale": why,
        "top_clusters": [{"cluster": c, "score": round(s, 3), "theme": cluster_theme.get(c)}
                         for s, c in cl_scores[:3] if s > 0],
        "nearest_refs": [{"ref": k, "score": round(s, 3)} for s, k in ref_scores[:3] if s > 0],
    }


def main(argv):
    flags = {a for a in argv if a.startswith("--")}
    rest = [a for a in argv if not a.startswith("--")]
    stub = None
    if "--stub-file" in argv:
        i = argv.index("--stub-file")
        stub = read_safe(argv[i + 1])
        rest = [a for a in rest if a != argv[i + 1]]
    hint = None
    if "--cluster" in argv:
        i = argv.index("--cluster")
        hint = argv[i + 1]
        rest = [a for a in rest if a != hint]
    if stub is None:
        if len(rest) < 2:
            print('Usage: python level_tender.py "<stub>" <corpus.bib> [--cluster <hint>] [--json]',
                  file=sys.stderr)
            return 2
        stub, corpus_path = rest[0], rest[1]
    else:
        if not rest:
            print("Usage: python level_tender.py --stub-file <f> <corpus.bib> [--json]", file=sys.stderr)
            return 2
        corpus_path = rest[0]
    if not os.path.exists(corpus_path):
        print(f"Error: corpus {corpus_path} not found.", file=sys.stderr)
        return 2
    rec = tend(stub, corpus_path, hint)
    if "--json" in flags:
        print(json.dumps(rec, indent=2))
    else:
        print(f"# Level tender")
        print(f"ACTION: {rec['action'].upper()}" + (f" -> {rec['target']}" if rec['target'] else ""))
        print(f"  {rec['rationale']}")
        if rec["top_clusters"]:
            print("  clusters: " + ", ".join(f"{c['cluster']}({c['score']})" for c in rec["top_clusters"]))
        if rec["nearest_refs"]:
            print("  nearest refs: " + ", ".join(f"{r['ref']}({r['score']})" for r in rec["nearest_refs"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
