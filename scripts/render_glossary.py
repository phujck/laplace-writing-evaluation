"""Render GLOSSARY.md for a project corpus FROM the conceptric's def-node registry.

The glossary is a VIEW: ``def:`` nodes carry ``projection.term`` / ``aliases`` /
``deprecated_aliases`` (enforced by the ``glossary`` verify gate), and this script projects
them to a human-readable table. Never hand-edit the output - rewire the conceptric.

Usage: python scripts/render_glossary.py <corpus-name> [<out-path>]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from laplace.research import corpus_ingest as ci
from laplace.web.scanner import _repo_root


def first_sentence(text: str, cap: int = 260) -> str:
    text = " ".join((text or "").split())
    for stop in (". ", ".$ ", "; "):
        i = text.find(stop)
        if 40 < i < cap:
            return text[: i + 1]
    return text[:cap] + ("..." if len(text) > cap else "")


def render(corpus: str) -> str:
    rr = _repo_root()
    net = ci.corpus_network(ci.resolve_corpus(rr, corpus), repo_root=rr, name=corpus)
    nodes = net["nodes"]

    def proj_of(nd):
        return nd.get("projection") or (nd.get("meta") or {}).get("projection") or {}

    rows, deprecated_rows = [], []
    for nid, nd in sorted(nodes.items()):
        if not nid.startswith("def:"):
            continue
        p = proj_of(nd)
        term = p.get("term") or nid.split(":", 1)[1].replace("-", " ")
        rows.append((term, nid, first_sentence(nd.get("essence") or ""),
                     ", ".join(p.get("aliases") or []),
                     bool(p.get("retired"))))
        for dep in p.get("deprecated_aliases") or []:
            deprecated_rows.append((dep, term, nid))

    lines = [
        f"# Glossary — {corpus}",
        "",
        "**Generated from the conceptric** (`def:` nodes' `projection.term` registry; the",
        "`glossary` verify gate enforces coverage, uniqueness, and retired-vocabulary hygiene).",
        "Do not hand-edit — rewire the conceptric and re-render:",
        f"`python scripts/render_glossary.py {corpus}`.",
        "",
        "| Term | Definition | Aliases | Node |",
        "|---|---|---|---|",
    ]
    for term, nid, defn, aliases, retired in sorted(rows, key=lambda r: r[0].lower()):
        mark = " *(retired)*" if retired else ""
        defn = defn.replace("|", "\\|")
        lines.append(f"| **{term}**{mark} | {defn} | {aliases} | `{nid}` |")

    if deprecated_rows:
        lines += ["", "## Deprecated vocabulary", "",
                  "Terms retired from live use; the gate fails any non-retired node whose",
                  "essence still uses them.", "",
                  "| Deprecated | Use instead | Owning def |", "|---|---|---|"]
        for dep, term, nid in sorted(deprecated_rows):
            lines.append(f"| ~~{dep}~~ | **{term}** | `{nid}` |")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    corpus = sys.argv[1] if len(sys.argv) > 1 else "subset-sum-itqde"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    text = render(corpus)
    if out is None:
        rr = _repo_root()
        troot = ci.resolve_corpus(rr, corpus)
        base = Path(troot)
        base = base if base.is_dir() else base.parent
        # project root = the directory above source/ when the corpus points inside it
        if base.name == "source":
            base = base.parent
        out = base / "GLOSSARY.md"
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out} ({text.count(chr(10))} lines)")
