"""The two handler resolvers the two pairwise syntheses brought, compared.

`Declaration.handler` has to answer one question --- which line runs this operation --- and
the merge arrived with two answers for it.  The contract x dispatch branch generated a `site`
column into the route table (`writing_verbs.site_for`); the identity x contract branch read
the door's own text (`writing_declarations.dispatch_site`).  This prints both for every
deployed operation and names every disagreement with the enclosing function of each answer,
which is how the two known ones were diagnosed: each resolver was wrong about exactly one
operation, and in both cases the wrong answer sat outside `_execute`.

    scripts/laplace-python tools/handler_resolvers.py
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from laplace.native import declarations as d          # noqa: E402
from laplace.native import verbs as writing_verbs                      # noqa: E402


def enclosing(lines: list[str], number: int) -> str:
    name = "<module level>"
    for index, line in enumerate(lines, 1):
        if index > number:
            break
        if line.startswith("def "):
            name = line[4:].split("(", 1)[0]
    return name


def main() -> int:
    lines = d._text(d.TOOL_DOOR)
    first, last = d._dispatch_span(lines)
    rows, disagree, silent = [], [], []
    for operation in sorted(d.DECLARATIONS):
        text = d.dispatch_site(operation)
        try:
            table = writing_verbs.site_for(operation)
        except ValueError:
            table = ""
            silent.append(operation)
        rows.append({"operation": operation, "from_the_door_text": text,
                     "from_the_route_table": table})
        if table and table != text:
            disagree.append({
                "operation": operation,
                "route_table": table,
                "route_table_in": enclosing(lines, int(table.rsplit(":", 1)[1])),
                "door_text": text,
                "door_text_in": enclosing(lines, int(text.rsplit(":", 1)[1])),
            })
    print("dispatch region (`_execute` and its families) spans %s:%d-%d" % (d.TOOL_DOOR, first, last))
    print("operations %d, the route table is silent for %d: %r"
          % (len(rows), len(silent), silent))
    print("disagreements: %d" % len(disagree))
    for row in disagree:
        print(json.dumps(row, indent=1))
    outside = [row for row in rows
               if not (first <= int(row["from_the_door_text"].rsplit(":", 1)[1]) <= last)]
    print("resolved handlers outside the dispatch function: %d %r"
          % (len(outside), [row["operation"] for row in outside]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
