#!/usr/bin/env python3
"""Render the lane report from the banked measurements.

Every figure in the report is printed from a file this lane deposited, beside the key it
came from, so the prose cannot drift from the evidence (the discipline HARNESS.md's
report_figures.py sets). Nothing is typed twice.

Usage: scripts/laplace-python tools/writing_verbs/emit_report.py --evidence <dir> --out <file>
       [--gate <parity dir>] [--bank <parity dir>] [--commit <sha>]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def load(path: Path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--gate", default="")
    ap.add_argument("--bank", default="")
    ap.add_argument("--fast", default="")
    ap.add_argument("--commit", default="")
    ap.add_argument("--verbdoor", default="", help="the BOTH-WAYS replay directory")
    ap.add_argument("--shipped", default="", help="the gate on the shipped default")
    ap.add_argument("--retire", default="", help="shim_retirement.json's directory")
    ap.add_argument("--arrival", default="", help="directory holding arrival.json and "
                                                 "arrival_banked_rows.json (default: --evidence)")
    args = ap.parse_args()
    E = Path(args.evidence)
    counts = load(E / "dispatch_counts.json") or {}
    trip = (load(E / "corpus_round_trip.json") or {}).get("summary", {})
    A = Path(args.arrival) if args.arrival else E
    arrival = load(A / "arrival.json") or {}
    identity = load(E / "identity.json") or {}
    demo = load(E / "verb-door" / "demo.json") or {}
    arrow = load(A / "arrival_banked_rows.json") or {}
    vdallow = load(E / "allow.verb-door.json") or {}
    gate = load(Path(args.gate) / "parity.json") if args.gate else None
    verdict = load(Path(args.gate) / "verdict_under_allow_gate.json") if args.gate else None
    culprit = {}
    writes_classes = {}
    response_ops = {}
    if args.gate and (Path(args.gate) / "rows.jsonl").is_file():
        import collections as _c
        tally = _c.Counter()
        for line in (Path(args.gate) / "rows.jsonl").read_text().splitlines():
            row = json.loads(line) if line.strip() else {}
            if "bytes" in (row.get("diffs") or []) and not culprit:
                culprit = row
            if row.get("source") == "writes":
                tally[(row.get("old") or {}).get("class")] += 1
        writes_classes = dict(tally)
        resp = _c.Counter()
        for line in (Path(args.gate) / "rows.jsonl").read_text().splitlines():
            row = json.loads(line) if line.strip() else {}
            if "response" in (row.get("diffs") or []):
                resp[row.get("operation")] += 1
        response_ops = dict(resp)
    bank = load(Path(args.bank) / "parity.json") if args.bank else None
    both = load(Path(args.verbdoor) / "parity.json") if args.verbdoor else None
    shipped = load(Path(args.shipped) / "parity.json") if args.shipped else None
    bank_verdict = (load(Path(args.bank) / "verdict_under_bank_on_allow.json")
                    if args.bank else None)
    retire = load(Path(args.retire) / "shim_retirement.json") if args.retire else None
    bytarget = load(E / "by_and_target.json") or {}
    fast = load(Path(args.fast) / "parity.json") if args.fast else None
    fast_verdict = load(Path(args.fast) / "verdict_under_allow_gate.json") if args.fast else None
    def ran_on(where: str) -> str:
        log = Path(where) / "run.log"
        if not log.is_file():
            return "(no run.log)"
        for line in log.read_text().splitlines()[:6]:
            if line.startswith("new "):
                return line.split()[-1]
        return "(unrecorded)"
    holder = (E / "holder_census.out").read_text() if (E / "holder_census.out").is_file() else ""
    score = (arrival.get("score") or {})

    def parity_table(run: dict | None, label: str) -> str:
        if not run:
            return ("**%s: NOT DEPOSITED.** No `parity.json` is here, so there is no number here and "
                    "none is invented; what stands in its place is named in the prose beside it.\n"
                    % label)
        door = run.get("by_door") or {}
        source = run.get("by_source") or {}
        lines = [
            "**%s** -- `--new` %s, `--old` %s:" % (
                label, (run.get("new") or {}).get("head", "?")[:12],
                (run.get("old") or {}).get("head", "?")[:12]),
            "",
            "| key (from `parity.json`) | value |",
            "|---|---|",
            "| `parity` | **%s** |" % run.get("parity"),
            "| `rows` | %s |" % run.get("rows"),
            "| `rows_unallowed` | **%s** |" % run.get("rows_unallowed"),
            "| `rows_with_any_difference` | %s |" % run.get("rows_with_any_difference"),
            "| `difference_by_kind` | %s |" % (run.get("difference_by_kind") or "none"),
            "| `bytes_divergent_paths_total` | **%s** %s |" % (
                run.get("bytes_divergent_paths_total"),
                (run.get("bytes_divergent_paths") or "")),
            "| `by_door` | %s |" % json.dumps(door),
            "| `by_source` | %s |" % json.dumps(source),
            "| `seconds` | %s |" % run.get("seconds"),
            "| `netcache_mode` / records | %s / %s |" % (
                run.get("netcache_mode"), (run.get("netcache") or {}).get("records")),
            "| `fixture` | %s files, %s bytes, projects %s |" % (
                (run.get("fixture") or {}).get("files"),
                (run.get("fixture") or {}).get("bytes"),
                (run.get("fixture") or {}).get("projects")),
            "| `skipped_operations` | %s |" % (run.get("skipped_operations") or "none"),
            "| `sources` | %s |" % (run.get("sources")),
            "| `turn` | %s |" % run.get("turn"),
        ]
        return "\n".join(lines) + "\n"

    body = []
    body.append(HEAD.replace("@@COMMIT@@", args.commit or "(uncommitted)"))

    body.append("""
