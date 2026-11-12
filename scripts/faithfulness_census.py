#!/usr/bin/env python3
"""The faithfulness census bench - does each organ DO what it claims?

An organ is a module that declares a function in its own header. The census asks
one question of each: is the claim what happens? The answer is a trichotomy -
fully-functional (claim and behaviour agree), almost-functional (the mechanism
runs, some declared leg does not), dead (the claimed function demonstrably does
not happen anywhere in production).

Half that question is mechanical and this bench re-derives it, offline, from the
tree as it stands:

  * import-reachability - which production files (src/, scripts/, .claude/)
    actually import the module. Tests do not count: a module exercised only by
    its own test is unreached.
  * call-site counts - production importers, plus the weaker mention count, plus
    the test importers, so a claim of "zero production call sites" is a number
    and not an assertion.
  * store-written-recently - the store paths the module's own source names, which
    of them exist, and how old the freshest one is. A write-only organ with a
    stale store reads the same as a live one until the mtime is looked at.

The other half is a judgement - whether the module's HEADER claim matches what
those numbers mean - and this bench does not make it. It prints the trichotomy
skeleton (mechanical class per organ, beside the prior banked verdict where one
exists) for the next run to judge over, and flags where the mechanics and the
prior verdict diverge, because a divergence is either drift in the tree or an
error in the bank and both want a reader.

Prior verdicts are rows, not prose: evidence/FAITHFULNESS_CENSUS_2026-08-21/
verdicts.jsonl, one typed row per organ. This render names that row-source; it
goes stale the moment the rows move.

Usage:
    python3 scripts/faithfulness_census.py                    # the whole skeleton
    python3 scripts/faithfulness_census.py --diverged-only    # only the seams
    python3 scripts/faithfulness_census.py --organ ruling_recall --organ dreamer
    python3 scripts/faithfulness_census.py --json > /tmp/census.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PRIOR_STORE = "evidence/FAITHFULNESS_CENSUS_2026-08-21/verdicts.jsonl"

# Where organs live.
# The subsystem packages that hold organs (laplace's top-level modules moved into them on 2026-10-21).
ORGAN_DIRS = tuple("src/laplace/" + package for package in (
    "engine", "pipeline", "manuscript", "projects", "work", "research", "representation", "writing", "native", "web", "desktop"))
# Where a production call site may live. tests/ is deliberately absent.
PROD_DIRS = ("src/laplace", "scripts", ".claude/workflows")
TEST_DIRS = ("tests",)
# Never walked: retired trees and the census's own evidence.
SKIP_PARTS = {".git", "archive", "evidence", "node_modules", "__pycache__", ".venv"}

CODE_SUFFIXES = {".py", ".js", ".mjs"}
STORE_SUFFIXES = (".jsonl", ".json", ".npz", ".yaml", ".yml", ".md")

# from <pkg> import a, b  /  import a, b  (indented in-function imports included)
_IMPORT_RE = re.compile(r"^[ \t]*(?:from[ \t]+([\w.]+)[ \t]+)?import[ \t]+([^\n#]+)", re.M)
# laplace.pipeline.foo / laplace.foo  (attribute-qualified reach, incl. from JS shell-outs)
_DOTTED_RE = re.compile(r"\blaplace(?:\.pipeline)?\.(\w+)\b")
# String literals that look like a store path.
_LITERAL_RE = re.compile(r"""["']([^"'\n]{3,120})["']""")
# A module-level constant, and the names that mean "this is my store".
_CONST_RE = re.compile(r"""^([A-Z][A-Z0-9_]*)\s*=\s*["']([^"'\n]+)["']""", re.M)
_STORE_CONST_RE = re.compile(r"(FILE|STORE|LEDGER|PATH|CACHE|INDEX|LOG|REL)$")


def _walk(root: Path, rel_dirs: tuple[str, ...]) -> list[Path]:
    out: list[Path] = []
    for rel in rel_dirs:
        base = root / rel
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if p.suffix not in CODE_SUFFIXES or not p.is_file():
                continue
            if SKIP_PARTS & set(p.relative_to(root).parts):
                continue
            out.append(p)
    return out


def discover_organs(root: Path) -> dict[str, str]:
    """repo-relative module path -> organ name, for every organ module on disk.

    Keyed by PATH, not name: src/laplace/engine/detector_organs.py (the pure reader) and
    src/laplace/pipeline/detector_organs.py (the runner) are two organs with two
    claims, and a name-keyed census silently drops one of them.
    """
    organs: dict[str, str] = {}
    for rel in ORGAN_DIRS:
        base = root / rel
        if not base.is_dir():
            continue
        for p in sorted(base.glob("*.py")):
            if p.name.startswith("_"):
                continue
            organs[str(p.relative_to(root))] = p.stem
    return organs


def _referenced_names(text: str) -> Counter:
    """Module basenames this file imports or reaches by dotted path.

    Records the bare leaf AND, where the import names the pipeline package, the
    qualified `pipeline.<leaf>`, so an ambiguous name can be split by package.
    """
    hits: Counter = Counter()

    def _add(leaf: str, pkg: str) -> None:
        if not leaf.isidentifier():
            return
        hits[leaf] += 1
        if "pipeline" in pkg.split("."):
            hits[f"pipeline.{leaf}"] += 1

    for pkg, names in _IMPORT_RE.findall(text):
        pkg = pkg or ""
        tail = pkg.rsplit(".", 1)[-1]
        if tail:
            _add(tail, pkg.rsplit(".", 1)[0] if "." in pkg else "")
        for chunk in names.split(","):
            token = chunk.strip().split(" as ")[0].strip()
            if not token or token == "*":
                continue
            _add(token.rsplit(".", 1)[-1], pkg)
    for m in _DOTTED_RE.finditer(text):
        _add(m.group(1), "pipeline" if ".pipeline." in m.group(0) else "")
    return hits


def _reach_count(hits: Counter, name: str, is_pipeline: bool, ambiguous: bool) -> int:
    """How far this file's imports reach THIS module, splitting ambiguous names."""
    if not ambiguous:
        return hits.get(name, 0)
    qualified = hits.get(f"pipeline.{name}", 0)
    return qualified if is_pipeline else max(0, hits.get(name, 0) - qualified)


