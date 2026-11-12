"""What the whole-system merge's help total is made of, in the suite's own metric.

`tests/test_generated_contract.py::test_the_help_total_is_smaller_than_the_measured_baseline`
sums, over the 73 deployed operations, the JSON of the envelope a caller actually receives.
Two pairwise syntheses each set that cap against their own tree, and the merge is larger than
either: the contract x dispatch branch measured 151,244 and capped at 153,000, while the
identity x contract branch's coordinate law adds a `line_numbers` sentence to every response
and an `@<base>` suffix to every typed door.  This prints the total and what each addition
costs, so the cap is set from a measurement and the report cannot quote a figure the tree
does not produce.

    scripts/laplace-python tools/help_cost_parts.py
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

CONTRACT = writing_operating.tool_contract()
PERMITTED = set(CONTRACT["role_permissions"]["work"])
DEPLOYED = sorted(d.DECLARATIONS)


def total(*, strip_law: bool = False, strip_marker: bool = False,
          strip_acts: bool = False) -> int:
    out = 0
    for operation in DEPLOYED:
        action = copy.deepcopy(d.help_payload(operation, permitted=operation in PERMITTED))
        if strip_law:
            action.pop("line_numbers", None)
        if strip_acts:
            action.pop("acts", None)
        text = json.dumps({"schema_version": writing_operating.VERSION,
                           "digest": CONTRACT["digest"],
                           "requested_operation": operation, "action": action},
                          ensure_ascii=False, default=str)
        if strip_marker:
            text = text.replace("@" + d.BASE_REVISION, "")
        out += len(text)
    return out


def main() -> int:
    whole = total()
    rows = [
        ("the whole-system merge, 73 operations", whole, None),
        ("without the coordinate-law sentence", total(strip_law=True), None),
        ("without the @base markers", total(strip_marker=True), None),
        ("without the acts block", total(strip_acts=True), None),
        ("without law and markers together",
         total(strip_law=True, strip_marker=True), None),
    ]
    print("%-42s %9s %9s" % ("", "chars", "costs"))
    for label, value, _ in rows:
        print("%-42s %9d %9s" % (label, value, "" if value == whole else whole - value))
    biggest = sorted(
        ((len(json.dumps(d.help_payload(op, permitted=op in PERMITTED),
                         ensure_ascii=False, default=str)), op) for op in DEPLOYED),
        reverse=True)
    print("largest five responses:", [(name, size) for size, name in biggest[:5]])
    print(json.dumps({"total": whole,
                      "coordinate_law": whole - total(strip_law=True),
                      "base_markers": whole - total(strip_marker=True),
                      "acts": whole - total(strip_acts=True),
                      "operations": len(DEPLOYED)}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