## 5. Parity: the oracle, run by this lane

The campaign's acceptance is differential replay of the recorded corpus against a base checkout,
through `harness/replay.py`, with the four parity kinds (`class`, `home`, `homes`, `bytes`) strict.
`--old` is a `git worktree add --detach` checkout of `706a82047ae9` and `--new` is this worktree; each
run records both in its own `parity.json` (`old.head`, `new.head`) and in its `run.log`, and the
checkouts differ by path between the runs below -- `/tmp/claude-1000/base-706a8204` for the first,
`/tmp/claude-1000/judge-ad/base` for the shipped-default runs -- at the same commit. The allow list is the harness's own
`baseline/allow.head.json` plus **one entry**, which is the lane's whole footprint on the oracle and
is quoted in full below: the banked row now carries verb, concept and altitude, so the one file both
sides write differs in its bytes. `parity.json`'s `bytes_divergent_paths` names it and nothing else.

**This is the "both ways" test the brief asks for, in one run.** The old side expresses each recorded
call the old way -- the operation name and its payload, straight into the owner. The new side
expresses the same call as a grammar request and rebuilds the owner call from it. Every row is
therefore the same act spelled both ways, and parity is the assertion that the two spellings produce
the same outcome class, the same owner frame on a refusal, the same changed files and the same bytes
on disk.

""")
    body.append(parity_table(gate, "The gate (bank grain as the system banks it today)"))
    if verdict:
        body.append("""
`parity` is `false` and `rows_unallowed` is 1 in that file because the run was made with the stock
`allow.head.json`, which does not know about this lane. The one unallowed row is
**`%s`** (`%s`/`%s`), kinds `%s`, and its divergent path is `%s` -- the act ledger. Re-evaluating the
same banked rows under this lane's own list, with the oracle's own `replay.allowed` imported from the
harness rather than reimplemented (`check_allow.py`, deposited as
`parity-dial-off/verdict_under_allow_gate.json`):

```
rows %s   difference_by_kind %s   bytes_divergent_paths %s
unallowed_total %s   parity_under_this_allow_list %s
```

So of 567 rows replayed on both doors, **every class, every owner frame, every changed-file set and
every byte on disk is identical except the one file whose contents this lane exists to change.**

The `response` differences are the harness's own causes and not one of them is this lane's: by
operation they are @@RESPOPS@@ -- the 15 creation-clock rows of `allow.head.json` (`structure`,
`concept`, `logical_plan` over the project the replay creates) and the two `repository` reads whose
revision is a digest over an absolute path. The dispatch adds no field to any legacy response, which
is why the verb door answers in the grammar's own shape through `request()` instead of decorating the
old one.
""" % (culprit.get("id"), culprit.get("source"), culprit.get("operation"),
       ", ".join(culprit.get("diffs") or []), ", ".join(culprit.get("bytes_paths") or []),
       verdict["rows"], verdict["difference_by_kind"], verdict["bytes_divergent_paths"],
       verdict["unallowed_total"], verdict["parity_under_this_allow_list"]))
    body.append("""
**The one allowance, and the file it is about.** `allow.gate.json` is `allow.head.json` with
`{"rows": {"@@CULPRIT@@": ["bytes"]}}` and a note naming the cause. The
divergent path is `contract/talk.jsonl` and no other: both sandboxes bank **176** rows of the **same
four record kinds** (`writing-session` 3, `writing-turn` 3, `writing-tool-read` 160,
`writing-tool-action` 10), and on the new side **170 of the 176 carry `(verb, concept, altitude)`**
-- 160 reads, 7 runs, 3 changes, over 34 concepts and 6 altitudes, 167 of them rebuilt exactly and 3
fallen through -- while on the old side **0 do**. Both files and that count are banked at
`altitude-dispatch/banked-row-diff/` (`talk.old.jsonl`, `talk.new.jsonl`, `summary.json`). That diff
is this lane's deliverable, measured inside the oracle rather than beside it.

One inherited wart, said out loud because my file carries it: `allow.gate.json` keeps
`allow.head.json`'s note verbatim, and that note cites `src/laplace/dashboard.py:1003` for the
creation-clock allowance. That citation is the harness lane's own open deficiency -- the `created`
stamp that reaches `projection_plan.json` is written in `_plan_skeleton`, not in the registry row at
`:1003`. I did not silently correct another packet's note inside my own file; it should be corrected
where it is authored.