def scan_reach(root: Path, organs: dict[str, str]) -> dict[str, dict]:
    """Per organ module: which production / test files import it, plus mentions."""
    reach = {
        module: {"prod_importers": [], "test_importers": [], "prod_mentions": 0}
        for module in organs
    }
    ambiguous = {n for n, c in Counter(organs.values()).items() if c > 1}
    word_res = {name: re.compile(rf"\b{re.escape(name)}\b") for name in set(organs.values())}

    for path in _walk(root, PROD_DIRS):
        rel = str(path.relative_to(root))
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        hits = _referenced_names(text)
        for module, name in organs.items():
            if rel == module:  # a module never reaches itself
                continue
            if _reach_count(hits, name, module.startswith("src/laplace/pipeline/"), name in ambiguous):
                reach[module]["prod_importers"].append(rel)
            elif word_res[name].search(text):
                reach[module]["prod_mentions"] += 1

    for path in _walk(root, TEST_DIRS):
        rel = str(path.relative_to(root))
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        hits = _referenced_names(text)
        for module, name in organs.items():
            if _reach_count(hits, name, module.startswith("src/laplace/pipeline/"), name in ambiguous):
                reach[module]["test_importers"].append(rel)
    return reach


def declared_stores(root: Path, module_rel: str) -> list[dict]:
    """Store paths the module's own source names, with existence and age.

    Only ROOT-ANCHORED literals are scored: a bare filename like
    "node_index.json" is a per-project store whose home is a manuscript dir, not
    the repo root, so resolving it here would report a false absence. Those are
    carried as project-relative and left out of the freshness call.
    """
    path = root / module_rel
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    now = time.time()
    declared = {v for k, v in _CONST_RE.findall(text) if _STORE_CONST_RE.search(k)}
    seen: dict[str, dict] = {}
    for lit in _LITERAL_RE.findall(text):
        lit = lit.strip()
        if not lit.endswith(STORE_SUFFIXES) or " " in lit:
            continue
        if lit.startswith(("http", "/usr", "/root")) or "{" in lit or "%" in lit or "*" in lit:
            continue
        # A store constant is resolved against the root AND against the module's
        # own dir - src/laplace/pipeline/canon/skill_residuals.json is named bare by the
        # organ that owns it, and a root-only probe would report a false absence.
        cand = Path(lit) if lit.startswith("/") else (root / lit)
        if not cand.is_file() and not lit.startswith("/"):
            sibling = path.parent / lit
            if sibling.is_file():
                cand = sibling
            elif "/" not in lit:  # a bare store name, homed somewhere in the package
                found = next((root / "src/laplace").glob(f"**/{lit}"), None)
                if found is not None and found.is_file():
                    cand = found
        exists = cand.is_file()
        # Scored only when the root can answer for it: it resolves here, or the
        # module names it as its OWN store constant and so should have written it.
        scored = exists or lit in declared
        row = {"path": lit, "exists": exists, "age_days": None, "scored": scored,
               "declared_const": lit in declared}
        if exists:
            row["age_days"] = round((now - cand.stat().st_mtime) / 86400.0, 1)
        elif not scored:
            row["why"] = "unresolved here - a project-relative store or a name fragment"
        seen[lit] = row
    return sorted(seen.values(), key=lambda r: (not r["scored"], not r["exists"], r["path"]))


def mechanical_class(row: dict, stale_days: float) -> str:
    """The mechanical half only. Never a verdict - a skeleton to judge over."""
    if row["n_prod_importers"] == 0:
        return "unreached"
    scored = [s for s in row["stores"] if s.get("scored")]
    live = [s for s in scored if s["exists"]]
    if not scored:
        return "reached-no-store-declared"
    if not live:
        return "reached-store-absent"
    freshest = min(s["age_days"] for s in live)
    return "reached-store-fresh" if freshest <= stale_days else "reached-store-stale"


