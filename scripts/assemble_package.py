#!/usr/bin/env python3
"""assemble_package.py - build the outward package repository from a declarative manifest.

The package that goes to GitHub is ASSEMBLED, never a permissions change on a source repo:
laplace's history carries sealed material, so the outward tree is a fresh repository holding
copies. This reads evidence/PACKAGE_2026-09-25/MANIFEST.json and applies three rules
mechanically, because a rule a human remembers is not a rule:

  MANUSCRIPTS travel as source (.tex/.md/.bib/.cls/.sty) plus ONE final PDF. Build
  intermediates and figure caches are the reason a manuscript directory reaches 77 MB.

  CODE travels as source only. runtime/, models/, stores/, work/, __pycache__ and the source
  repo's own .git never travel; the manifest records how to obtain them by name instead.

  THE PERIMETER is enforced here, not trusted: any source path under a sealed prefix is a
  refusal, not a warning, and the refusal names the path.

Every entry records its source repo's HEAD at copy time, so a claim in the package can be
traced to the commit it was taken from.

    scripts/laplace-python scripts/assemble_package.py            # dry run: what would travel
    scripts/laplace-python scripts/assemble_package.py --apply    # copy it
"""
from __future__ import annotations
import argparse, json, shutil, subprocess, sys
from pathlib import Path

REPOS = {
    "laplace": Path("/home/phujck/VScodeProjects/laplace"),
    "physics_paper_orchestra": Path("/home/phujck/VScodeProjects/physics_paper_orchestra"),
    "low_temp_submission": Path("/home/phujck/VScodeProjects/low_temp_submission"),
    "Hamiltonian_of_mean_force": Path("/home/phujck/VScodeProjects/Hamiltonian_of_mean_force"),
    "eigenengine-v2": Path("/home/phujck/VScodeProjects/eigenengine-v2"),
    "imaginarytimemethod": Path("/home/phujck/VScodeProjects/imaginarytimemethod"),
    "nested_hs_paper": Path("/home/phujck/VScodeProjects/nested_hs_paper"),
}
SEALED = ("soul/", "soul_corpus/", "soul_vectors/", "archive/soul_dump/", "profiles/",
          "life_corpus/", "collaborator_corpus/", "company/", "grants/", "evidence/call_")
TEXT = {".tex", ".md", ".bib", ".cls", ".sty"}
TEXT_FILE_CAP = 24 << 20  # the author overruled the 1 MB cap 2026-09-25: heavy manuscripts travel
CODE = {".py", ".pyi", ".js", ".mjs", ".ts", ".html", ".css", ".svg", ".toml", ".json", ".md", ".cfg", ".txt"}
NUMERICS = CODE | {".ipynb", ".pdf", ".png", ".bib", ".tex", ".sh", ".yaml", ".yml", ".csv", ".npz"}
SKIP_DIR = {"__pycache__", ".git", ".pytest_cache", ".ruff_cache", "runtime", "models",
            "stores", "work", "node_modules", ".venv", "_minted", "_build", "tmp", "build"}
JUNK = {".aux", ".log", ".out", ".toc", ".bbl", ".blg", ".fls", ".fdb_latexmk", ".synctex.gz",
        ".pyc", ".nav", ".snm", ".vrb", ".spl", ".bcf", ".run.xml"}
# No size ceiling. The author's concern (2026-09-25) is USELESS data - vendored runtimes, model
# weights, caches, build trees - not weight. Those are excluded by SKIP_DIR and JUNK above, which is
# the instrument that matters. The total is reported because it is useful to know, not to gate on.


def head(repo: Path) -> str:
    r = subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
                       capture_output=True, text=True)
    return r.stdout.strip() or "(not a git repo)"


def sealed_violation(rel: str) -> str | None:
    return next((s for s in SEALED if rel.startswith(s)), None)


