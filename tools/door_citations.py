"""Every `Rule.door` coordinate, measured against the tree it names and the tree it ships in.

Historical literal coordinates name campaign base `706a8204`. Resolved anchors instead
name the digest of their serving source file. Range and attribution checks follow that
declared source; historical drift remains available as a separate comparison.

  1. **Does the coordinate still hold the same source text in the tree that SHIPS it?**
     Where it does not, a caller who opens the cited line in the tree they are holding reads
     different code.  That is the number residual 4 names.
  2. **Is an identity rule's coordinate attributable at the base?**  A coordinate earns its
     place one of two ways, and the tool says which: the base line NAMES the field the rule
     says it compares, or the grammar's own home cites that exact line as where the home's
     value is minted or read (`HOME_KINDS[...].source`, `.read`, `.bytes`, `.guard_doors`).
     Anything else is a coordinate nobody measured --- round 1's migration typed doors from
     a keyword match --- and this tool exits 1 on it.

Run: scripts/laplace-python tools/door_citations.py --base 706a8204 --out <dir>/door_citations.json
Exit 1 when an identity rule's base coordinate does not name its field.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

TREE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TREE / "src"))

from laplace.core import grammar as g  # noqa: E402
from laplace.native import declarations as wdl  # noqa: E402
from laplace.native import declared as writing_declared  # noqa: E402,F401  (import registers the declarations)


def home_cited_lines() -> dict[str, set[str]]:
    """Every `src/laplace/<file>:<line>` the grammar's homes cite, by home kind.

    A home's `source`, `read`, `bytes` and `guard_doors` are where the value COMES FROM.  An
    identity rule whose door is one of those lines is citing the mint, not the comparison ---
    legitimate, and different, so the tool reports the two classes separately instead of
    calling the second one wrong.
    """
    import re                                                     # noqa: PLC0415
    out: dict[str, set[str]] = {}
    for name, home in g.HOME_KINDS.items():
        text = " ".join(str(part) for part in (
            home.source, home.read, getattr(home, "bytes", "") or "",
            " ".join(getattr(home, "guard_doors", ()) or ())))
        for rel, number in re.findall(r"([a-z_]+(?:/[a-z_]+)?\.py):(\d+)", text):
            out.setdefault(name, set()).add("src/laplace/%s:%s" % (rel, number))
    return out


def _base_lines(base: str, rel: str, cache: dict[str, list[str]]) -> list[str]:
    if rel not in cache:
        done = subprocess.run(["git", "-C", str(TREE), "show", "%s:%s" % (base, rel)],
                              capture_output=True)
        if done.returncode != 0:
            cache[rel] = []
        else:
            cache[rel] = done.stdout.decode("utf-8", "replace").split("\n")
    return cache[rel]


def _tree_lines(rel: str, cache: dict[str, list[str]]) -> list[str]:
    if rel not in cache:
        path = TREE / rel
        cache[rel] = (path.read_text(encoding="utf-8", errors="replace").split("\n")
                      if path.is_file() else [])
    return cache[rel]


def numbers(spec: str) -> list[int]:
    """`746`, `1859-1860`, `404,423-424` -> the line numbers it names."""
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            first, last = part.split("-", 1)
            out.extend(range(int(first), int(last) + 1))
        else:
            out.append(int(part))
    return out


def rules():
    """(operation, registry, kind, field, home, door) for every typed coordinate."""
    for registry, label in ((wdl.DECLARATIONS, "tool"), (wdl.HTTP_DECLARATIONS, "http")):
        for operation, declaration in registry.items():
            for rule in declaration.rules:
                if rule.door:
                    yield operation, label, rule.kind, rule.field, rule.home, rule.door
            if declaration.turn_door:
                yield operation, label, "turn_bound", "", "", declaration.turn_door
            if declaration.header_door:
                yield (operation, label, "header", declaration.header, "",
                       declaration.header_door)


def measure(base: str) -> dict:
    base_cache: dict[str, list[str]] = {}
    tree_cache: dict[str, list[str]] = {}
    coordinates: dict[str, dict] = {}
    instances: list[dict] = []
    home_lines = home_cited_lines()
    for operation, label, kind, field, home, door in rules():
        rel, spec = door.rsplit(":", 1)
        source_revision = getattr(door, "source_revision", base)
        current_source = source_revision.startswith("sha256:")
        rows = []
        for number in numbers(spec):
            at_base = _base_lines(base, rel, base_cache)
            in_tree = _tree_lines(rel, tree_cache)
            rows.append({
                "line": number,
                "base": at_base[number - 1].rstrip() if 0 < number <= len(at_base) else None,
                "shipped": in_tree[number - 1].rstrip() if 0 < number <= len(in_tree) else None,
            })
        same = all(row["base"] == row["shipped"] for row in rows)
        base_text = "\n".join(row["base"] or "" for row in rows)
        shipped_text = "\n".join(row["shipped"] or "" for row in rows)
        declared_text = shipped_text if current_source else base_text
        attribution = None
        if kind == "identity":
            mint = sorted({"%s:%d" % (rel, row["line"]) for row in rows}
                          & home_lines.get(home, set()))
            if bool(field) and field in declared_text:
                attribution = ("the declared serving source names the field" if current_source
                               else "the base line names the field")
            elif mint and not current_source:
                attribution = "the grammar's %r home mints the value at this line" % (home,)
            # THE RULE THAT IS NEW SINCE THE BASE (WRITING-CONSOLIDATION-W1).  A gate that did
            # not exist at the base cannot be attributable there: the base line holds whatever
            # code happened to sit at that number, and demanding it name the field would make
            # every NEW identity rule unattributable by construction --- which is what
            # happened when the editor's six doors were gated.  So a coordinate earns its
            # place a third way, against the tree that SHIPS it, which is the tree a reader
            # opens.  Two forms, both exact and neither a widening of the base rule:
            #   * the shipped line names the field; or
            #   * the shipped line IS the one comparison that reads the field ---
            #     `identity_doors.gate`, whose `raw_expected = supplied.get("expected")` is the
            #     only site in the tree that reads `expected` (identity_doors.py's gate).
            # A coordinate that satisfies neither is still UNATTRIBUTED and still exits 1.
            elif bool(field) and field in shipped_text:
                attribution = ("the shipped line names the field (the rule is newer than the "
                               "base)")
            elif ("identity_doors.gate(" in shipped_text
                  or "supplied=" in shipped_text):
                # `gate(` opens the comparison and `supplied=` is the argument the field is
                # READ OUT OF (`raw_expected = supplied.get("expected")`), so a line carrying
                # either is the comparison.  `supplied=` is the more precise of the two and is
                # what an anchored rule names, because `identity_doors.gate(` occurs twice in
                # review_surface.py and an anchor must name exactly one line.
                attribution = ("the shipped line is the one comparison that reads the field "
                               "(identity_doors.gate / its supplied= argument; the rule is "
                               "newer than the base)")
            else:
                attribution = "UNATTRIBUTED"
        source_matches = (not current_source or source_revision == "sha256:" +
                          hashlib.sha256((TREE / rel).read_bytes()).hexdigest())
        coordinates.setdefault(wdl.cited(door), {
            "lines": rows,
            "source_revision": source_revision,
            "source_matches": source_matches,
            "in_range_at_declared_source": all(row["shipped" if current_source else "base"]
                                               is not None for row in rows),
            "same_text_in_the_shipped_tree": same,
            "in_range_at_base": all(row["base"] is not None for row in rows),
        })
        instances.append({"operation": operation, "door_registry": label, "kind": kind,
                          "field": field, "home": home, "door": door,
                          "source_revision": source_revision,
                          "same_text_in_the_shipped_tree": same,
                          "identity_attribution_at_base": attribution})
    drifted = [door for door, row in coordinates.items()
               if not row["same_text_in_the_shipped_tree"]]
    stale_instances = [row for row in instances if not row["same_text_in_the_shipped_tree"]]
    unmeasured_identity = [row for row in instances
                           if row["identity_attribution_at_base"] == "UNATTRIBUTED"]
    out_of_range = [door for door, row in coordinates.items()
                    if row["source_revision"] == base and not row["in_range_at_base"]]
    invalid_source = [door for door, row in coordinates.items()
                      if not row["in_range_at_declared_source"] or not row["source_matches"]]
    return {
        "summary": {
            "base": base,
            "how": ("Historical drift compares base and serving lines. Range, source digest "
                    "and identity attribution follow each coordinate's declared source. "
                    "Legacy *_at_base attribution keys include serving-source anchors; "
                    "source_revision and the attribution explanation disambiguate them."),
            "distinct_door_coordinates": len(coordinates),
            "rule_instances": len(instances),
            "coordinates_whose_line_holds_other_code_in_the_shipped_tree": len(drifted),
            "rule_instances_on_those_coordinates": len(stale_instances),
            "identity_instances_on_those_coordinates": len(
                [row for row in stale_instances if row["kind"] == "identity"]),
            "identity_instances_unattributable_at_base": len(unmeasured_identity),
            "identity_attribution_at_base": dict(Counter(
                row["identity_attribution_at_base"] for row in instances
                if row["kind"] == "identity")),
            "coordinates_out_of_range_at_base": out_of_range,
            "coordinates_invalid_at_declared_source": invalid_source,
            "by_kind_on_drifted": dict(Counter(row["kind"] for row in stale_instances)),
        },
        "identity_instances_on_drifted_coordinates": [
            row for row in stale_instances if row["kind"] == "identity"],
        "identity_instances_unattributable_at_base": unmeasured_identity,
        "coordinates": coordinates,
        "rule_instances": instances,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="706a8204")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    report = measure(args.base)
    summary = report["summary"]
    for key, value in summary.items():
        if key not in ("how",):
            print("%-62s %s" % (key, value))
    if report["identity_instances_on_drifted_coordinates"]:
        print("\nidentity rules whose cited line holds other code in the shipped tree:")
        for row in sorted(report["identity_instances_on_drifted_coordinates"],
                          key=lambda r: (r["door"], r["operation"])):
            print("  %-34s %-30s %s" % (row["operation"], row["field"], row["door"]))
    if report["identity_instances_unattributable_at_base"]:
        print("\nidentity rules whose base coordinate neither names the field nor mints it:")
        for row in report["identity_instances_unattributable_at_base"]:
            print("  %-34s %-30s %s" % (row["operation"], row["field"], row["door"]))
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=1, sort_keys=True, ensure_ascii=False),
                        encoding="utf-8")
        print("\nwrote %s" % path)
    bad = len(report["identity_instances_unattributable_at_base"]) + len(
        summary["coordinates_invalid_at_declared_source"])
    print("\n%s" % ("EVERY DOOR IS IN RANGE AND IDENTITIES ARE ATTRIBUTABLE AT THEIR DECLARED SOURCE" if not bad else
                    "%d DECLARED-SOURCE CITATION CHECKS FAILED" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
