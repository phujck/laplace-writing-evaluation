#!/usr/bin/env python3
"""Attribute every allowed difference to the ENTRY that grants it, and narrow the list.

WHY.  ``harness/replay.py:203-209`` grants a difference if its KIND appears under
``kinds`` (blanket), or under ``rows[<row id>]``, or under
``operations[<operation>]``, or under ``sources[<source>]``.  A SOURCE entry is the
widest of the four that is not blanket: ``sources: {"failures": ["response"]}``
forgives the response body of EVERY recorded failure row.  A report that says
"every entry is a row or an operation" has to be able to prove it, and the way to
prove it is to ask, per row, which entries actually did the granting.

    attribute_allow.py --rows <rows.jsonl> --allow <allow.json> --out <dir>

It prints, for each (row, kind) difference, every scope that grants it, and then
the rows for which a given scope is the ONLY grant.  With ``--drop-scope sources``
it writes a narrowed allow list without that scope and re-applies the harness's
own ``allowed`` rule to the same rows: an ``unallowed_total 0`` under the narrowed
list is the proof that the wide entry granted nothing.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def granting_scopes(allow: dict, row: dict, kind: str) -> list[str]:
    """Every scope of ``allow`` that would grant ``kind`` on ``row``.

    The membership test is harness/replay.py:203-209, repeated here per scope
    instead of collapsed to a boolean, which is the whole point of this tool.
    """
    scopes = []
    if kind in (allow.get("kinds") or []):
        scopes.append("kinds")
    for scope, key in (("rows", row.get("id")), ("operations", row.get("operation")),
                       ("sources", row.get("source"))):
        if kind in (allow.get(scope) or {}).get(str(key), []):
            scopes.append(scope)
    return scopes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", required=True)
    ap.add_argument("--allow", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--drop-scope", default="sources")
    args = ap.parse_args()

    allow = json.loads(Path(args.allow).read_text())
    rows = [json.loads(line) for line in Path(args.rows).read_text().splitlines() if line.strip()]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    by_source = Counter(str(r.get("source")) for r in rows)
    diff_kinds = Counter()
    only_by = defaultdict(list)          # scope -> [(row id, kind)]
    unallowed = []
    detail = []
    response_rows = []
    for row in rows:
        for kind in row.get("diffs") or []:
            diff_kinds[kind] += 1
            scopes = granting_scopes(allow, row, kind)
            detail.append({"id": row.get("id"), "source": row.get("source"),
                           "operation": row.get("operation"), "kind": kind,
                           "granted_by": scopes})
            if kind == "response":
                response_rows.append({"id": row.get("id"), "source": row.get("source"),
                                      "operation": row.get("operation"),
                                      "granted_by": scopes})
            if not scopes:
                unallowed.append((row.get("id"), kind))
            elif len(scopes) == 1:
                only_by[scopes[0]].append((row.get("id"), kind))

    narrowed = {k: v for k, v in allow.items() if k != args.drop_scope}
    narrowed[args.drop_scope] = {}
    narrowed["note"] = (allow.get("note", "") + f"\n\nNARROWED by "
                        f"tools/writing_verbs/attribute_allow.py: the `{args.drop_scope}` "
                        f"scope is emptied. Every difference in {Path(args.rows).name} that "
                        f"the full list allowed is still allowed, by a row or an operation "
                        f"entry; see narrowed_unallowed in the report beside this file.")
    narrowed_unallowed = []
    for row in rows:
        for kind in row.get("diffs") or []:
            if not granting_scopes(narrowed, row, kind):
                narrowed_unallowed.append({"id": row.get("id"), "kind": kind,
                                           "source": row.get("source"),
                                           "operation": row.get("operation")})

    scope_sizes = {scope: len(allow.get(scope) or []) for scope in
                   ("kinds", "rows", "operations", "sources")}
    source_entry_covers = {name: by_source.get(name, 0)
                           for name in (allow.get("sources") or {})}
    report = {
        "rows_file": str(Path(args.rows).resolve()),
        "allow_file": str(Path(args.allow).resolve()),
        "rows_total": len(rows),
        "rows_by_source": dict(by_source),
        "difference_by_kind": dict(diff_kinds),
        "allow_scope_sizes": scope_sizes,
        "allow_sources_entries": allow.get("sources") or {},
        "rows_a_source_entry_covers": source_entry_covers,
        "unallowed_under_the_full_list": unallowed,
        "granted_by_exactly_one_scope": {k: len(v) for k, v in only_by.items()},
        "rows_whose_only_grant_is_a_source_entry": only_by.get("sources", []),
        "response_differences": response_rows,
        "response_differences_by_operation":
            dict(Counter(r["operation"] for r in response_rows)),
        "response_differences_by_source":
            dict(Counter(str(r["source"]) for r in response_rows)),
        "narrowed_unallowed": narrowed_unallowed,
        "narrowed_is_as_strong": not narrowed_unallowed,
    }
    (out / "attribution.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    (out / "attribution_rows.jsonl").write_text(
        "".join(json.dumps(d, ensure_ascii=False) + "\n" for d in detail))
    (out / "allow.narrowed.json").write_text(json.dumps(narrowed, indent=1, ensure_ascii=False) + "\n")

    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("response_differences",)}, indent=1, ensure_ascii=False))
    print(f"\nwrote {out}/attribution.json, attribution_rows.jsonl, allow.narrowed.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