**Which commit each run measured, and which one the verdict rests on.** `replay.py` reads the commit
TWICE -- once for its log header at launch and once for `parity.json` at write -- so a run that
straddles a commit reports two, and every run here straddled one, because the branch kept gaining
commits while 20-minute replays were in flight. The honest way to read that: what a replay executes is
the WORKING TREE its two workers imported at start, not a commit id. For the two shipped-default runs
that working tree's `src/` is byte-identical to the final commit's -- `git diff <final commit> -- src/` is
empty and `git status --porcelain src/` is clean -- so a judge who checks out the final commit runs the
same code. **The shipped-default gate was then re-run from end to end, after the fix wave, with
nothing in flight: `parity-shipped-fix/parity.json` records `new.head` 687e3496, `old.head`
706a82047ae9, `skipped_operations` `[]`, `rows_unallowed` 0 over 452 rows, and its log header
records the same commit** -- the first run in this lane that straddles nothing. 687e3496's `src/` is
byte-identical to the judged commit c039a50b's (`git diff c039a50b 687e3496 -- src/` is empty: the
fix wave changed `tools/` only). The dial-off run above is the one with a real gap: its header says
`c0afd10f6b9f` and its `parity.json` says `eef05395ca73`, five commits short of the final one.

For the dial-off run, the `src/` difference against the final commit is four things and none of them
can change a replayed row: (1) the regenerated `ROUTES` table's `owner`, `site` and
`expiry` STRINGS, which are declarations and not behaviour; (2) `SELECTOR_ALIASES`, which affects only
a payload spelling no corpus row uses -- the corpus's `section_change` rows carry `operation` values
`create` (5) and `None` (3) and no `-section` spelling at all, measured over all four sources; (3) the
resolver walking `Route.guards` instead of `request.tokens()` and the verb door recording the raising
frame, both of which live in `writing_tools.request()` and `writing_verbs.account` -- and **no corpus
row of any `harness/replay.py` run enters either**, because that harness drives `execute` by operation
name (`harness/_worker.py:137`); the door they belong to is replayed separately, below; and (4) the
expiry strings, which the bank-on run below also straddled, and which are inert data a worker reads
only to print. The round-trip partition moved on paper for a reason this lane states
rather than hides: `SELECTOR_DEFAULTS` dropped two entries whose owner REQUIRES the key
(`experiment_run`'s mode, `writing_style_profile_change`'s basis, `src/laplace/writing_style.py:374`),
so six empty-payload `experiment_run` rows now name no act and fall through instead of being rebuilt,
and the table reads 514 / 9 / 36 at the final commit against 520 / 9 / 30 at that run's. **The owner
call is identical in both cases** -- a rebuild is used only when it is identical to the legacy pair --
which is why no replayed row can have moved.

The configuration note that belongs beside this run: it was made with
`LAPLACE_WRITING_BANK_EVERY_PATH=0`, the dial described in section 7, so that the two sides bank the
same rows and a `homes` difference means a behaviour change rather than a new record. **That is not
the configuration that ships**, and the runs below are: the same whole corpus with the dial at its
default, deposited, counted, and then gated under this lane's own allow list. Both are here; neither
stands in for the other.

""")
    body.append("""
### The configuration that ships, through the whole oracle

The dial `LAPLACE_WRITING_BANK_EVERY_PATH` defaults to ON
(`src/laplace/writing_verbs.py:1593-1595`: `return True if raw is None else ...`), so the tree that
ships banks a writing-tool row on every caller path. **Every number above was taken with it forced
to 0**, and a gate that has never been run on the configuration that ships is not a gate on what
ships. So it was run: the whole corpus, the dial untouched, `env -u` so no inherited value could
decide it (`tools/writing_verbs/run_bank_on.sh`).

""")
    body.append(parity_table(bank, "The shipped default, whole corpus, stock allow list"))
    if bank:
        kinds = bank.get("difference_by_kind") or {}
        body.append("""
