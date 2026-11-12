"""Can a caller read the (verb, concept) mapping without opening a file in `tests/`?

`help {operation}` publishes an `acts` block: one line per act the operation can be
(`writing_verbs.acts_for`, rendered where `writing_declarations.help_payload` sets
`value["acts"]`).  Across the 73
deployed operations that block costs 11,743 characters of help, and it exists for one reason:
the whole table lives in `tests/grammar_spec/mapping.csv`, which a caller cannot read.  So it
is a SHIM, and the campaign's own law (`tests/test_grammar.py:400`, and the sibling proof
`tests/test_generated_contract.py::test_the_base_revision_is_one_constant_with_one_expiry`)
is that a shim in production carries an expiry whose trigger an instrument can EVALUATE, not a
sentence a reader has to judge.

This is that instrument.  `writing_declarations.ACTS_BLOCK_EXPIRY` retires the per-operation
block when a caller can obtain the whole mapping from ONE door, and the number below is what
decides it:

    caller_doors_publishing_the_whole_mapping

A "caller door" is any response a caller can obtain by calling the system: the 89 `help`
payloads, the 48 HTTP `help` payloads, and the bare catalogue (2026-10-16, M5 work_review).  A door "publishes
the whole mapping" when its single response carries every distinct (verb, concept) pair the route
table holds --- today 130 of them.  The catalogue is the closest: it carries one pair per operation
--- 91 rows, which are 80 of the 130 distinct pairs, because an operation name hides more than
one act and two names can be one act.  (73 was in this docstring until the closing read of
2026-10-02; it is the row count, and `closest_door` below has always printed the distinct
pairs; 75 rows/68 pairs is 2026-10-05, S2 settings-three-ways, and 80 rows/71 pairs is
2026-10-06, S3 dispatch-build, after the five dispatch operations were declared.)  So the
number is 0 and the
shim is alive; when some door publishes the table, the number is non-zero, the proof that
asserts it is still 0 goes red, and the 11,743 characters are given back.

    scripts/laplace-python tools/acts_block_expiry.py        # exit 0; prints the trigger

Banked beside the whole-system report as `wave1/synth-whole/acts_block_expiry.out`.
"""

from __future__ import annotations

import copy
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from laplace.native import declarations as d          # noqa: E402
from laplace.writing import operating as writing_operating                  # noqa: E402
from laplace.native import verbs as writing_verbs                      # noqa: E402

MAPPING = pathlib.Path("tests/grammar_spec/mapping.csv")
CONTRACT = writing_operating.tool_contract()
PERMITTED = set(CONTRACT["role_permissions"]["work"])
DEPLOYED = sorted(d.DECLARATIONS)


def every_pair() -> set[tuple[str, str]]:
    """Every distinct (verb, concept) the route table holds, over all declared operations."""
    out: set[tuple[str, str]] = set()
    for operation in DEPLOYED:
        out.update(writing_verbs.pairs_for(operation))
    return out


def _pairs_in(payload: object) -> set[tuple[str, str]]:
    """The (verb, concept) pairs a single response actually carries.

    Two renderings count, because those are the two the tree ships: a catalogue row's
    `{"verb": ..., "concept": ...}` keys, and an `acts` line's `"<verb> <concept> <- ..."`.
    Nothing is counted by substring over the whole blob: a response that merely happens to
    contain the word `change` somewhere does not publish the pair `(change, plan@plan)`.
    """
    found: set[tuple[str, str]] = set()
    stack = [payload]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            verb, concept = item.get("verb"), item.get("concept")
            if isinstance(verb, str) and isinstance(concept, str):
                found.add((verb, concept))
            stack.extend(item.values())
        elif isinstance(item, (list, tuple)):
            stack.extend(item)
        elif isinstance(item, str) and " <- " in item:
            head = item.split(" <- ", 1)[0].split()
            if len(head) == 2:
                found.add((head[0], head[1]))
    return found


def doors() -> list[tuple[str, object]]:
    """Every response a caller can obtain by calling the system, named."""
    out: list[tuple[str, object]] = [("catalogue", d.catalogue())]
    for operation in DEPLOYED:
        out.append(("help %s" % operation,
                    d.help_payload(operation, permitted=operation in PERMITTED)))
    for row in sorted(d.http_catalogue(), key=lambda r: r["route"]):
        out.append(("help HTTP %s" % row["route"], d.http_help(row["route"])))
    return out


def acts_block_chars(full: bool = False) -> int:
    """What the block costs, in the suite's own metric (`tools/help_cost_parts.py`): as SERVED by default (the
    inline acts, their acts_total and their entry in the sections index, D2 help sections), or in the complete
    rendering (`full=True`), which is what retiring the shim would give back in total."""
    with_block = without = 0
    for operation in DEPLOYED:
        action = copy.deepcopy(d.help_payload(operation, permitted=operation in PERMITTED, full=full))
        envelope = {"schema_version": writing_operating.VERSION,
                    "digest": CONTRACT["digest"], "requested_operation": operation,
                    "action": action}
        with_block += len(json.dumps(envelope, ensure_ascii=False, default=str))
        action.pop("acts", None)
        action.pop("acts_total", None)
        sections = action.get("sections")
        if sections and "acts" in sections.get("chars", {}):
            sections["chars"].pop("acts")
            if not sections["chars"]:
                action.pop("sections")
        without += len(json.dumps(envelope, ensure_ascii=False, default=str))
    return with_block - without


def measure() -> dict:
    whole = every_pair()
    per_door = [(name, len(_pairs_in(payload) & whole)) for name, payload in doors()]
    publishing = [name for name, count in per_door if count >= len(whole)]
    best = max(per_door, key=lambda row: row[1])
    return {
        "acts_block_chars": acts_block_chars(),
        "acts_block_full_chars": acts_block_chars(full=True),
        "distinct_acts_in_the_table": len(writing_verbs.ROUTES),
        "distinct_verb_concept_pairs": len(whole),
        "mapping_file": str(MAPPING),
        "mapping_file_is_readable_by_a_caller": not str(MAPPING).startswith("tests/"),
        "caller_doors_measured": len(per_door),
        "caller_doors_publishing_the_whole_mapping": len(publishing),
        "doors_that_publish_it": publishing,
        "closest_door": {"door": best[0], "pairs": best[1], "of": len(whole)},
        "expiry": d.ACTS_BLOCK_EXPIRY,
    }


def main() -> int:
    report = measure()
    for key in ("acts_block_chars", "distinct_acts_in_the_table",
                "distinct_verb_concept_pairs", "mapping_file",
                "mapping_file_is_readable_by_a_caller", "caller_doors_measured",
                "caller_doors_publishing_the_whole_mapping"):
        print("%-46s %s" % (key, report[key]))
    print("%-46s %s, %d of %d pairs"
          % ("closest_door", report["closest_door"]["door"],
             report["closest_door"]["pairs"], report["closest_door"]["of"]))
    print("%-46s %s" % ("expiry", report["expiry"]))
    print("RETIRABLE: %s" % ("YES --- a caller can read the mapping; delete the block and "
                             "give back %d characters" % report["acts_block_chars"]
                             if report["caller_doors_publishing_the_whole_mapping"]
                             else "NO --- no door publishes the whole mapping, the block "
                                  "stays and costs %d characters"
                                  % report["acts_block_chars"]))
    print(json.dumps(report, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
