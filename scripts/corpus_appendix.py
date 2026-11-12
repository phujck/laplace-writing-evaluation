"""Appendix data for the EigenEngine core paper: anonymised author IDs, the author-author thematic
coupling matrix, and the cross-link edge list - the rich cross-linking detail, in a form the figures
and tables read. Names appear ONLY here (the appendix), never in the body or the data figures
(consent: collaborators are numbered in public, named only in the detail appendix).

Reuses scripts/author_theme_crosslink.py verbatim, so the coupling is the same mechanical metric.
Run: python scripts/corpus_appendix.py  ->  paper_eigen/_experiments/corpus_appendix.json
"""
from __future__ import annotations

import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import author_theme_crosslink as X  # noqa: E402

ME = "mccaul"  # the author; everyone else is a numbered collaborator


def _regraded():
    out = {}
    for f in sorted(glob.glob(os.path.join(ROOT, "collaborator_corpus/_structural/*_regraded.json"))):
        a = os.path.basename(f).replace("_regraded.json", "")
        if a == "eigen_operations":
            continue
        out[a] = json.load(open(f, encoding="utf-8"))
    return out


def main() -> int:
    themes_by_author = X._load_themes()
    idf = X._idf(themes_by_author)
    reg = _regraded()
    names = {a: reg[a].get("name", a) for a in reg}
    base = {}
    for a, d in reg.items():
        b = 0
        for g in d.get("generators", []):
            for r in g.get("rungs", []):
                if isinstance(r, dict):
                    b += len(r.get("papers") or r.get("members") or [])
        base[a] = b

    collabs = sorted((a for a in themes_by_author if a != ME), key=lambda a: -base.get(a, 0))
    ids = {ME: "A"}
    for i, a in enumerate(collabs, 1):
        ids[a] = str(i)
    order = [ME] + collabs
    id_order = [ids[a] for a in order]

    def vec(t):
        return X._vec(t["tokens"], idf)

    # author-author coupling = strongest cosine over any theme pair; remember the achieving link
    coupling = [[0.0] * len(order) for _ in order]
    best = {}
    for ia, a in enumerate(order):
        for ib, b in enumerate(order):
            if a == b:
                coupling[ia][ib] = 1.0
                continue
            mx, bl = 0.0, None
            for ta in themes_by_author[a]:
                va = vec(ta)
                for tb in themes_by_author[b]:
                    s = X._cos(va, vec(tb))
                    if s > mx:
                        mx, bl = s, (ta, tb, s, len(ta["papers"] & tb["papers"]))
            coupling[ia][ib] = round(mx, 3)
            best[(a, b)] = bl

    edges, seen = [], set()
    for a in order:
        for b in order:
            if a == b or (b, a) in seen:
                continue
            seen.add((a, b))
            bl = best.get((a, b))
            if not bl:
                continue
            edges.append({"i": ids[a], "j": ids[b], "i_theme": bl[0]["key"], "j_theme": bl[1]["key"],
                          "sim": round(bl[2], 3), "citation_free": bl[3] == 0})
    edges.sort(key=lambda e: -e["sim"])

    legend = [{"id": ids[a], "key": a, "name": names[a], "n_themes": len(themes_by_author[a]),
               "n_papers": base[a], "themes": [t["key"] for t in themes_by_author[a]]} for a in order]

    # ---- emit a LaTeX include with the legend, per-author themes, and top cross-links ----
    def esc(s: str) -> str:
        for a, b in [("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"), ("$", r"\$"),
                     ("#", r"\#"), ("_", r"\_"), ("{", r"\{"), ("}", r"\}"),
                     ("~", r"\textasciitilde{}"), ("^", r"\textasciicircum{}")]:
            s = s.replace(a, b)
        return s

    tex = [r"\begin{table}[h]\centering\small", r"\begin{tabular}{clrr}", r"\hline",
           r"ID & Author & Themes & Papers \\ \hline"]
    for L in legend:
        nm = esc(L["name"]) + (r" \textit{(the author)}" if L["id"] == "A" else "")
        tex.append(f"{L['id']} & {nm} & {L['n_themes']} & {L['n_papers']} \\\\")
    tex += [r"\hline", r"\end{tabular}",
            r"\caption{The corpus: the author (A) and seven collaborators, numbered by corpus size. "
            r"Names appear only in this appendix.}\label{tab:legend}", r"\end{table}", "",
            r"\noindent\textbf{Research themes by author.}", r"\begin{description}\small"]
    for L in legend:
        tex.append(rf"\item[{L['id']}] " + "; ".join(esc(t) for t in L["themes"]) + ".")
    tex += [r"\end{description}", "",
            r"\begin{table*}[t]\centering\small",
            r"\begin{tabular}{cc p{5.6cm} p{5.6cm} c}", r"\hline",
            r"pair & sim & theme (left) & theme (right) & link \\ \hline"]
    for e in edges[:12]:
        link = "citation-free" if e["citation_free"] else "shared paper"
        tex.append(f"{e['i']}--{e['j']} & {e['sim']:.2f} & {esc(e['i_theme'])} & "
                   f"{esc(e['j_theme'])} & {link} \\\\")
    tex += [r"\hline", r"\end{tabular}",
            r"\caption{The strongest thematic cross-link between each author pair (top twelve of 28). "
            r"Most connect researchers who share no paper.}\label{tab:edges}", r"\end{table*}"]
    open(os.path.join(ROOT, "paper_eigen", "_experiments", "appendix_tables.tex"),
         "w", encoding="utf-8").write("\n".join(tex) + "\n")

    report = {"id_order": id_order, "id_to_key": {ids[a]: a for a in order},
              "legend": legend, "coupling_matrix": coupling, "edges": edges}
    out = os.path.join(ROOT, "paper_eigen", "_experiments", "corpus_appendix.json")
    json.dump(report, open(out, "w", encoding="utf-8"), indent=2)

    print(f"authors: {len(order)}  (1 author + {len(collabs)} collaborators)")
    for L in legend:
        print(f"  {L['id']:>2}  {L['name'][:26]:<26} themes={L['n_themes']:>2} papers={L['n_papers']:>4}  :: "
              + "; ".join(t[:34] for t in L["themes"][:4]) + (" ..." if len(L["themes"]) > 4 else ""))
    print(f"\ntop cross-links ({len(edges)} author-pairs total):")
    for e in edges[:12]:
        tag = "citation-free" if e["citation_free"] else "shared paper(s)"
        print(f"  {e['i']}<->{e['j']}  sim={e['sim']:.2f}  [{tag}]  {e['i_theme'][:30]} | {e['j_theme'][:30]}")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