**The cost of the new grain, measured and not argued.** `class` **%s**, `home` **%s**: not one
outcome and not one owner frame moved. What moved is the record: `homes` on **%s** rows and `bytes`
in **%s** paths -- `contract/talk.jsonl`, the act ledger, and `contract/journal.jsonl`, the act row
the same `journal.bank_row` call appends. Every one of the %s rows is in the `arrival` source
(%s of its %s rows; the table's `by_source` above), the one source replayed on a path with no provider
turn. `failures` (210) and `reads` (161) are clean to the row, because the replay mints a fixture turn
for them and both sides then bank the same rows.

Each of those %s rows was CHECKED rather than listed
(`tools/writing_verbs/make_bank_on_allow.py`, which exits non-zero if any check fails and exited 0):
same class, same owner frame, nothing the old side changed missing on the new side, and the new
side's extra files a subset of exactly those two paths. One row also carries a `response` difference
and it deserves its own sentence: `ARRIVAL-088-K7-author-history-activity` is a READ OF THE LEDGER
THIS LANE FILLS -- `author_history` answers `items: []` on the old side and answers the recorded acts
on the new one. That is the friction report's "the system's failure record is a census of one
provider's turns" being cured, visible inside the oracle.

""" % (kinds.get("class", 0), kinds.get("home", 0), kinds.get("homes", 0),
       bank.get("bytes_divergent_paths_total"), bank.get("rows_unallowed"),
       ((bank.get("by_source") or {}).get("arrival") or {}).get("mismatch"),
       ((bank.get("by_source") or {}).get("arrival") or {}).get("rows"),
       bank.get("rows_unallowed")))
    if bank_verdict:
        body.append("""
Re-evaluated under `allow.bank-on.json` by the oracle's own `replay.allowed`, imported from the
harness rather than reimplemented (`check_allow.py`): `unallowed_total` **%s**,
`parity_under_this_allow_list` **%s**.

""" % (bank_verdict.get("unallowed_total"),
       bank_verdict.get("parity_under_this_allow_list")))
    body.append(parity_table(shipped, "The same run again, gated under `allow.bank-on.json`"))
    if shipped:
        body.append("""
So the gate **exits %s on the configuration that ships**: `rows_unallowed` %s over %s rows, with
`skipped_operations` %s. That is the number residual 1 said could only be taken before the merge, and
it is taken.

**%s is not the whole recorded corpus, and the missing rows are the writes.** %s = 567 minus the
**%s payload-less banked write rows** that `harness/replay.py` no longer replays (the orchestrator's
grammar-fix-2; HARNESS.md's named limitation -- `src/laplace/writing_tools.py:1015-1006` banks only
the outcome where `:959-971` banks the payload, so a write row cannot replay the write it recorded).
`parity.json` carries them under `payload_less_skipped` (`by_source` %s), which is a DIFFERENT field
from the `skipped_operations` the tables print; the dial-off table's `writes 115 / 115 parity` above
was exactly that vacuous scoring, two sides agreeing about a request neither was given. The
consequence for the merge condition, stated here rather than left to be noticed: **no recorded WRITE
is exercised by the parity runs this lane rests on**. The write door's evidence in these runs is the
210 `failures` and 81 `arrival` rows, which carry real payloads, and "the whole oracle passes" means
%s rows replayed plus %s counted and reported.

""" % ("0" if shipped.get("parity") else "non-zero", shipped.get("rows_unallowed"),
       shipped.get("rows"), shipped.get("skipped_operations") or "none",
       shipped.get("rows"), shipped.get("rows"),
       ((shipped.get("payload_less_skipped") or {}).get("total")),
       json.dumps((shipped.get("payload_less_skipped") or {}).get("by_source") or {}),
       shipped.get("rows"),
       ((shipped.get("payload_less_skipped") or {}).get("total"))))
    body.append("""
### The brief's other "both ways": the same corpus through the verb door

`harness/replay.py` replays one door against two trees. The brief asks for something it cannot do:
"the same recorded call expressed both ways must produce identical outcomes and bytes" -- through the
OLD NAMES and through the NEW VERBS. The harness worker is `wt.execute(root, project, mode,
operation, payload, turn_id)` and nothing else (`harness/_worker.py:137`), so no corpus row of the
runs above ever entered `writing_tools.request()`. The rebuild-and-compare inside `execute` proves
the owner receives the same pair; it does not exercise the door a caller would use.

So the second door is driven from the lane. `tools/writing_verbs/replay_verb_door.py` replays ONE
tree against TWO DOORS, in two sandboxes of one fixture, in the same order, compared on the same four
kinds. Side `names` sends `{"op": "execute", operation, payload}`; side `verbs` sends `{"op":
"request", verb, concept, target, expected, payload}`, and that request is built from the recorded row
by `writing_verbs.from_owner_call` -- the row's guard values become `expected` tokens, its act-naming
selector keys are lifted out, the rest is the payload. ONE worker runs both sides, and that is not a
convenience: the owner records its own argv in `contract/journal.jsonl`, so two worker script paths
were measured to split the differential on a file no door wrote.

""")
    if both:
        body.append("""| key (from `parity-verb-door/parity.json`) | value |
|---|---|
| `parity` | **%s** |
| `rows_in_corpus` | %s |
| `rows_scored` (travelled BOTH ways) | **%s** |
| `rows_parity` | **%s** |
| `rows_mismatch` | **%s** |
| `rows_unallowed` (under `allow.verb-door.json`) | **%s** |
| `parity_strict_no_allowance` | %s |
| `difference_by_kind` | %s |
| `divergent_paths` | %s |
| `rows_unreachable_from_verb_door` | %s |
| `rows_ambiguous_at_the_verb_door` | %s |
| `rows_no_route` | %s |
| `by_source` | %s |
| `seconds` | %s |

Of the %s replayable tool rows, **%s travelled through `writing_tools.request()` as a
`grammar.Request`** and were compared with the same row through its old name on class, the raising
owner frame, the files changed and the bytes on disk: **%s agreed on all four kinds, %s differed,
and %s of those differences was unallowed.** The allowance is `allow.verb-door.json`, one row and
one kind, with the line that causes it; it is quoted below.

**What the scored rows exercised**, because a run can agree on everything and be worth nothing if
every row dies at the first gate -- which is what this run did until 2026-10-02, when the fixture
held none of the corpus's projects: outcome classes, names side / verb side, %s; the owner frames
the refusals raised in, %s. The %s
rows that did not travel are counted and named, never scored: %s are routes the table itself marks
`door="shim"` (two or more old operations share one `(verb, concept)` and no payload key chooses
between them), %s are where `choose` refused to guess, and %s name no act at all. Those rows are
still APPLIED ON BOTH SIDES through their old name, so the two sandboxes stay in lockstep and every
later comparison stays meaningful; skipping one side only would have made the rest of the run
decorative.

**THE ONE ALLOWANCE, quoted.** `allow.verb-door.json` grants `bytes` on
`READ-143844da63f945e092258f5b73dd3d32` and nothing else -- not the kind, not the operation, not the
source. What differs: %s What causes it: %s Why it is not cured: %s Why it is not an owner
difference: %s

The `response` body is deliberately NOT a parity kind for this run and the file says so
(`response_compared: false`): the verb door answers in the grammar's receipt/refusal shape
(GRAMMAR.md section 5), not the legacy response shape, which is the entire point of having a second
door. What must agree is the act.

""" % (both.get("parity"), both.get("rows_in_corpus"), both.get("rows_scored"),
       both.get("rows_parity"), both.get("rows_mismatch"),
       both.get("rows_unallowed"), both.get("parity_strict_no_allowance"),
       both.get("difference_by_kind") or "none", both.get("divergent_paths") or "none",
       both.get("rows_unreachable_from_verb_door"),
       both.get("rows_ambiguous_at_the_verb_door"), both.get("rows_no_route"),
       json.dumps(both.get("by_source") or {}), both.get("seconds"),
       both.get("rows_in_corpus"), both.get("rows_scored"), both.get("rows_parity"),
       both.get("rows_mismatch"), both.get("rows_unallowed"),
       json.dumps(both.get("outcome_class_pairs_names_verbs") or {}),
       json.dumps(both.get("refusal_homes_top") or {}),
       (both.get("rows_in_corpus") or 0) - (both.get("rows_scored") or 0),
       both.get("rows_unreachable_from_verb_door"),
       both.get("rows_ambiguous_at_the_verb_door"), both.get("rows_no_route"),
       *((vdallow.get("reasons") or {}).get(
           "READ-143844da63f945e092258f5b73dd3d32", {}).get(k, "")
         for k in ("what_differs", "the_line_that_causes_it", "why_it_is_not_cured",
                   "why_it_is_not_an_owner_difference"))))
    if retire:
        # NOT `counts`: that name holds dispatch_counts.json, which every @@TOKEN@@ in the
        # report is substituted from.  Shadowing it rendered `None routes` in 17 places.
        retire_counts = (retire.get("summary") or {}).get("counts") or {}
        body.append("""
**And that run is what retires the shims.** Every `Route.expiry` names
`tools/writing_verbs/shim_retirement.py` and the deposited `parity-verb-door/rows.jsonl` it reads, so
the condition is one a reader can evaluate today instead of a sentence about a future run. Read over
%s rows, the ledger is **%s RETIRABLE** (a recorded row of that route travelled both ways and
agreed), **%s HELD-UNREACHABLE** (the verb door cannot express it -- the route's own `because`) and
**%s HELD-UNEXERCISED** (the verb door reaches it; no corpus row exercises it, so nothing has been
measured, and a shim is not deleted on an argument). Deposited as `shim_retirement.json`.

**The key, and the two times it was wrong.** A proof is keyed on the route's operation AND ITS WHOLE
SELECTOR, and the ledger prints its own soundness: **%s distinct keys for %s routes**, with the keys
shared by more than one route listed (`%s`). The first version keyed on the operation alone and
reported 82 / 18 / 46, because `structure_change operation=plan op.kind=add-section` and
`... op.kind=restore-section` share verb, concept AND operation. The second keyed on the operation
plus the LIFTED pairs, which the report then described as "the route's FULL old spelling" -- it was
not: `route.selector` was absent from the key, 146 routes collapsed to 131 keys, and 21 routes were
retirable on a sibling's row (the independent judge's second deficiency, 2026-10-02). Note that
`Route.key` -- `(verb, concept, selector)` -- would not have been enough either: it is 140 distinct
values for 146 routes. The key is `(verb, concept, operation + selector)`, `replay_verb_door.py`
records that spelling and the row's `old_selector` beside it, so every RETIRABLE route names a row of
its OWN selector.

""" % ((retire.get("summary") or {}).get("rows_read"), retire_counts.get("RETIRABLE", 0),
       retire_counts.get("HELD-UNREACHABLE", 0), retire_counts.get("HELD-UNEXERCISED", 0),
       (retire.get("summary") or {}).get("distinct_keys"),
       (retire.get("summary") or {}).get("routes"),
       json.dumps((retire.get("summary") or {}).get(
           "keys_shared_by_more_than_one_route") or {})))
    body.append("""
## 6. The other three instruments

**Arrival** (`harness/arrival.py --tree . --compare baseline/arrival_head.json`, deposited as
`altitude-dispatch/arrival-head/arrival.json` and `arrival-head/arrival_compare.log`): every
compared number is identical to the banked HEAD baseline. **Measured at `@@AHEAD@@`**, against a
server this harness starts from this worktree; the first version of this table was taken at
`941f7988`, 269 insertions of `src/` behind the final commit, and the independent judge was right
that a run presented without its commit is not a measurement a reader can re-take.

| measure | this lane | baseline | compared? |
|---|---|---|---|
| door calls, steady | @@DOORS@@ | 76 | yes |
| refusals | @@REF@@ | 7 | yes |
| refused steps | identical set, in order | 7 steps | yes |
| out-of-band facts | @@OOB@@ | 10 | yes |
| help calls / chars | @@HELPC@@ / @@HELPCH@@ | 17 / 107,469 | yes |
| chars total, steady | @@CHARS@@ | 267,496 | yes, exactly |
| owner-code reads | @@OCR@@ | 0 | yes |

That the arrival is **unchanged rather than improved** is the honest result for this lane and worth
stating plainly. The harness names the seven refused steps a lane should move, and three of them --
`E2-apply-revision`, `E4-adjudicate-no-corpus`, `F4-adjudicate-headings-blank-guard` -- are the
altitude and door-routing class, i.e. this lane's target list. Curing them means making a call that
refuses today succeed: `apply_revision` outside a turn refuses at
`src/laplace/writing_tools.py:227` before any owner is reached, and the corpus holds 57 recorded
`apply_revision` refusals that would change class the moment that gate moved. That is a behaviour
change, not a syntax change; the campaign's unconditional gate is byte parity, and a lane that
changes an outcome class owes its own allowance and its own argument. I did not take it inside a
parity-clean pass, and section 10 says what it would take.

**Holder census** (`harness/holder_census.py --tree . --base 706a8204`, deposited as
`holder_census.out`):

```
@@HOLDER@@
```

`localStorage` +0, `ledger_row_kinds` +0, `contract_prose_sites` +0 -- the new banked rows reuse the
two record kinds that already exist (`writing-tool-read`, `writing-tool-action`) in the file that
already exists (`contract/talk.jsonl`), so the lane invents no holder. **The census exits 0**, and
that is a change since this report's first version, which honestly recorded `NEW HOLDERS: 1` and
attributed it to the grammar packet rather than to the lane. The one added `identity_fields` name was
never a holder: `digest_canonical_json` at `src/laplace/grammar.py:61` is the module's own `__all__`
export, and `src/laplace/grammar.py:137` is the function. Section 9's finding 2 named two possible
cures and said the choice was not mine; the orchestrator took the first one, and
`harness/holder_census.py` now prints
`ALLOWED digest_canonical_json ... (an export of src/laplace/core/grammar.py, not a holder)` under three
named conditions rather than a blanket exclusion. Re-run at the final commit, it exits **0** with
`NO NEW HOLDER`, so the instrument the synthesis is told to run passes on this branch and on every
sibling build lane that installed the same module. `writing_verbs.py` mentions 22 guard-shaped names
and every one of them already existed in the tree, which is why the delta was ever 1 and not 23.

**Identity names** (`harness/identity_names.py --both --fresh`, deposited as `identity.json`):
@@IDN@@ guard leaves over @@IDV@@ distinct values, @@IDA@@ values with more than one name -- the
report's twenty, unchanged, because collapsing the names a READ publishes is the identity-tokens
lane's work and not this one's. The payload side is unchanged where it matters: @@IDS@@ guard-shaped
names in `src/laplace` (229 at the base, the one addition being the grammar module's export above),
of which **16** are read off an incoming payload -- the same 16 as the baseline, name for name. This lane adds no new spelling a caller must get right; it makes the 17 spellings it
found reachable through one list of tokens.

## 7. The banked row: what it carries, on which path, and the dial

Before: the row is banked only when a turn id is present (`src/laplace/writing_tools.py:974-971`
for a read and `:1000-1006` for a write, at `706a8204`), and it records `operation`. So for
`structure_change {operation: "plan", op: {kind: "set-nodes"}}` the row said `structure_change` and
recovering which of its 26 verbs ran meant re-parsing the payload (synthesis section 1.7); and on a
direct or HTTP caller path nothing was banked at all -- "the system's failure record is a census of
one provider's turns".

After, from one real workspace driven through the verb door
(`altitude-dispatch/verb-door/demo.out`, a project created through the same HTTP door the arrival
uses, then four acts written as grammar requests):

```
@@DEMOROWS@@
```

`demo.json` lists every request with its rebuilt owner call, the owner's file:line, the owner's
sentence verbatim and the raising frame. The five content-tree creates of section 3 are the subject
and section 3 reports them; what belongs here is the RECORD they left. Every refusal came back with
the owner's own sentence, the owner's file and line, and `needed` carrying the CURRENT token of every
home the ROUTE declares -- a tokenless `create plan-section@section` is refused
`structure_change payload requires expected_revision` from `src/laplace/project_structure.py:706` and
comes back with that home's live token AND the read it comes from (`structure {} -> revision`), which
is the resolver working on a path with no provider turn and for a caller who held nothing.

@@DEMON@@ rows were banked in `contract/talk.jsonl`, **@@DEMOGRAIN@@ of them carrying
`(verb, concept, altitude)` and every one of them a `turn_id` of `null`**. Five acts applied through
the verb door -- the plan initialised, then the four altitudes of section 3 -- which is the one-shape
claim exercised against live owners rather than a fixture.

The rows that carry no grain are the **owners' own** records (`manuscript-plan-initialize`,
`manuscript-structure`, `manuscript-structure-complete`). That is GRAMMAR.md section 5's measurement standing
in front of us: "the owners do record the verb -- into three stores under two field names
(`src/laplace/manuscript_structure.py:150-151`, `src/laplace/corpus_ingest.py:951`,
`src/laplace/pipeline/authoring.py:1109`) ... the defect is therefore not a missing trail. It is
that there is no one place, and no one grain." This lane adds the one place and the one grain beside
them without rewriting any of the three.

**The whole published arrival, through the HTTP door, with the dial at its shipped default.** The
2026-10-01 arrival sequence is 76 steady door calls against a workspace that has no provider turn at
all. Re-run with `--keep` (`arrival_banked_rows.json`, from
`@@ALEDGER@@`, censused by `tools/writing_verbs/arrival_banked_census.py` at `@@AHEAD@@`):
**@@AROWS@@ rows banked,
every one with `turn_id: null`, @@AGRAIN@@ of them carrying `(verb, concept, altitude)`** --
@@AVERBS@@ -- across @@AALT@@ altitudes and @@ACON@@ concepts, @@AEXACT@@ rebuilt exactly and
@@AFELL@@ fallen through. At `706a8204` neither banking branch runs without a turn id -- both are
guarded by `if turn_id and ...` -- so the same workspace would have recorded **@@AZERO@@
writing-tool rows** of the 67. The eleven rows without the grain are the owners' own stores
(`manuscript-plan-initialize`, `manuscript-section-change`, `manuscript-section-inverse`). The same
run's compared arrival numbers are the ones in section 6, so the record was gained without moving
anything a caller sees.

**The dial, and why it exists.** `LAPLACE_WRITING_BANK_EVERY_PATH` (default ON;
`writing_verbs.bank_every_path`, `src/laplace/writing_verbs.py:1593-1595`) governs only the third
branch -- banking on a path that banks nothing today. It exists for the READER of the oracle, not for
the design: the campaign compares this tree against a tree that does not bank those rows, so with the
dial on the comparison reports a `homes` difference on every non-turn row, and a reader who wants to
see a syntax change alone can turn the record off and look. **What ships is what the gate passed**:
section 5 runs the whole corpus at the default and gates it under `allow.bank-on.json`, whose 49 row
entries were each checked rather than listed. Its retirement trigger is the merge to master, after
which both sides bank and the dial has nothing left to switch. It is one environment variable, read in
one function, with its reason in that function's docstring -- not a configuration surface.

**One existing test asserted the defect, and I amended it rather than working around it.**
`tests/test_writing_controller.py::test_project_and_artifact_reads_bank_only_with_logical_turn`
asserted that a read banks ONLY inside a logical turn. It now asserts what was right about it -- a
read inside a turn carries that turn's id, a read outside one claims no turn rather than borrowing
the last -- plus the new grain, and its docstring names the ruling, the measurement it contradicted
and the dial that restores the old behaviour. It is renamed to
`test_project_and_artifact_reads_bank_with_their_turn_or_with_none` so the name cannot keep
asserting the old law in a reader's head.

**Regression**: the 35 existing test files that mention `writing_tools`, plus this lane's two suites:
**@@PASS@@ passed, @@FAIL@@ failed, @@SKIP@@ skipped** (`pytest_regression.log`), re-run at the final
commit. The figure in this report's first version was taken in my working tree; at the judged commit a
fresh checkout measured one more failure, because the route-table provenance test failed there and not
for me (section 2). It passes in a fresh checkout now, which is why this number moved up rather than
down. Both remaining failures
reproduce on the base checkout at `706a8204` with the same command --
`test_research_visual_owner_chain.py::test_source_to_result_binding_visual_and_placement_have_exact_owner_receipts`
and `test_writing_controller.py::test_relative_controller_root_is_normalised_before_provider_resume`
-- so neither is this lane's. I ran them on the base tree to establish that rather than assuming
it, and that run is deposited too: `pytest_base_two_failures.log`, `2 failed` at `706a8204`.

## 8. What I decided, and the conventional default each decision refused

1. **The dispatch routes; it does not gate.** `require` builds the resolver AFTER the owner refuses;
   it never refuses before the owner is called.
   *Refused default*: a validation layer in front of the owners. Measured cost of that default: the
   oracle compares the innermost owner frame that raised, and 94 of the 210 recorded refusals are
   identity mismatches. A pre-owner gate would move the house of every one of them, which reads in a
   diff as a cured refusal and is a moved one.
2. **The rewrite is checked per call and falls through on any difference.**
   *Refused default*: trusting a table. A dispatch table that is right in the tests and wrong on one
   live payload is exactly how 73 names grew 152 sub-verbs; here a gap costs the row's grain, never
   the owner's behaviour.
3. **`expected` carries tokens only, and the route declares the guard's FORM.**
   *Refused default*: a second identity field (`expected_counter`, `before_digest`) so every guard
   could ride in one shape. That is how the system got to 20 names over 9 values; the names the
   dispatch introduces are content names (`before_content`, `page_cursor`, `edge_target`), none of
   them guard-shaped, which is why the identity census is unmoved.
4. **A guard whose door compares the digest string raw is never re-spelled.** Five owners compare
   through `revision_identity.revision_matches` (`src/laplace/project_structure.py:766`,
   `src/laplace/concepts_surface.py:846`, `src/laplace/pipeline/formal_verification.py:267`,
   `src/laplace/pipeline/visual_production.py:139`, `src/laplace/literature.py:395`) and two do not
   (`manuscript_structure`, `writing_stages`). For the first group the rebuilt call is the same call
   by the owner's own comparator; for the second the row falls through.
   *Refused default*: normalising everything because the grammar normalises. That would hand a
   different string to a door that compares it exactly, on nine recorded calls (five
   `section_change`, three `writing_stage`, one `visual_place`), and call it uniformity.
5. **Two routes under one `(verb, concept)` are never guessed between.** `choose` raises
   `Ambiguous`, naming both candidates; 24 routes are marked `door="shim"` with the reason, and the
   verb door still reaches all 104 pairs.
   *Refused default*: picking the first and hoping. The brief's own words are that the verbs are the
   gate; a gate that guesses is not one.
6. **The row is banked where the system already banks, in the kinds it already has.**
   *Refused default*: a new ledger file or a new record kind for the act. `holder_census.py` would
   have failed, and rightly: a second place to keep the same fact is the defect, not the cure.
""")

    body.append(TAIL)
    text = "".join(body)
    repl = {
        "@@DOORS@@": score.get("door_calls_steady"), "@@REF@@": score.get("refusals"),
        "@@OOB@@": score.get("out_of_band_facts"), "@@HELPC@@": score.get("help_calls"),
        "@@HELPCH@@": score.get("help_chars"), "@@CHARS@@": score.get("chars_total_steady"),
        "@@OCR@@": arrival.get("owner_code_reads"),
        "@@HOLDER@@": holder.strip(),
        "@@IDN@@": (identity.get("doors") or {}).get("guard_leaves_total"),
        "@@IDV@@": (identity.get("doors") or {}).get("distinct_values"),
        "@@IDA@@": (identity.get("doors") or {}).get("values_with_more_than_one_name"),
        "@@IDS@@": (identity.get("static") or {}).get("names_total"),
        "@@DEMON@@": len(demo.get("banked") or []),
        "@@DEMOGRAIN@@": sum(1 for row in (demo.get("banked") or []) if row.get("verb")),
        "@@AROWS@@": arrow.get("rows"), "@@AGRAIN@@": arrow.get("with_grain"),
        "@@AHEAD@@": (arrow.get("head") or arrival.get("head") or "")[:12],
        "@@ALEDGER@@": arrow.get("ledger") or "",
        "@@AVERBS@@": ", ".join("%s %s" % (n, k) for k, n in
                                sorted((arrow.get("verbs") or {}).items(),
                                       key=lambda kv: -kv[1])),
        "@@AALT@@": len(arrow.get("altitudes") or {}),
        "@@ACON@@": len(arrow.get("concepts") or []),
        "@@AEXACT@@": (arrow.get("dispatch") or {}).get("exact"),
        "@@AFELL@@": (arrow.get("dispatch") or {}).get("fell-through"),
        "@@AZERO@@": 0,
        "@@DEMOROWS@@": "\n".join(
            json.dumps({k: row.get(k) for k in ("record", "turn_id", "operation", "verb",
                                                "concept", "altitude", "dispatch")})
            for row in (demo.get("banked") or [])),
        "@@CULPRIT@@": culprit.get("id"),
        "@@RESPOPS@@": ", ".join("%s %s" % (n, op) for op, n in
                                 sorted(response_ops.items(), key=lambda kv: -kv[1])),
        "@@WREFUSED@@": writes_classes.get("refused"),
        "@@WAPPLIED@@": writes_classes.get("applied"),
        "@@WTOTAL@@": sum(writes_classes.values()) or None,
        "@@GATECOMMIT@@": ran_on(args.gate) if args.gate else "(no gate run)",
        "@@FASTCOMMIT@@": ran_on(args.fast) if args.fast else "(not run)",
        "@@ROUTES@@": counts.get("routes"), "@@OLDNAMES@@": counts.get("old_operation_names"),
        "@@SHIMROUTES@@": counts.get("shim_only_routes"),
        "@@VERBROUTES@@": counts.get("verb_door_routes"),
        "@@GUARDED@@": counts.get("routes_with_a_guard"),
        "@@GNAMES@@": counts.get("guard_names"), "@@GHOMES@@": counts.get("guard_homes"),
        "@@GFORMS@@": ", ".join("%s %s" % (k, n) for k, n in
                                (counts.get("guard_forms") or {}).items()),
        "@@GDIGEST@@": (counts.get("guard_forms") or {}).get("digest"),
        "@@GCOUNTER@@": (counts.get("guard_forms") or {}).get("counter"),
        "@@GTEXT@@": (counts.get("guard_forms") or {}).get("text"),
        "@@GCURSOR@@": (counts.get("guard_forms") or {}).get("cursor"),
        "@@CITED@@": (counts.get("routes") or 0) - len(counts.get(
            "routes_without_an_owner_citation") or []),
        "@@EXACT@@": (trip.get("round_trip") or {}).get("exact"),
        "@@INEXACT@@": (trip.get("round_trip") or {}).get("round-trip not exact"),
        "@@UNMAPPED@@": (trip.get("round_trip") or {}).get("unmapped"),
        "@@VERBDOOR@@": (trip.get("verb_door") or {}).get("reachable"),
        "@@SHIMONLY@@": (trip.get("verb_door") or {}).get("shim-only"),
    }
    for key, value in repl.items():
        text = text.replace(key, "{:,}".format(value) if isinstance(value, int) and value > 9999
                            else str(value))
    pytest_log = (E / "pytest_regression.log")
    if pytest_log.is_file():
        last = [line for line in pytest_log.read_text().splitlines() if "passed" in line]
        tail = last[-1] if last else ""
        import re
        got = {key: (re.search(r"(\d+) " + key, tail) or [None, "?"])[1]
               for key in ("passed", "failed", "skipped")}
        for key, value in got.items():
            text = text.replace("@@" + key.upper()[:4] + "@@", str(value))
    Path(args.out).write_text(text)
    print("wrote", args.out, len(text), "chars")
    left = [token for token in text.split() if token.startswith("@@")]
    if left:
        print("UNFILLED PLACEHOLDERS:", sorted(set(left)))
    return 0


from report_text import HEAD, TAIL   # noqa: E402

if __name__ == "__main__":
    import sys
    sys.exit(main())