def load_prior(root: Path, rel: str) -> dict[str, dict]:
    store = root / rel
    if not store.is_file():
        return {}
    prior: dict[str, dict] = {}
    for line in store.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("record") == "organ-verdict":
            prior[r.get("module") or r.get("organ", "")] = r
    return prior


def diverges(prior_verdict: str, mech: str, n_prod: int, dead_reach_floor: int) -> str:
    """Where the mechanics and the banked verdict disagree, and how.

    A dead organ with ONE production importer is not a divergence - that is the
    census's own finding (reach is not use: the importer is the relic transport,
    or a caller nothing calls). Only a dead organ that has since grown real reach
    is worth a reader.
    """
    if not prior_verdict:
        return "no-prior"
    if mech == "unreached" and prior_verdict == "fully-functional":
        return "prior-fully-but-now-unreached"
    if prior_verdict == "dead" and n_prod >= dead_reach_floor:
        return "prior-dead-but-reach-grew"
    if mech in {"reached-store-absent", "reached-store-stale"} and prior_verdict == "fully-functional":
        return "prior-fully-but-store-cold"
    return ""


def build(root: Path, args) -> dict:
    organs = discover_organs(root)
    if args.organ:
        wanted = set(args.organ)
        organs = {k: v for k, v in organs.items() if v in wanted}
        missing = wanted - set(organs.values())
        if missing:
            print(f"unknown organ(s): {sorted(missing)}", file=sys.stderr)
    reach = scan_reach(root, organs)
    prior = load_prior(root, args.prior)

    rows = []
    for module, name in sorted(organs.items(), key=lambda kv: (kv[1], kv[0])):
        r = reach[module]
        p = prior.get(module, {})
        row = {
            "organ": name,
            "module": module,
            "n_prod_importers": len(r["prod_importers"]),
            "prod_importers": sorted(r["prod_importers"])[: args.cap],
            "n_test_importers": len(r["test_importers"]),
            "prod_mentions_only": r["prod_mentions"],
            "stores": declared_stores(root, module),
            "prior_verdict": p.get("verdict", ""),
            "prior_defects": p.get("defect_count", 0) if p else 0,
        }
        row["mechanical"] = mechanical_class(row, args.stale_days)
        row["divergence"] = diverges(
            row["prior_verdict"], row["mechanical"], row["n_prod_importers"], args.dead_reach_floor
        )
        rows.append(row)

    return {
        "record": "faithfulness-census-bench",
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "root": str(root),
        "prior_store": args.prior if (root / args.prior).is_file() else "",
        "stale_days": args.stale_days,
        "n_organs": len(rows),
        "mechanical_counts": dict(Counter(r["mechanical"] for r in rows)),
        "prior_counts": dict(Counter(r["prior_verdict"] for r in rows if r["prior_verdict"])),
        "rows": rows,
    }


def render(out: dict, diverged_only: bool) -> str:
    lines: list[str] = []
    lines.append(f"faithfulness census bench - {out['ran_at']} - {out['n_organs']} organs")
    lines.append(f"  prior rows: {out['prior_store'] or '(none banked)'}")
    lines.append(f"  mechanical: {out['mechanical_counts']}")
    lines.append(f"  prior:      {out['prior_counts'] or '(none)'}")
    lines.append("")
    lines.append(f"{'organ':30} {'prod':>4} {'test':>4} {'mechanical':26} {'prior':18} divergence")
    lines.append("-" * 104)
    for r in out["rows"]:
        if diverged_only and not r["divergence"]:
            continue
        lines.append(
            f"{r['organ'][:30]:30} {r['n_prod_importers']:>4} {r['n_test_importers']:>4} "
            f"{r['mechanical']:26} {r['prior_verdict'] or '-':18} {r['divergence']}"
        )
    lines.append("")
    lines.append(
        "the mechanical column is import-reachability + store freshness only; "
        "the verdict is a judgement over the module's own claim and is banked as a row."
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="re-derive the mechanical half of the faithfulness census")
    ap.add_argument("--root", default=str(REPO_ROOT), help="repo root (default: this checkout)")
    ap.add_argument("--organ", action="append", default=[], help="restrict to this organ (repeatable)")
    ap.add_argument("--prior", default=PRIOR_STORE, help=f"banked verdict rows (default: {PRIOR_STORE})")
    ap.add_argument("--stale-days", type=float, default=30.0, help="a store older than this reads stale")
    ap.add_argument("--cap", type=int, default=6, help="max importer paths carried per row")
    ap.add_argument(
        "--dead-reach-floor",
        type=int,
        default=3,
        help="production importers a banked-dead organ needs before its reach reads as grown",
    )
    ap.add_argument("--diverged-only", action="store_true", help="print only mechanics-vs-prior seams")
    ap.add_argument("--json", action="store_true", help="emit the typed payload instead of the table")
    args = ap.parse_args(argv)

    out = build(Path(args.root).resolve(), args)
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
    else:
        print(render(out, args.diverged_only))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
