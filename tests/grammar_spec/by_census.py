"""Measure what every door actually does with the request's writer field, `by`.

`grammar.BY_AT_DOORS` DECLARES it, one of four statuses per operation; this script is the
measurement that the declaration is true, and `test_grammar.py` runs the same comparison as
a test so the two cannot drift.  The declaration exists because the owners disagree with
each other: one door refuses `by` outright, another has it overwritten with a constant
before the owner sees it, and most simply lose it.  A lane must not rediscover that one
refusal at a time.

Run from the tree being measured (the live tree, or a lane's worktree after INSTALL):

    scripts/laplace-python evidence/WRITING_RECONCILIATION_2026-10-02/grammar/by_census.py \
        [tree]

Three facts are read from the tree, never from this file:

  1. THE OVERWRITE SET - the operations listed on the `if operation in {...}` line that
     precedes `payload["by"] = "eigen:session"` in ``src/laplace/native/tools.py``.  Those
     doors replace the caller's writer with one constant name, so the contract declaring
     `by` buys the caller no attribution at all.
  2. THE CONTRACT - whether each operation's generated input schema declares `by`
     (``writing_contracts.exact_contract``, plus ``concepts_surface.operation_contract``
     for the 13 concept_change operations, which validate against their own table).
  3. THE STRICT DOORS - every ``set(payload)`` unknown-key site in ``src/laplace``.  Each
     one must be CITED in the declaration (in a status reason, or in the dropped-by-default
     reason), so a new strict door cannot appear without the grammar naming it.

Exit status is 1 when the declaration and the measurement disagree.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CAMPAIGN_BASE = "706a8204"   # the commit the declaration's citations are coordinates in
# Resolving a citation against a frozen blob is a shim, so it carries a shim's expiry: this
# census translates a moved strict door back to its base line, which means it cannot notice a
# door that moved AND changed meaning.  Retire the translation when the sites are anchored.
CAMPAIGN_BASE_EXPIRY = ("retire when the strict unknown-key sites are cited by anchor rather "
                        "than by line, on WRITING-RECONCILIATION replay parity; "
                        "review 2026-11-01")
OVERWRITE_MARK = 'payload["by"] = "eigen:session"'
SET_PAYLOAD = re.compile(r"set\(payload\)")
QUOTED = re.compile(r"""["']([A-Za-z_][A-Za-z0-9_]*)["']""")
CITATION = re.compile(r"(?:([a-z_]+\.py))?:(\d+)(?:-(\d+))?")


def cited_sites(text: str) -> set[str]:
    """Every `<file>.py:<line>` a declaration's reasons cite, ranges expanded.

    A citation may carry the file (`project_structure.py:746`) or continue the last file
    named (`... and :710 raises`), and may be a range (`writing_style.py:371-372`), which
    is how a two-line check is cited.  Written once here because the closed-set check below
    is only as good as its reading of the citations.
    """
    out: set[str] = set()
    current = ""
    for match in CITATION.finditer(text):
        if match.group(1):
            current = match.group(1)
        if not current:
            continue
        first = int(match.group(2))
        last = int(match.group(3) or first)
        for line in range(first, max(first, last) + 1):
            out.add("%s:%d" % (current, line))
    return out


def _grammar():
    """The module that owns the `by` census: the installed native declaration table
    (laplace.native.declarations, where it moved on 2026-10-21), else this packet's copy."""
    try:
        from laplace.native import declarations as mod    # type: ignore
        if hasattr(mod, "BY_AT_DOORS"):
            return mod
    except Exception:
        pass
    sys.path.insert(0, str(HERE))
    import grammar as mod                     # type: ignore
    assert hasattr(mod, "BY_AT_DOORS"), (
        "%r is not the grammar module; a directory named `grammar` is shadowing it"
        % (getattr(mod, "__file__", mod),))
    return mod


def operations(mapping: Path) -> list[str]:
    """Every audited operation name, from the mapping's own rows (the base name only:
    a sub-verb row spells `structure_change operation=plan`)."""
    with mapping.open() as handle:
        rows = list(csv.DictReader(handle))
    return sorted({str(row["operation"]).split()[0] for row in rows if row.get("operation")})


def overwrite_set(tree: Path) -> tuple[set[str], str]:
    """The operations whose `by` the module door replaces, read off the live line."""
    path = tree / "src" / "laplace" / "native" / "tools.py"
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for number, line in enumerate(lines, 1):
        if OVERWRITE_MARK in line.replace("'", '"').replace(" ", " "):
            guard = lines[number - 2] if number >= 2 else ""
            names = set(QUOTED.findall(guard)) if "operation in" in guard else set()
            return names, "writing_tools.py:%d" % (number - 1)
    return set(), ""


def declares_by(tree: Path, ops: list[str]) -> dict[str, bool]:
    """Does each operation's generated input schema declare `by`?"""
    sys.path.insert(0, str(tree / "src"))
    from laplace.native import contracts as wc        # noqa: PLC0415
    out: dict[str, bool] = {}
    for operation in ops:
        try:
            schema = (wc.exact_contract(operation, permitted=True) or {}).get("input") or {}
        except Exception:
            out[operation] = False
            continue
        variants = schema.get("oneOf") or [schema]
        keys: set[str] = set()
        for variant in variants:
            keys |= set(variant.get("properties") or {})
        # `additionalProperties: true` is NOT a declaration: `style`'s schema takes anything
        # and its owner keeps nine named keys (project_work.py:163), so the writer is lost.
        out[operation] = "by" in keys
    try:
        from laplace.research import concepts_surface as cs     # noqa: PLC0415
        table = (cs.operation_contract() or {}).get("operations") or {}
        if table and all("by" in (rule.get("properties") or {}) for rule in table.values()):
            out["concept_change"] = True
    except Exception:
        pass
    return out


def _base_text(tree: Path, rel: str, base: str) -> str:
    """One file's text at `base`, read out of git rather than from disk."""
    done = subprocess.run(["git", "-C", str(tree), "show", "%s:%s" % (base, rel)],
                          capture_output=True)
    if done.returncode != 0:
        return ""
    return done.stdout.decode("utf-8", "replace")


def strict_sites(tree: Path, base: str = CAMPAIGN_BASE) -> list[str]:
    """Every ``set(payload)`` unknown-key site in src/laplace, reported at the coordinate
    THE DECLARATION USES: a line number in the campaign base.

    A lane that edits an owner moves the strict door it never touched.  Measured on the
    identity x contract synthesis: `concepts_surface.py:1021` -> `:1073` and
    `writing_style.py:371-372` -> `:380-381`, three doors whose lines are byte-identical to
    the base, which the closed-set check below reported as three uncited new strict doors.
    So a site whose exact line text occurs exactly once at `base` is reported at THAT line;
    any other site is reported at its own line, which is what a genuinely new strict door
    looks like and still fails the check.  The translation is the measurement, not an
    exemption: `translated` in the report names every site that moved.
    """
    out: list[str] = []
    for path in sorted((tree / "src" / "laplace").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(tree).as_posix()
        base_lines: list[str] | None = None
        for number, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if SET_PAYLOAD.search(line) and ("-" in line or "unknown" in line):
                if base_lines is None:
                    base_lines = _base_text(tree, rel, base).splitlines()
                at = [n for n, text in enumerate(base_lines, 1) if text == line]
                out.append("%s:%d" % (path.name, at[0] if len(at) == 1 else number))
    return out


def census(tree: Path, mapping: Path) -> dict:
    g = _grammar()
    ops = operations(mapping)
    overwritten, overwrite_site = overwrite_set(tree)
    declared = declares_by(tree, ops)
    cited = cited_sites(" ".join([reason for _status, reason in g.BY_AT_DOORS.values()]
                                 + [g.BY_DEFAULT_STATUS[1]]))
    sites = strict_sites(tree)
    disagreements: list[str] = []

    observed: dict[str, str] = {}
    for operation in ops:
        if operation in overwritten:
            observed[operation] = "overwritten"
        else:
            status, _reason = g.by_at(operation)
            # `refused` and `dropped` are facts about a door's key check, which this census
            # verifies through its CITATION (below) rather than by calling the door: a probe
            # would have to write.  The contract is checked here, because a declaration of
            # `by` with no overwrite would make the status `declared`.
            observed[operation] = "declared" if (
                status == "dropped" and declared.get(operation)) else status

    for operation in ops:
        status, _reason = g.by_at(operation)
        if status != observed[operation]:
            disagreements.append("%s: declared %s, measured %s"
                                 % (operation, status, observed[operation]))
    for operation in sorted(overwritten - set(ops)):
        disagreements.append("%s: the door overwrites `by` but the mapping has no such "
                             "operation" % (operation,))
    for site in sites:
        if site not in cited:
            disagreements.append("%s validates unknown payload keys and the declaration "
                                 "does not cite it" % (site,))
    for operation, status_reason in sorted(g.BY_AT_DOORS.items()):
        status, reason = status_reason
        if status not in g.BY_STATUSES:
            disagreements.append("%s: %r is not one of %r" % (operation, status,
                                                              g.BY_STATUSES))
        if not cited_sites(reason):
            disagreements.append("%s: its reason cites no owner file:line" % (operation,))
        if operation not in ops:
            disagreements.append("%s: declared, but it is not an audited operation"
                                 % (operation,))

    counts: dict[str, int] = {}
    for operation in ops:
        counts[observed[operation]] = counts.get(observed[operation], 0) + 1
    return {"tree": str(tree), "operations": len(ops), "overwrite_site": overwrite_site,
            "overwritten": sorted(overwritten), "declares_by_in_contract":
            sorted(name for name, yes in declared.items() if yes),
            "strict_sites": sites, "counts": counts,
            "by_status": observed, "disagreements": disagreements}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tree", nargs="?", default=".", help="tree whose owners are measured")
    ap.add_argument("--mapping", default=str(HERE / "mapping.csv"))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    report = census(Path(args.tree).resolve(), Path(args.mapping))
    if args.json:
        print(json.dumps(report, indent=1, sort_keys=True))
    else:
        print("by census  tree %s  %d operations" % (report["tree"], report["operations"]))
        print("  overwritten at %s: %s" % (report["overwrite_site"],
                                           ", ".join(report["overwritten"])))
        print("  declares `by` in its contract: %s"
              % (", ".join(report["declares_by_in_contract"]) or "none"))
        print("  strict unknown-key sites (%d): %s"
              % (len(report["strict_sites"]), ", ".join(report["strict_sites"])))
        print("  status counts: %s" % (report["counts"],))
        for line in report["disagreements"]:
            print("  DISAGREES  " + line)
        print("DECLARED `by` STATUS MATCHES THE DOORS"
              if not report["disagreements"]
              else "DISAGREEMENTS: %d" % len(report["disagreements"]))
    return 0 if not report["disagreements"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
