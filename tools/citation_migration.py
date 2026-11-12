"""Where every citation into writing_contracts.py now points.

    scripts/laplace-python tools/citation_migration.py --base <ref> --out <dir>

The grammar lane cites `src/laplace/native/contracts.py` at eight lines, in
`grammar.py`, `map_verbs.py` and `GRAMMAR.md`, and `test_grammar.py`'s
`test_the_cited_lines_are_the_lines_they_claim` checks that each line exists.  This
packet rewrote that file from 631 lines to about 120, so three of those citations
now point past the end of it and the proof fails --- correctly: it is doing its job.

The citations are not wrong about the SYSTEM; they are wrong about the address.  So
this prints, for each one, the base line's text and the file:line that holds the same
fact now, as a table the synthesis lane applies to `grammar.py`, `map_verbs.py` and
`GRAMMAR.md`.  This packet does not edit them itself: GRAMMAR.md section 8 says a lane
must not edit `grammar.py` in place, because four build lanes install the same bytes
and two copies of it is the defect the grammar exists to end.

Every resolved address carries the LIVE TEXT of the line it names (`now_line`) and the
substring that line must hold (`now_holds`), and this tool exits non-zero if any row
fails that.  The first version did not, and resolved `note` to line 31 of
`writing_schemas.py` --- `literature_bind`, whose nested `evidence.note` property
matched an unanchored search for `'note':` eleven lines above the real schema at 39.
A table the synthesis lane applies has to be checkable by the lane that receives it.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "src"))

CITED = "src/laplace/native/contracts.py"
SEARCHED = ("src/laplace/core/grammar.py", "tests/grammar_spec/map_verbs.py",
            "tests/grammar_spec/GRAMMAR.md", "tests/grammar_spec/grammar.py")


def base_lines(ref: str) -> list[str]:
    text = subprocess.run(["git", "show", "%s:%s" % (ref, CITED)], cwd=HERE, check=True,
                          capture_output=True, text=True).stdout
    return text.split("\n")


def find_in(path: Path, needle: str, *, anchored: bool = True) -> str:
    """The first line of `path` that starts with `needle` (anchored) or holds it.

    ANCHORED BY DEFAULT, and this is the whole correctness of the tool.  An
    unanchored search for `'note':` finds the NESTED `'note'` property of
    `literature_bind`'s `evidence` object --- line 31 of `writing_schemas.py` ---
    eleven lines above the top-level `'note'` schema it was looking for.  The
    resolved address then points at a different operation's schema and nothing
    fails, because the only thing checked downstream was that the number is inside
    the file.  `SCHEMAS` and `DECLARED` are both one four-space-indented key per
    line, so the top-level key is exactly a line prefix.
    """
    for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
        if line.startswith(needle) if anchored else (needle in line):
            return "%s:%d" % (path.relative_to(HERE), number)
    return ""


#: Three cited lines are NOT inside the `CONTRACTS` dict: they are code in the old
#: `exact_contract`'s variant builder, after it.  `_operation_of` reads upwards for the
#: nearest `    "name": {`, so for all three it answered `export_pdf` --- the last contract
#: entry above them --- and the table resolved an edge-payload fact, a `by` injection and a
#: `connect` property to one declaration that has nothing to do with any of them, while the
#: tool's own check passed because that line does begin with `'export_pdf',`.  The synthesis
#: lane resolves them by hand, with the anchor each one must land on:
#: base line (stripped) -> (file, the live line it must BEGIN with, fact, why)
CODE_SITES = {
    'allowed=list(dict.fromkeys(allowed+["by"]))': (
        "src/laplace/native/declarations.py",
        '        allowed = list(dict.fromkeys(allowed + ["by"]))',
        "by",
        "the line moved verbatim into _variants_logical_plan_change: `by` is still added to "
        "every variant of that one operation, and nowhere else, which is what the grammar's "
        "`by` census records for it (overwritten at writing_tools.py:324)"),
    'if name=="connect":properties["target"]=_STRING': (
        "src/laplace/native/declarations.py",
        '        if name == "connect":',
        "connect",
        "the line moved verbatim into _variants_logical_plan_change: `connect` is the one "
        "operation that declares a top-level `target`, which is why the grammar's payload "
        "carrier for it is `edge_target` and the request's own `target` cannot collide"),
    '"add_edge":{"operation":"add_edge","node":"claim:new","target":"def:basis",': (
        "src/laplace/native/declarations.py",
        "def _variants_concept_change",
        "concept_change",
        "the hand-written example is gone; concept_change's variants are built from the "
        "owner's own contract here, and its edge operations still carry their target INSIDE "
        "the op object, so they never collide with the request's `target`"),
}


def _still_verbatim(operation: str) -> bool:
    """Whether SCHEMAS[operation] still equals the base table's input (tests/grammar_spec/head_contract_prose.json)."""
    from laplace.writing.schemas import SCHEMAS
    base = json.loads((HERE / "tests/grammar_spec/head_contract_prose.json").read_text(encoding="utf-8"))["contracts"]
    return SCHEMAS.get(operation) == (base.get(operation) or {}).get("input")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="706a82047ae90ce79956cb25a4831973f61eec85")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    lines = base_lines(args.base)
    citations: dict[int, list[str]] = {}
    for name in SEARCHED:
        path = HERE / name
        if not path.is_file():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
            for hit in re.findall(r"writing_contracts\.py:(\d+)", line):
                citations.setdefault(int(hit), []).append("%s:%d" % (name, number))

    from laplace.native.declarations import DECLARATIONS

    rows = []
    for cited in sorted(citations):
        base_text = lines[cited - 1].strip() if cited <= len(lines) else ""
        now = ""
        why = ""
        # what the cited line was about, and where that fact lives now
        holds = ""
        fact = ""
        if base_text in CODE_SITES:
            where, anchor, fact, reason = CODE_SITES[base_text]
            now = find_in(HERE / where, anchor, anchored=True)
            holds, fact, why = anchor, fact, reason
        elif "owner_contract" in base_text:
            now = find_in(HERE / "src/laplace/native/declarations.py",
                          "def _variants_structure_change", anchored=True)
            holds = "def _variants_structure_change"
            fact = "_variants_structure_change"
            why = ("the owner-contract duplicate this packet deleted; the variants are "
                   "built from the owner by _variants_structure_change here")
        else:
            operation = _operation_of(lines, cited)
            if operation and operation in DECLARATIONS:
                schema_at = find_in(HERE / "src/laplace/writing/schemas.py",
                                    "    %r:" % operation)
                declared_at = find_in(HERE / "src/laplace/native/declared.py",
                                      "    %r," % operation)
                # Both are given for every row: a cited line inside an `input` block is
                # now data in SCHEMAS, a cited precondition or enum note is now one or
                # more Rule(...) of the declaration, and several lines are both.
                if '"input"' in base_text or "_object((" in base_text or '"enum"' in base_text:
                    now, holds, fact = schema_at, "    %r:" % operation, operation
                    # D1 (2026-10-15): say what holds TODAY. The schema moved verbatim at the migration; whether it
                    # is still verbatim is measured against the pinned base table, and later additive changes are
                    # the ones tests/test_generated_contract.py names (REVIEWED_SCHEMA_CHANGES / its named blocks).
                    still = _still_verbatim(operation)
                    why = ("the schema moved verbatim into SCHEMAS[%r]%s; "
                           "the declaration is at %s" % (operation,
                               " and is still verbatim" if still else
                               " at the migration; its later additive changes are named in "
                               "tests/test_generated_contract.py", declared_at))
                else:
                    now, holds, fact = declared_at, "    %r," % operation, operation
                    why = ("the clause became one or more Rule(%r) of this declaration; "
                           "the schema is at %s" % (operation, schema_at))
        rows.append({"cited": "%s:%d" % (CITED, cited), "cited_by": citations[cited],
                     "base_line": base_text[:160], "now": now,
                     "now_holds": holds, "now_fact": fact,
                     "now_line": _line_at(now),
                     "why": why, "exists_today": cited <= len(_today())})
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "citation_migration.json").write_text(
        json.dumps({"base": args.base, "cited_file": CITED,
                    "base_line_count": len(lines),
                    "today_line_count": len(_today()), "rows": rows},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print("%s: %d lines at %s, %d lines now"
          % (CITED, len(lines), args.base[:12], len(_today())))
    for row in rows:
        print("  %-38s cited by %-44s -> %s"
              % (row["cited"], ",".join(row["cited_by"])[:44], row["now"] or "UNRESOLVED"))
        print("      was: %s" % row["base_line"][:120])
        print("      %s" % row["why"])
    stale = [row["cited"] for row in rows if not row["exists_today"]]
    print("citations that now point past the end of the file: %d %r" % (len(stale), stale))
    # The tool checks its own answers: a resolved address must HOLD the fact its
    # `why` names.  Without this the table could point anywhere inside the right
    # file and read as resolved.
    # ANCHORED, like the search.  `'note':` is a substring of `literature_bind`'s
    # line too, so "the line contains the key" is the same mistake one layer down:
    # the line must BEGIN with the top-level key.
    wrong = [row for row in rows
             if row["now"] and (not (row["now_line"] or "").startswith(row["now_holds"])
                                or row["now_fact"] not in row["why"])]
    for row in wrong:
        print("  WRONG TARGET %s -> %s does not BEGIN with %r; it holds: %s"
              % (row["cited"], row["now"], row["now_holds"],
                 (row["now_line"] or "")[:90]))
    print("resolved addresses verified to hold what the row claims: %d of %d"
          % (len([r for r in rows if r["now"]]) - len(wrong),
             len([r for r in rows if r["now"]])))
    return 1 if wrong else 0


def _line_at(address: str) -> str:
    """The live text of `path:line`, so the table carries what it resolved to."""
    if not address:
        return ""
    path, _, number = address.rpartition(":")
    lines = (HERE / path).read_text(encoding="utf-8").split("\n")
    index = int(number)
    return lines[index - 1] if 0 < index <= len(lines) else ""


def _today() -> list[str]:
    return (HERE / CITED).read_text(encoding="utf-8").split("\n")


def _operation_of(lines: list[str], cited: int) -> str:
    """The operation whose contract entry contains this line, read upwards.

    TWO shapes, because the base file has two.  Most cited lines sit inside the CONTRACTS
    dict, whose entry is `    "<op>": {`.  But `exact_contract` also special-cases five
    operations with `if operation == "<op>":`, and three of the grammar's citations are in
    those blocks (`:579` concept_change's edge example, `:604` and `:607`
    logical_plan_change's `by` and `connect.target`).  Reading only the dict shape walked
    PAST those blocks to whatever dict key came before them and attributed all three to
    `export_pdf` --- three wrong rows in the table the final citation re-point applies.
    Measured on the identity x contract synthesis, where the round-3 grammar module cites
    those three lines and the round-2 one did not.
    """
    for number in range(min(cited, len(lines)), 0, -1):
        line = lines[number - 1]
        match = re.match(r'^\s{4}"([a-z_]+)":\s*\{', line)
        if match:
            return match.group(1)
        match = re.match(r'^\s{4}if operation == "([a-z_]+)":', line)
        if match:
            return match.group(1)
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