def pick_files(src: Path, kind: str, include: list[str] | None,
               exclude: list[str] | None = None) -> list[Path]:
    ex = [str(src / e) for e in (exclude or [])]
    roots = [src / i for i in include] if include else [src]
    out: list[Path] = []
    for root in roots:
        if root.is_file():
            out.append(root); continue
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if any(part in SKIP_DIR for part in p.parts):
                continue
            if any(str(p).startswith(x) for x in ex):
                continue
            if p.suffix.lower() in JUNK:
                continue
            allow = {"theory": TEXT, "numerics": NUMERICS}.get(kind, CODE)
            if p.suffix.lower() in allow or p.name in ("Makefile", "requirements.txt"):
                if kind == "theory" and p.stat().st_size > TEXT_FILE_CAP:
                    continue
                out.append(p)
    if kind == "theory":
        pdfs = sorted([q for pat in ("*.pdf", "*/*.pdf", "*/*/*.pdf") for q in src.glob(pat)
                       if not any(str(q).startswith(x) for x in ex)],
                      key=lambda q: q.stat().st_mtime, reverse=True)
        if pdfs:
            out.append(pdfs[0])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--manifest", default="evidence/PACKAGE_2026-09-25/MANIFEST.json")
    a = ap.parse_args()

    man = json.loads(Path(a.manifest).read_text())
    target = Path(man["target"])
    heads = {name: head(p) for name, p in REPOS.items()}
    report, total, refusals = [], 0, []

    for kind in ("theory", "engines"):
        for e in man[kind]:
            repo_name, _, sub = e["src"].partition(":")
            repo = REPOS[repo_name]
            src = repo if sub == "." else repo / sub
            if not src.exists():
                refusals.append(f"{e['dest']}: source missing {src}")
                continue
            rel_to_repo = "" if sub == "." else sub + "/"
            v = sealed_violation(rel_to_repo)
            if v:
                refusals.append(f"{e['dest']}: PERIMETER - source under sealed prefix {v!r}")
                continue
            files = pick_files(src, e.get("kind", kind), e.get("include"), e.get("exclude"))
            bad = [f for f in files if sealed_violation(str(f.relative_to(repo)))]
            if bad:
                refusals.append(f"{e['dest']}: PERIMETER - {len(bad)} file(s) under a sealed prefix, first {bad[0]}")
                continue
            nbytes = sum(f.stat().st_size for f in files)
            total += nbytes
            report.append((e["dest"], repo_name, heads[repo_name], len(files), nbytes))
            if a.apply:
                base = src if not e.get("include") else src
                for f in files:
                    try:
                        rel = f.relative_to(base)
                    except ValueError:
                        rel = Path(f.name)
                    d = target / e["dest"] / rel
                    d.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, d)

    for e in man.get("data_for_checks", {}).get("files", []):
        repo_name, _, sub = e["src"].partition(":")
        src = REPOS[repo_name] / sub
        if not src.exists():
            refusals.append(f"{e['dest']}: check data missing {src}"); continue
        if sealed_violation(sub + "/"):
            refusals.append(f"{e['dest']}: PERIMETER"); continue
        fs = [src] if src.is_file() else [q for q in src.rglob("*") if q.is_file()
              and not any(x in SKIP_DIR for x in q.parts) and q.suffix.lower() not in JUNK]
        nb = sum(f.stat().st_size for f in fs); total += nb
        report.append((e["dest"] + "  [check data]", repo_name, heads[repo_name], len(fs), nb))
        if a.apply:
            for f in fs:
                rel = Path(f.name) if src.is_file() else f.relative_to(src)
                dd = target / e["dest"] / ("" if src.is_file() else str(rel))
                dd = (target / e["dest"]) if src.is_file() else dd
                dd.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dd)

    print(f"{'DEST':58} {'REPO':26} {'HEAD':10} {'FILES':>6} {'MB':>8}")
    for dest, repo, h, n, b in report:
        print(f"{dest[:58]:58} {repo[:26]:26} {h:10} {n:6} {b/1048576:8.2f}")
    print(f"\n{'TOTAL':58} {'':26} {'':10} {sum(r[3] for r in report):6} {total/1048576:8.2f} MB")
    if refusals:
        print("\nREFUSALS:")
        for r in refusals:
            print("  !", r)
    print("" if a.apply else "\n(dry run - nothing written)")
    if a.apply:
        prov = {"record": "package.provenance/1", "source_heads": heads,
                "entries": [{"dest": d, "repo": r, "head": h, "files": n, "bytes": b}
                            for d, r, h, n, b in report]}
        (target / "PROVENANCE.json").write_text(json.dumps(prov, indent=2))
        print(f"wrote {target}/PROVENANCE.json")
    return 1 if refusals else 0


if __name__ == "__main__":
    sys.exit(main())
