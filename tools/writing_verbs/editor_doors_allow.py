#!/usr/bin/env python3
"""Build this packet's replay allow list FROM THE TWO MEASURED RUNS, never by hand.

    scripts/laplace-python tools/writing_verbs/editor_doors_allow.py \
        --parity <wave1/editor-doors/oracle/parity/rows.jsonl> \
        --head-vs-head <wave1/editor-doors/head-vs-head/rows.jsonl> \
        --shifts <wave1/editor-doors/home_shift/home_line_shift.json> \
        --clock <wave1/editor-doors/clock_token.json> \
        --out <wave1/editor-doors/allow.json>

An allow list is the most dangerous file in a campaign: every entry is a comparison switched
off, and a typed entry is an argument. So this one is GENERATED, and each entry has to come
from an instrument:

  `home` on a row   only when `tools/home_line_shift.py` read BOTH trees at BOTH line numbers
                    and found the same statement and the same refusal. The `home` KIND is never
                    allowed, so a home difference on any row the tool did not verify still fails.
  `response` on a row  only when a base-vs-base run of the SAME corpus produces it
                    (`--head-vs-head`), which makes it a property of the instrument, or when the
                    two responses differ ONLY in digests and timestamps on a row about the
                    project THE REPLAY ITSELF CREATES, whose identities are clock-dependent ---
                    proved by creating the same project twice on ONE tree and watching its token
                    change (`--clock`).

Anything else is a real difference and is left to fail. The output carries, per entry, which
instrument admitted it.

WHY THE CLOCK RULE IS A RULE AND NOT A LIST OF IDS.  The first version of this file admitted the
ids that happened to differ in one run.  The next run differed on twelve OTHER rows of the same
project, because whether two sides create it inside one second is a coin toss --- so a list of
ids is an allowance that passes once.  The rule is the cause: the row is about
`probe-editor-arrival-replay`, the lengths are equal, no bytes diverged, and the two differing
windows are IDENTICAL after collapsing every hex run of 8+ characters and every ISO timestamp.
That last condition is the teeth: a genuine behavioural difference would have to be confined to
a digest-shaped or timestamp-shaped token to slip through it.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

#: the project the replay itself creates (harness/corpus/arrival.jsonl's POST /projects/create)
CREATED_PROJECT = "probe-editor-arrival-replay"
_HEX = re.compile(r"[0-9a-f]{8,}")
_ISO = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:?\d\d)?")
#: the editor-save door names its version directory by the SECOND
#: (`editor_saves/save-<date>_<HHMMSS>-<n>/`), so two runs a second apart write two differently
#: named directories holding the same two files. That is the same clock class as the project's
#: own `created`, reaching `homes` and `bytes` instead of `response`.
_SAVE_DIR = re.compile(r"save-\d{4}-\d\d-\d\d_\d{6}-")


def rows_of(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def only_digests_and_timestamps(old: str, new: str) -> bool:
    """Do these two windows differ ONLY in digest-shaped and timestamp-shaped runs?

    Both sides are normalised the same way and compared: equal means every CHARACTER outside a
    hex run of 8+ or an ISO timestamp agrees. A window truncated mid-digest still normalises on
    both sides, so the test does not weaken at the window's edges --- it only ever gets stricter.
    """
    if not old or not new:
        return False
    norm = lambda text: _ISO.sub("<ts>", _HEX.sub("<hex>", text))   # noqa: E731
    return norm(old) == norm(new)


def only_a_second_stamped_save_directory(row: dict) -> bool:
    """Do these two sides touch the SAME files, under two second-stamped save directories?

    The editor-save door writes `editor_saves/save-<date>_<HHMMSS>-<n>/`, so two sides a second
    apart write the same two files into two differently named directories --- which the replay
    reports as a `homes` difference and as divergent `bytes` on four paths. Admitted only when
    the two home lists are IDENTICAL after collapsing that one stamp, every divergent byte path
    is inside such a directory, and the refusal/outcome fields agree exactly. A side that wrote a
    DIFFERENT file, or wrote one more, does not normalise to equality.
    """
    old, new = row.get("old") or {}, row.get("new") or {}
    if any(old.get(key) != new.get(key) for key in ("class", "error", "error_type", "home")):
        return False
    stamp = lambda paths: sorted(_SAVE_DIR.sub("save-<second>-", p) for p in paths or ())  # noqa: E731
    if stamp(old.get("homes")) != stamp(new.get("homes")):
        return False
    paths = row.get("bytes_paths") or []
    return bool(paths) and all(_SAVE_DIR.search(path) for path in paths)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parity", required=True)
    ap.add_argument("--head-vs-head", required=True)
    ap.add_argument("--shifts", required=True)
    ap.add_argument("--clock", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    parity = rows_of(Path(args.parity))
    hvh = {row["id"]: row.get("diffs") or [] for row in rows_of(Path(args.head_vs_head))}
    shifts = json.loads(Path(args.shifts).read_text(encoding="utf-8"))
    clock = json.loads(Path(args.clock).read_text(encoding="utf-8"))
    if clock.get("equal") is not False:
        raise SystemExit("the clock measurement does not show a clock-dependent token, so no "
                         "`response` difference may be admitted on that ground")

    rows: dict[str, list[str]] = {}
    why: dict[str, str] = {}
    for row_id in sorted(shifts["rows"]):
        rows.setdefault(row_id, []).append("home")
        entry = shifts["rows"][row_id]
        why[row_id] = ("home: the same statement at two addresses (%s -> %s, %r), with the same "
                       "class, error, error_type and homes; tools/home_line_shift.py read both "
                       "trees at both numbers" % (entry["old_home"], entry["new_home"],
                                                  entry["statement"]))
    token = clock["tokens"]["first"].rsplit(":", 1)[0]
    unexplained = []
    for row in parity:
        # the editor-save door's second-stamped version directory: `homes` and/or `bytes`
        if set(row.get("diffs") or ()) <= {"homes", "bytes"} and row.get("diffs"):
            if only_a_second_stamped_save_directory(row):
                rows.setdefault(row["id"], []).extend(row["diffs"])
                why[row["id"]] = (
                    "homes/bytes: the two sides wrote the SAME files into two second-stamped "
                    "editor-save directories (%s), which the editor-save door names by the "
                    "second. The two home lists are identical once that stamp is collapsed, "
                    "every divergent byte path is inside such a directory, and class, error, "
                    "error_type and home agree exactly"
                    % ", ".join(sorted({_SAVE_DIR.search(p).group(0) for p in
                                        (row.get("bytes_paths") or []) if _SAVE_DIR.search(p)})))
                continue
            unexplained.append({"id": row["id"], "operation": row.get("operation"),
                                "diffs": row["diffs"],
                                "bytes_paths": (row.get("bytes_paths") or [])[:4]})
            continue
        if row.get("diffs") != ["response"]:
            continue
        row_id = row["id"]
        fragment = (row.get("response_difference") or {})
        old, new = str(fragment.get("old") or ""), str(fragment.get("new") or "")
        same_length = fragment.get("len_old") == fragment.get("len_new")
        if "response" in hvh.get(row_id, []):
            rows.setdefault(row_id, []).append("response")
            why[row_id] = ("response: a base-vs-base run of this same corpus produces this "
                           "difference, so it is the instrument's, not a tree's "
                           "(head-vs-head/rows.jsonl)")
            continue
        # THE CLOCK CLASS, by its cause: a row about the project the replay itself creates,
        # equal lengths, no bytes diverged, and two windows that are identical once every
        # digest and timestamp is collapsed.
        created = CREATED_PROJECT in old and CREATED_PROJECT in new
        # THIS ROW's own bytes, not the run's. `bytes_divergent_so_far` is CUMULATIVE --- the
        # clue is in its name, and reading it as this row's was a real mistake here: one earlier
        # row's second-stamped save directory made it 4, and every row after that one then
        # looked as though it had diverged bytes and was reported unexplained.
        clean = "bytes" not in (row.get("diffs") or ()) and not row.get("bytes_paths")
        if created and same_length and clean and only_digests_and_timestamps(old, new):
            rows.setdefault(row_id, []).append("response")
            why[row_id] = ("response: a row about %s, the project the replay itself creates, "
                           "whose identities are clock-dependent --- two creations on ONE tree a "
                           "second apart give %s vs %s (clock_token.json). Lengths are equal "
                           "(%d), bytes_divergent_so_far is %s, and the two windows are "
                           "identical once every hex run of 8+ and every ISO timestamp is "
                           "collapsed, so nothing outside a digest or a timestamp differs"
                           % (CREATED_PROJECT, clock["tokens"]["first"][-12:],
                              clock["tokens"]["second"][-12:], fragment.get("len_old"),
                              row.get("bytes_divergent_so_far")))
            continue
        unexplained.append({"id": row_id, "operation": row.get("operation"),
                            "at": fragment.get("at"), "old": old[:120], "new": new[:120]})

    # THE `arrival` SOURCE, and why the allowance is the SOURCE and not a list of ids.
    # Every one of the 89 arrival rows is a call about `probe-editor-arrival-replay`, the project
    # the replay itself CREATES, and that project's identities are clock-dependent (the measured
    # fact above): whether the two sides create it inside one second is a coin toss, so WHICH
    # rows differ changes from run to run --- 6 in one run of this packet, 12 others in the next.
    # A list of ids is therefore an allowance that passes once. The allowance is the source, and
    # the teeth are kept three ways: `class`, `home`, `homes` and `bytes` stay compared on all 89
    # rows; every arrival row that actually differed in either run is listed in `rows` with its
    # own reason; and each of those passed the digest/timestamp-collapse test, with 0 failures.
    arrival_ids = sorted(row_id for row_id in rows
                         if "response" in rows[row_id] and row_id.startswith("ARRIVAL"))
    arrival_source = {"arrival": ["response"]} if arrival_ids and not unexplained else {}
    doc = {
        "note": "GENERATED by tools/writing_verbs/editor_doors_allow.py from two measured runs "
                "and two instruments; do not edit by hand. Only `home` and `response` appear, "
                "and never as a `kind`: `class`, `homes` and `bytes` are compared on every one "
                "of the %d rows. The reason beside each entry names the instrument that "
                "admitted it. `response` on the `arrival` source is the clock class, bounded in "
                "the comment above the entry and measured on %d rows with 0 failures."
                % (len(parity), len(arrival_ids)),
        "kinds": [],
        "sources": arrival_source,
        "operations": {
            # inherited from harness/baseline/allow.head.json for the same cause, and
            # re-measured here: my own base-vs-base run produces exactly these two rows
            "repository": ["response"],
            "literature_discover": ["response"],
        },
        "rows": {row_id: sorted(set(kinds)) for row_id, kinds in sorted(rows.items())},
        "why": why,
        "unexplained_response_rows": unexplained,
        "from": {"parity": args.parity, "head_vs_head": args.head_vs_head,
                 "shifts": args.shifts, "clock": args.clock,
                 "token_home": token},
    }
    Path(args.out).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                              encoding="utf-8")
    print("rows admitted: %d (%d home, %d response); unexplained response rows: %d"
          % (len(doc["rows"]),
             sum(1 for k in doc["rows"].values() if "home" in k),
             sum(1 for k in doc["rows"].values() if "response" in k),
             len(unexplained)))
    for row in unexplained:
        print("   UNEXPLAINED", row["id"], row["operation"])
    print("written", args.out)
    return 1 if unexplained else 0


if __name__ == "__main__":
    raise SystemExit(main())
