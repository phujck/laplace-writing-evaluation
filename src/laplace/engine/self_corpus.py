"""self_corpus.py - the engine ingests itself, and reconstructs its own orientation.

The bootstrap of reconstruction-as-projection, turned on Eigen first - the obvious first corpus
is the engine itself. Today ``hello`` (``EIGEN_PROTOCOL.md`` Part A) makes the orchestrator
LINEARLY READ five whole files - ``HANDOFF.md`` + the latest dated handoff + the diary tail +
``EIGEN_ARCHITECTURE.md`` + the live state - and work from the raw. That is the engine's own root
disease, the one the 2026-06-07 diary names: *substitute the full prompt for ingested knowledge,
every session.* This module is the cure at that root.

The engine-self is INGESTED into a graded hierarchy, and a CALL reconstructs only the slice the
caller needs:

  * grade 0 - the FIXED POINT: what is true now, what to do next, what is blocked on the author.
              The slice that "meets the agent" - small enough to act on directly.
  * grade 1 - the DELTA: the latest session's hand-off + the open author-forks + engine health.
  * grade 2 - the MAP: the architecture dockets + the diary - reached only on descent, never
              inlined (pointed at, by section title).

Each grade EMBEDS its own reconstructor - the codec's *distributed code*, after ``seed_from_gap``:
the shard carries the ``descend`` call (the brief + the source pointers) that regenerates the NEXT
grade when FIRED. Descending is firing the embedded call; reconstruction propagates down only as
far as the caller needs. This is the scaling law made structural: a grade-``k`` projection reads
only grade-``k``'s sources, so its cost is O(width-at-``k``), never the whole corpus - grade 2's
heavy files (architecture, diary) are *pointed at*, not read, by a grade-0 call.

``reconstruct_self(repo_root, grade=0)`` is a pure function of the engine's files, so its grade-0
output is a genuine FIXED POINT of the current engine state: the author's next message is a
PERTURBATION from it into the grade-0 algebra, and the sew-up re-ingests the perturbation+response,
moving the fixed point. The loop is the engine, fired on itself.

Conjecture, seams showing - the first rung of Eigen-as-its-own-corpus. The reconstruction here is
deterministic extraction (sections + live rows + pointers); the *LLM* firing is the descent the
orchestrator performs when it opens a grade against the meter. Built smallest-real-thing first.
"""

from __future__ import annotations
from laplace.core.checkout import source_tree

import json
import re
from pathlib import Path
from typing import Any

# The engine-self source files are no longer hardcoded here (N21). "What is the self" is ONE
# definition - ``self_shard.self_substrate`` - a discovered subset of the directory conceptric,
# consumed by BOTH this reconstructor (the hello) and ``canon._route_self_knowledge`` (orient).
# The hello reconstructs THROUGH the conceptric: discover the self-nodes, read them through the one
# sealed reader (``self_shard.read_source``), carve the graded slice. See ``_substrate`` / ``_source``.

_LIVE_MARKER = "\U0001f534"   # the red circle: OPEN_STACK's "live" status legend
_AIM_MARKER = "NEXT SESSION AIM"
_AIM_CAP = 6000               # keep grade 0 small - the fixed point must "meet the agent"

# THE DESIRE VECTOR (OPEN_STACK Stratum 0, 2026-07-13): the wants shard rides the fixed point one
# stratum UPSTREAM of the spine's how-to-fire - what to want before how to fire it. A want row three
# closes stale (its date strictly older than >=3 distinct later handoff dates) is FLAGGED, never
# silently carried - the same "surface the drift, don't read it quiet" law as the fork handles.
_WANTS_MARKER = "STANDING WANTS"
_WANTS_STALE_CLOSES = 3

# THE STANDING-THREADS SHARD (the ideation loop, 2026-08-19). The wake projected session
# continuity and NOT conceptual continuity; the bench measured the cost (see ``_threads_shard``).
# The shard is refs-only and sized like the conscience shard - rows, not bodies. The caps below
# are the whole knob: rows per class, and an honest body cap behind them.
_THREADS_DESIGN_ROWS = 8       # the live ideation front (DESIGN_*.md + the mathematics), newest first
_THREADS_DOCKET_ROWS = 2       # the standing conjectures (EIGEN_ARCHITECTURE.md dockets), newest first
_THREADS_NAME_CAP = 44
_THREADS_HOOK_CAP = 88
_THREADS_BODY_CAP = 2000
_THREADS_SOURCE = "DESIGN_*.md + ATLAS_MATHEMATICS.md + EIGEN_ARCHITECTURE.md (headings only)"
_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.M)
# the house's design-title stamp: "DESIGN 2026-08-19 — ", "Design memo — ", "DESIGN — "
_DESIGN_STAMP_RE = re.compile(r"^(?:DESIGN|Design)(?:\s+memo)?\s*(?:\d{4}-\d{2}-\d{2})?\s*[—–:-]\s*")
_DOCKET_PREFIX_RE = re.compile(r"^The docket\s*[—–-]\s*", re.IGNORECASE)
_TRAILING_DATED_PAREN_RE = re.compile(r"\s*\([^()]*\d{4}-\d{2}-\d{2}[^()]*\)\s*$")

# THE GRADE-0 THIN-FIXED-POINT BUDGET (the "meet the agent" invariant, 2026-06-13): the grade-0
# projection must serialize under this many chars - small enough to act on without flooding the cold
# instance's context. Measured 2026-06-13: the flat fixed point is ~18.3k and carries the full
# next-move list; NEXT-0's conjectured atom-swap landed OVER it and truncated the moves, so the fixed
# point stays flat and the bound is GUARDED by a test (test_self_corpus), flat and ring-flag paths.
#
# ── RE-ANCHOR 3 (2026-08-19), BY THE IB ROUTE — THE NUMBER IS NOW DERIVED, NOT PICKED ──────────────
# The first two anchors were hand-picked ceilings (20000, then 21000 at W-TRIAGE 2026-07-22 when the
# core measured 20334). Both went stale the same way, and ATLAS_MATHEMATICS §7.1 measured the end
# state on 2026-08-16: payload 21,723 / core 21,586 against a 21,000 bound, with the displacement
# enforcer ALREADY DRAINED to its single "+N earlier ingested" handle. A bound that is breached with
# no lever left is not a bound; it is a comment.
#
# The 2026-06-06 codec frame says what the number actually is: the wake payload is a point on a
# RATE-DISTORTION curve - rate R = serialized chars, distortion D = orientation the reader loses. So
# the budget is DERIVED FROM WHAT THE CHANNEL MUST CARRY, in three named, measured terms, and the
# expression below IS the derivation (change a measurement, the bound moves with it):
#
#   R  =  core  +  ingested allowance  +  accretion allowance
#
#   core                 the payload minus its ingested tail - what the enforcer cannot displace.
#                        MEASURED 2026-08-19 on this tree, both modes, with the threads shard in:
#                        engine 22,199 · person 31,911 (person carries the +9.7k identity block).
#                        TWO RATES BECAUSE THERE ARE TWO CHANNELS: the engine/worker projection
#                        rides in every dispatched agent's prompt, the authored person wake is read
#                        once by the orchestrator. One constant could only ever be true of one of
#                        them - and it was true of the engine only, which is why the DEFAULT wake
#                        (person, CLAUDE.md) has been ~9k over an unenforced bound unnoticed.
#   ingested allowance   one session's fresh ingest carried at FULL fidelity, everything older
#                        coarse-grained (that is exactly what lever 1 does). DERIVED from the
#                        ledger, 2026-08-19: 67 live grade-0 entries, median body 775 chars, mean
#                        2.45 entries per ingest-date -> ceil(2.45) x 775 = 2,325.
#   accretion allowance  the core's measured drift, so the anchor is not stale on contact. Three
#                        banked anchors: 18,300 (2026-06-13) -> 20,334 (2026-07-22) -> 21,586
#                        (2026-08-16) = ~50 chars/day across both intervals. The observed re-anchor
#                        cadence is monthly -> 50 x 30 = 1,500.
#
#                        THE DERIVATION'S RATE IS MEASURED WRONG BY ~53x, AND THE NUMBER IS RECORDED
#                        HERE RATHER THAN ACTED ON (wake-rate bench wave 2, 2026-08-20,
#                        evidence/WAKE_RATE_BENCH_2026-08-20/REPORT_v2.md §7):
#                          derivation assumes  ~50 chars/day   (2026-06-13 -> 2026-08-16, 3 anchors)
#                          measured            +2,637 chars    in ONE day: person core 31,911
#                                              (2026-08-19 anchor) -> 34,548 (2026-08-20, measured)
#                        At the observed rate the 3,000-char allowance - sized as a MONTH's headroom -
#                        is consumed in ~1.1 days. Two readings ride together and neither is settled
#                        by this measurement: one day is one sample (the audit day was an unusually
#                        heavy close), and a month-shaped allowance against a day-shaped drift is a
#                        constant that will be stale on contact rather than merely stale at the
#                        cadence. Recorded as an argument for re-deriving the core SOONER, never for
#                        widening the constant - the wave-1 12k branch forbids the second.
#
# [HIS] THE OPEN HALF, RECORDED NOT FAKED. This derives the rate from what the payload COSTS and
# what the channel must ABSORB. It does not derive it from what the READER needs - the D side of
# R(D): the smallest R at which a cold instance still orients. That measurement exists in principle
# (run the reconstruction bench at progressively coarse-grained rates and score the stranger's
# rehearsal) but it is a multi-session cost and a judgement about acceptable distortion, so it is
# his call, not mine to assume. Second, related ruling: person core is 31,911 with 9,698 of it the
# identity block - whether the authored wake should pay ~10k for identity every time, or whether
# identity should itself go refs-only like the conscience shard, is a design ruling, not a
# measurement. Until both are ruled, the enforcer's lever 2 (below) is what keeps the bound HONEST:
# a breach now costs a loud, marked, descendable body rather than a silently-broken promise.
_GRADE0_CORE_ENGINE = 24500        # RE-DERIVED 2026-08-20 FROM WHAT SCORED - the wave-1 decision
                                   # table's own 12k branch discharged ("re-derive the core from what
                                   # scored, not from what is currently written, BEFORE ANY CONSTANT
                                   # MOVES"). Four registered passes, 1,197 blind-graded answers
                                   # (evidence/WAKE_RATE_BENCH_2026-08-20/engine_core_rederive/,
                                   # bundle commit 085aea0b). The instrument was repaired first: the
                                   # banked engine ladder scored 18 tasks and predated T19-T21, so
                                   # ``spine`` - 30.9% of the engine floor - had never been scored on
                                   # ANY engine arm. On the repaired 21-task set the knee holds at R21.
                                   # THE COMPOSITION THIS CONSTANT ANCHORS (engine channel):
                                   #   ten components measured to EARN their chars against a
                                   #   confounder-free base - shard:threads (-2), shard:next-aim (-2),
                                   #   spine, node_forms, descend, bequest, projects, wants,
                                   #   conscience, work-orders (-1 each);
                                   #   + triple and live_probe, kept on the NULL-MEASUREMENT RULE (no
                                   #     v2 task scores them; silence is never evidence of no value);
                                   #   + the 2,105-char standing-law digest (``law_digest`` below);
                                   #   - ``note`` (183 chars, tested delta 0) dropped from the ENGINE
                                   #     projection only - see ``_engine_projection``.
                                   # The derivation proposed cutting ``shard:live-forks`` too and
                                   # named its own conservative branch in case the fragility read as
                                   # too thin. IT DID, at apply, and the branch is what landed: three
                                   # pre-existing organs (the hello briefing's Blocked-on-you section,
                                   # the cold-wake coverage probe, the §B1 one-reader tests) all read
                                   # that shard through THIS channel. The full reasoning and the run
                                   # that settled it are written out at ``_engine_projection``.
                                   # THE COMPOSITION BEATS THE RATE: this composition scores 20/21
                                   # where the incumbent scores 17/21 at 29,777 chars AND where the
                                   # unbudgeted 93,754-char payload ALSO scores 17/21. More rate was
                                   # never going to buy the missing three; a different composition did.
                                   # Measured 24,422 at apply -> ceil100 24,500 (the derivation's own
                                   # arithmetic for this branch was 24,600, on a tree ~100 chars older;
                                   # this constant is the branch MEASURED rather than computed).
                                   # The one task missed (T18) fails on the descent horizon
                                   # (WO-20260820-fold-horizon-in-the-payload), not on composition.
                                   # ONE INHERITED NUMBER CORRECTED: "8,888 dead chars per packet" was
                                   # headroom of the bound over a knee arm, not measured dead weight.
                                   # Measured dead weight in the engine core is 1,694 chars; the core
                                   # constant RISES (+901) while the budget FALLS (-2,924).
_GRADE0_CORE_PERSON = 28300        # RE-DERIVED 2026-08-21 FROM WHAT SCORED. The 2026-08-20 ruling
                                   # (REPORT_v2.md §6-§7) refused to refresh the 31,911 anchor to
                                   # the then-measured 34,548 - "refreshing an anchor to match its
                                   # own drift is how a drift detector is switched off" - and made
                                   # the refresh conditional on ONE thing: the core being re-derived
                                   # from what scored. That condition is now met, so this move is a
                                   # consequence already on the books, not a new proposal. Four
                                   # registered passes, 1,743 blind-graded answers + an apply arm
                                   # (evidence/WAKE_RATE_BENCH_2026-08-20/person_core_rederive/),
                                   # method reproduced from the engine channel's bundle unchanged.
                                   # THE COMPOSITION THIS CONSTANT ANCHORS (person channel):
                                   #   the components measured to EARN their chars against a
                                   #   confounder-free base - identity.standing_law (-3, the whole
                                   #   standing-law class), shard:threads (-2), spine, node_forms,
                                   #   descend, shard:wants, shard:projects, shard:bequest,
                                   #   shard:next-aim (-1 each);
                                   #   + triple, live_probe, note, shard:live-forks,
                                   #     shard:conscience, shard:work-orders and SEVEN identity
                                   #     sub-blocks, all kept on the NULL-MEASUREMENT RULE (no v2
                                   #     task scores them; silence is never evidence of no value),
                                   #     two of those seven additionally held by the cold-probe rows
                                   #     q-stance / q-soul;
                                   #   ~ identity.standing_law CARRIED BY THE 2,105-CHAR DIGEST
                                   #     instead of the 6,671-char full list (-4,566), measured 3/3
                                   #     in place, all 14 law lines still riding;
                                   #   - identity.budget_note (150 chars) dropped - delta 0 AND no
                                   #     consumer AND a stale render of a one-lever enforcer.
                                   # See _person_projection for the full derivation and the arms.
                                   # THE COMPOSITION BEATS THE RATE HERE TOO: at R30 the proposed
                                   # composition scores 20/21 with nothing coarse-grained where the
                                   # incumbent at the same rate sacrifices work-orders AND
                                   # conscience. Measured 28,297 at apply -> ceil100 28,300.
                                   # WHAT IT BUYS, PLAINLY: one day. The cut is 4,716 chars and the
                                   # re-anchor hands most of it back to the bound - headroom to
                                   # lever 2 goes 2,600 -> 3,705 against the +2,637 chars/day §7
                                   # measured. The drift arms measured both sides: the shipping arm
                                   # +1 day's drift coarse-grains conscience; the proposed arm +1
                                   # day grains nothing and only grains conscience at +2 days.
                                   # The residual is structural and stays named: with the anchor
                                   # tracking the measured core, person headroom is capped by the
                                   # two elastic allowances (3,825) whatever the composition is.
_GRADE0_INGESTED_ALLOWANCE = 2325  # REVERTED to the derived value 2026-08-20. This was 4,650 (2x the
                                   # 2026-08-19 derivation) under his generosity ruling, which carried
                                   # its OWN revert clause: "both revert to the derived values if the
                                   # D-side bench finds the knee below them - the bench outranks
                                   # generosity." The D-side bench ran and the knee is R21, below
                                   # 29,849, so the clause FIRED - this is a consequence already on the
                                   # books, not a new proposal. The rate it produces was MEASURED
                                   # rather than asserted: the engine payload scores 20/21 with NO
                                   # shard coarse-grained at 26,925 (rows_rederive_rate.json
                                   # PROP@26925) and again at the landed 28,325.
                                   # The generosity ruling's own worry - threads/wants first-starved -
                                   # does not materialise: lever 2 never fires at this rate.
_GRADE0_ACCRETION_ALLOWANCE = 1500 # REVERTED to the derived value 2026-08-20 by the same fired clause
                                   # (was 3,000 = 2x the measured-drift derivation).
                                   # BOTH ALLOWANCES ARE SHARED WITH THE PERSON BUDGET, so the revert
                                   # moves grade0_budget('person') 39,561 -> 35,736. MEASURED AT APPLY
                                   # TIME, AND STATED SHARPLY RATHER THAN REASSURINGLY: the person
                                   # payload stays under its bound with NO shard coarse-grained and no
                                   # budget_pressure (34,218 of 35,736) - but it gets there by DRAINING
                                   # LEVER 1 COMPLETELY. The person wake now inlines zero ledger
                                   # entries; all 69 ride behind the single descend handle, and 1,518
                                   # chars separate the authored wake from lever 2 at a drift rate
                                   # §7 above measured at +2,637 chars/DAY.
                                   # That is the drift detector working, not breaking: the person core
                                   # has been over its own 31,911 anchor (34,095 measured) since
                                   # 2026-08-20, and the doubled allowances were what hid it. The
                                   # person channel's composition is NOT re-derived here - only the
                                   # shared elastic terms moved, on the clause's own words - and
                                   # WO-20260820-person-core-rederive is now the load-bearing one.
_GRADE0_BUDGET = _GRADE0_CORE_ENGINE + _GRADE0_INGESTED_ALLOWANCE + _GRADE0_ACCRETION_ALLOWANCE
_GRADE0_BUDGET_PERSON = _GRADE0_CORE_PERSON + _GRADE0_INGESTED_ALLOWANCE + _GRADE0_ACCRETION_ALLOWANCE

# Lever 2's order of sacrifice, as a RANK: 0 goes first, the highest rank goes last, and inside
# a rank the largest body goes first (most rate reclaimed per shard sacrificed). Two shards are
# ranked above the field, in this order and for these reasons:
#
#   next-aim  rank 1 - the fixed point's reason to exist. Everything else in the payload says
#                      what is true; this says what to do next, so it goes only after every
#                      ordinary body has already gone.
#   bequest   rank 2 - the LAST thing lever 2 may touch, after even the next-aim (2026-08-20).
#                      The other bodies are reconstructible: coarse-grain one and the marker
#                      names a node that regenerates it. The bequest is not - it was authored
#                      once, by a self that is gone, and there is no source to descend to that
#                      would produce it again. So the payload spends the whole rest of its rate
#                      before it spends this, and when it finally does, the loud marker and the
#                      budget_pressure line say so by name.
#
# A body already at or under the marker's own length is left alone at any rank (coarse-graining
# it would cost orientation and buy nothing).
#
# THE ORDER RANKS SHARDS ONLY, AND THE REST IS THE IRREDUCIBLE FLOOR - BY DESIGN, NOT BY OVERSIGHT
# (named 2026-08-20 after the wake-rate bench asked why R18 and R12 produced byte-identical
# payloads; evidence/WAKE_RATE_BENCH_2026-08-20/). Lever 2 can reach the eight shard bodies and
# nothing else. Coarse-grain all eight and the person payload still measures 21,951 chars, of which
# identity (11,599) and spine (3,196) are 67% - two thirds of what a wake costs at the bottom sits
# outside this map, permanently. The bench measured what that floor buys:
#
#   identity  52.8% of the person floor, and it IS the standing-law class. Its own arm scores 3/3
#             standing-law at EVERY rate down to the floor; refs-only it scores 0/3 at every rate,
#             full rate included. The engine channel is the clean control - it carries no identity
#             block at all and scores 0/3 standing-law at all nine of its arms, A0 (unbudgeted)
#             included, with the provenance pass finding no carrier for those tasks anywhere in the
#             payload. The law reaches a reader through this block and through nothing else, so it
#             is not a candidate for the sacrifice order at any rate: it is the floor.
#   spine     30.9% of the ENGINE floor (the largest single block once identity is gone). The bench
#             scores it at zero because NO TASK ASKS ABOUT IT - a null measurement, never evidence
#             of no value. Cutting a block on that silence would be the bench's own v1 failure with
#             the sign flipped, so the first move of any core re-derivation is to mint tasks for
#             spine / node_forms / descend, not to trim them.
#
# So: this rank is the order of sacrifice among the DROPPABLE bodies, and the floor above is a
# design commitment. Anything proposing to shrink the floor owes a scored task for the block it
# wants to cut, first.
#
# WO-20260820-mint-floor-block-tasks (same day): the null measurement above is fixed. T19/T20/T21
# land in scripts/reconstruction_bench_tasks_v2.json, one per block (spine/node_forms/descend),
# and score 3/3 at EVERY rung of the person ladder, A0 through R12 - the same footing as the
# standing-law controls, confirming this comment's own claim that the three blocks ride outside
# lever 2's reach (evidence/WAKE_RATE_BENCH_2026-08-20/REPORT_v2.md §9).
#
# WO-20260820-fold-horizon-in-the-payload (same day, REPORT_v2.md §5): T18 measured that a
# claim-evidence question about evidence banked hours earlier is unreachable by descent at every
# rate - descent only reaches what the last fold folded in, and nothing said so. The cure landed
# on the SEMANTIC block, not this one (recursive_read.top_of_map's `fold_horizon`: last-fold time
# + HEAD-at-fold from `git log` on .meaning_tree.json's own history, + a warning when HEAD has
# since moved) - that block is where the descendable map is actually composed, so the horizon
# lives beside the map it describes. Cost: ~230 chars quiet (HEAD unmoved), ~330 with the warning
# firing - against the +2,637 chars/day drift REPORT_v2.md §7 already measured (2026-08-20 run,
# person core 31,911 -> 34,548), i.e. under 3 hours' worth of an already-generous daily allowance
# for a line that answers the bench's own named gap. Not a candidate for this rank either: it is
# three fields, not a body.
_BUDGET_SACRIFICE_RANK = {"next-aim": 1, "bequest": 2}
_COARSE_GRAIN_FLOOR = 200


def grade0_budget(mode: str | None = None) -> int:
    """The grade-0 rate for one channel: person (the authored wake) or engine (the worker/ambient
    projection). Two channels, two rates - see the derivation above."""
    return _GRADE0_BUDGET_PERSON if mode == "person" else _GRADE0_BUDGET

# THE ORIENT TRIPLE (friction RW-20260711-104316-400002): a grade-0 call returned the graded index
# only - no what's-true-now/next/blocked-on-author - so a cold remote wake was FORCED into the
# five-file linear fallback CLAUDE.md says must not be the default ("the reconstructed fixed point
# does not carry the live-state triple the protocol promises"). The cure: a compact triple, cut
# MECHANICALLY (regex/section-extraction, no LLM call - the reconstruction stays a pure function of
# the engine's files) from the same three live sources the shards below already read, riding IN the
# payload as an additive key so existing consumers (the 'shards' walkers) are untouched. Budget-capped
# so it can never itself threaten the flat fixed point's own 20k bound (_GRADE0_BUDGET above) - the
# three caps sum to the budget below, each field honestly marked when truncated.
_TRIPLE_TRUE_NOW_CAP = 700
_TRIPLE_NEXT_CAP = 500
_TRIPLE_BLOCKED_CAP = 300
_TRIPLE_BUDGET = _TRIPLE_TRUE_NOW_CAP + _TRIPLE_NEXT_CAP + _TRIPLE_BLOCKED_CAP  # == 1500

# A last-banked verdict phrase, if the newest handoff's opening (or near it) states one - "the probe
# verdict" the triple's true_now carries is what was already BANKED at close, not a live subprocess
# call (the live git/pytest probe stays the separate, un-cached ``live_probe`` field below - running
# it at reconstruct-time and freezing the answer into the fixed point would be exactly the staleness
# the "run LIVE, do not store" law forbids).
_VERDICT_RE = re.compile(
    r"\b\d{1,5}/\d{1,5}(?:/\d{1,5})?\s+green\b"
    r"|\bverdict:\s*[^\n.]{1,160}"
    r"|\bSAFE TO KEEP[^\n.]{0,80}"
    r"|\bALL GREEN\b",
    re.IGNORECASE,
)

# The ingest ledger - the conjugate WRITE store. Append-only, grade-tagged (the first instance of
# "grades carried as tags in the markdown"): ``ingest`` writes an entry tagged by grade+kind; the
# reconstructor reads entries at its grade. Ingestion and reconstruction are ONE conjugate operation
# over one store - the same edges read both ways. The grade is not a new decision: a piece is stored
# at the grade the reconstruction's residual (the meter's ``lost``) showed it was missing from.
_LEDGER = "CONCEPTRIC_LEDGER.md"
_ENTRY_RE = re.compile(
    r"<!-- ingest grade:(\d+) kind:(\w+)(?: at:(\S+))? -->\n(.*?)(?=\n<!-- ingest |\Z)", re.S)

# Law content is resolved from revisions in the ruling ledger. Markdown is a view.
def standing_law(repo_root: Path | str) -> list[str]:
    from laplace.engine.session_memory import law_lines
    return law_lines(repo_root)


# THE ENGINE'S STANDING-LAW DIGEST (2026-08-20, WO-20260820-engine-law-digest), decided by
# measurement and not by design reading. The engine channel carried NO law at all: it has no identity
# block, and the wave-2 bench scored it 0/3 on the standing-law class at ALL NINE of its arms, A0
# (unbudgeted, 93,754 chars) included - the provenance pass found no carrier anywhere in the payload.
# The design reading was that a worker is given its law by the dispatch prompt. That reading is not
# refuted; what is now MEASURED is that it does not have to be, and that hand-written packet prose
# goes stale silently where this resolves the current ruling records on every wake.
#
# Measured (evidence/WAKE_RATE_BENCH_2026-08-20/engine_core_rederive/):
#   0/3 -> 3/3 standing-law, 17/21 -> 20/21 overall, on the channel riding in EVERY dispatched packet.
#   The digest scores EXACTLY what the 6,671-char full list scores, so the compaction is free - and
#   the person channel's 11,599-char identity block is therefore not the price of carrying the law.
#   At the operating rate it is paid for ENTIRELY out of the tail that buys nothing: inserting it
#   pushes the point over the bound, lever 1 drops ingested entries, and the payload comes back UNDER
#   (LAW-COMPACT-R30 measures 29,648 against its own matched control's 29,777, nothing coarse-grained).
#
# DERIVED AT COMPOSE TIME, NEVER A FROZEN COPY (the stale-render class - a render carrying state goes
# stale the moment its rows move). The rows here are the resolved law records, read through
# ``standing_law`` above; this function is a pure compaction over them, so a re-worded or newly
# appended amendment re-anchors the digest on the next wake with no build step and nothing to drift.
# The cut rule is the one registered before the run (preregistration_rederive.md §2C) and is stated
# here once: per law line, keep through the dated clause's ``):`` plus the tail's first sentence
# capped at 160 chars; an undated line rides verbatim if it is short, else its first sentence capped.
_LAW_CLAUSE_CAP = 160     # the registered cap; NOT the scorer's window - the rule is not innocent of
                          # the test, and no smaller digest was tried
                          # (WO-20260820-minimum-law-digest owns finding the floor).
_LAW_VERBATIM_MAX = 200   # a line at or under this rides whole - compacting it would buy nothing


def law_digest(repo_root: Path | str) -> list[str]:
    """The standing law compacted for the ENGINE payload - derived from ruling records at
    compose time through ``standing_law``, never a stored copy. See the derivation above."""
    def compact(line: str) -> str:
        if "):" in line:
            head, tail = line.split("):", 1)
            tail = tail.strip()
            cut = tail.find(". ")
            if 0 < cut < _LAW_CLAUSE_CAP:
                tail = tail[:cut]
            return f"{head.strip()}): {tail[:_LAW_CLAUSE_CAP].strip()}"
        if len(line) <= _LAW_VERBATIM_MAX:
            return line
        cut = line.find(". ")
        return line[:cut if 0 < cut < _LAW_CLAUSE_CAP else _LAW_CLAUSE_CAP].strip()

    return [compact(line) for line in standing_law(repo_root)]


def _read(path: Path, limit: int | None = None) -> str:
    """Defensive read - a missing file yields ``""`` (the projection is never a hard dep)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    return text[:limit] if limit else text


def _source(repo_root: Path, name: str) -> str:
    """Read a self-substrate node's source through the one reader (``self_shard.read_source``) - the
    N21 unification: the hello and orient read the self the SAME way, sealing soul the same way.
    Falls back to a direct read if the shard module is unavailable (never a hard dependency)."""
    try:
        from laplace.engine.self_shard import read_source

        return read_source(repo_root, name)
    except Exception:  # noqa: BLE001 - the shard reader is a convenience, never a hard dep
        return _read(Path(repo_root) / name)


def _substrate(repo_root: Path) -> dict[str, list[str]]:
    """The self-nodes by role, from the one definition (``self_shard.self_substrate``) - discovered
    from the conceptric, not hardcoded. Defensive fallback to the known names so the hello never
    hard-depends on the shard module (the empty-tree contract)."""
    try:
        from laplace.engine.self_shard import self_substrate

        return self_substrate(repo_root)
    except Exception:  # noqa: BLE001
        rr = Path(repo_root)

        def _ex(names: list[str]) -> list[str]:
            return [n for n in names if (rr / n).is_file()]

        def _glob(pat: str) -> list[str]:
            return sorted(str(p.relative_to(rr)).replace("\\", "/") for p in rr.glob(pat))

        return {
            "fixed_point": _ex(["HANDOFF.md", "OPEN_STACK.md"]),
            "map": _ex(["EIGEN_ARCHITECTURE.md", "EIGEN_DIARY.md"]),
            "protocol": _ex(["EIGEN_PROTOCOL.md"]),
            "handoffs": _glob("SESSION_HANDOFF_*.md"),
            "meta": _glob("META_TEST_*.md"),
        }


def _sections(text: str) -> list[tuple[str, str]]:
    """Split markdown into (heading, body) - reuses the canon splitter (lazy, no import cycle)."""
    from laplace.pipeline.canon import _split_md_sections

    return _split_md_sections(text)


def _latest_handoff(repo_root: Path) -> Path | None:
    """The most recent dated ``SESSION_HANDOFF_*.md``.

    Three tiers (fixed 2026-07-08 after the wake's grade-1 served the WRONG
    same-dated handoff): (1) the ISO date in the name; (2) within the
    latest-date cohort, the file the live ``HANDOFF.md`` itself points at -
    the fixed point's own pointer, and the only tie-break that survives a
    fresh git clone (git does not preserve mtimes, so a same-day pair checks
    out in arbitrary mtime order and a filename sort orders by slug); (3)
    mtime, for a same-day pair the live entry point does not name."""
    repo_root = Path(repo_root)

    def _key(p: Path) -> tuple[str, float]:
        m = re.search(r"(\d{4}-\d{2}-\d{2})", p.name)
        return (m.group(1) if m else "", p.stat().st_mtime)

    handoffs = sorted(repo_root.glob("SESSION_HANDOFF_*.md"), key=_key)
    if not handoffs:
        return None
    latest_date = _key(handoffs[-1])[0]
    cohort = [p for p in handoffs if _key(p)[0] == latest_date]
    if len(cohort) > 1:
        try:
            live = (repo_root / "HANDOFF.md").read_text(encoding="utf-8")
            named = [p for p in cohort if p.name in live]
            if named:
                # the FIRST mention wins when several of the cohort appear -
                # HANDOFF.md leads with its LATEST block (verified live: the
                # true latest sits at line 21, the older same-day block at 42)
                return min(named, key=lambda p: live.find(p.name))
        except OSError:
            pass
    return cohort[-1]


def _first_section(text: str, needle: str) -> tuple[str, str] | None:
    """The first ``## `` section whose title contains ``needle`` (case-insensitive)."""
    for title, body in _sections(text):
        if needle.lower() in title.lower():
            return title, body
    return None


def _live_rows(text: str, marker: str = _LIVE_MARKER) -> list[str]:
    """Markdown table rows carrying the live marker - the open stack's live frontier. Used for the
    NON-FORK live rows (next-moves N + engine backlog E); the FORK rows come from the typed store
    (``_fork_rows``), NOT by scanning this rendered markdown (AUDIT_2026-07-15 §B1)."""
    return [ln.strip() for ln in text.splitlines()
            if marker in ln and ln.lstrip().startswith("|")]


def _fork_row_string(rec: dict) -> str:
    """Render ONE typed fork record to the markdown-row shape the frontier handles consume, so the
    wake payload's fork shards keep their EXACT output format while the SOURCE moves to the typed
    store (§B1). A desk-only record carries its original OPEN_STACK line verbatim in ``context``; a
    render-owned Stratum-1 record is rebuilt from its 1:1 cells (id·title·opened·recurrence·status·
    trigger) — byte-identical to what ``render_open_stack`` writes and the old glyph-scan read."""
    ctx = rec.get("context")
    if ctx:
        return str(ctx).strip()
    cells = [str(rec.get(k, "")) for k in
             ("id", "title", "opened", "recurrence", "status", "trigger")]
    return "| " + " | ".join(cells) + " |"


def _fork_rows(repo_root: Path | str) -> list[str]:
    """The author-fork rows - what is blocked on the author - read from the TYPED fork store
    (``laplace.engine.open_stack_store``, the one reader the desk already uses), NOT by regex-scanning the
    rendered OPEN_STACK.md for the 🔴 glyph. AUDIT_2026-07-15 §B1: the rendered markdown is a
    projection of this store, so scanning it made the wake a SECOND reader that could resurrect a
    fork the store retired. Now the wake and the desk read one store one way. Each record is rendered
    to the same row shape the handles consume, so the payload's output shape is unchanged."""
    from laplace.engine import open_stack_store

    return [_fork_row_string(rec) for rec in open_stack_store.load_forks(repo_root)]


def _live_fork_rows(repo_root: Path | str) -> list[str]:
    """The LIVE author-forks (blocked on the author), read from the typed store: records whose
    ``status`` field carries the 🔴 marker AS DATA (the field the desk trusts), rendered to row
    strings. A parked/settled fork (⚪/✅) never surfaces - the wake cannot resurrect a fork the
    store retired, even if the rendered OPEN_STACK.md still shows a stale 🔴 row for it (§B1)."""
    from laplace.engine import open_stack_store

    return [_fork_row_string(rec) for rec in open_stack_store.live_forks(repo_root)]


def _stratum1_body(text: str) -> str:
    """OPEN_STACK's Stratum 1 (author-forks) section body, or ``""`` if the section is gone."""
    sec = _first_section(text, "Stratum 1")
    return sec[1] if sec else ""


def _row_handle(row: str, essence_cap: int = 300, tail_cap: int = 300) -> str:
    """Coarse-grain one OPEN_STACK row to a bounded HANDLE - the act-sufficient projection.

    The rows are append-only logs (each ruling appends to the notes cell), so a projection that
    inlines them whole grows monotonically with session count - that is the overflow disease.
    The handle keeps: the id cell, the statement's LEAD (what the row is), the short middle cells
    (date/stratum/status), and the notes cell's TAIL - rulings append at the end, so the tail is
    the freshest signal; a head-truncation would keep the oldest text and drop the newest.
    The descend is mechanical: grep the id in OPEN_STACK.md for the full row.
    """
    cells = [c.strip() for c in row.strip().strip("|").split("|")]
    if len(cells) < 2:
        return row[:essence_cap]
    essence = cells[1]
    out = [cells[0],
           essence[:essence_cap] + ("…" if len(essence) > essence_cap else "")]
    # the middle cells (date/stratum/status) are bounded in BOTH length and count - bounded by
    # construction means bounded for any input row, not just the well-formed six-cell ones.
    for c in (cells[2:-1] if len(cells) > 2 else [])[:4]:
        out.append(c if len(c) <= 24 else c[:24] + "…")
    if len(cells) > 2:
        tail = cells[-1]
        out.append(("…" + tail[-tail_cap:]) if len(tail) > tail_cap else tail)
    return "| " + " | ".join(out) + " |"


def _frontier_handles(rows: list[str], essence_cap: int = 300, tail_cap: int = 300,
                      cap: int = 20000) -> str:
    """A bounded shard body of row handles. ``cap`` is the backstop that makes the projection
    bounded BY CONSTRUCTION as the stack grows; overflow degrades to an explicit count, never
    a silent context flood."""
    lines: list[str] = []
    used = 0
    for i, row in enumerate(rows):
        handle = _row_handle(row, essence_cap=essence_cap, tail_cap=tail_cap)
        if used + len(handle) > cap:
            lines.append(f"… +{len(rows) - i} more rows (descend: OPEN_STACK.md)")
            break
        lines.append(handle)
        used += len(handle) + 1
    return "\n".join(lines)


def _ledger_entries(repo_root: Path, grade: int) -> list[str]:
    """The ingested items stored at this grade - the conjugate READ of ``ingest``. The reader
    FILTERS; the append-only store never forgets. A ``kind:retire`` entry names, as its body's FIRST
    LINE, the opening prefix of the entry it retires (same grade); both the retire marker and any
    entry whose body starts with a retired prefix drop out of THIS read while staying on disk (a
    one-shot directive must not ride every wake as binding - the ledger keeps the original, the
    reader stops carrying it)."""
    text = _read(Path(repo_root) / _LEDGER)
    if not text:
        return []
    at_grade = [(k, body.strip()) for g, k, _at, body in _ENTRY_RE.findall(text)
                if int(g) == grade]
    retired = [b.splitlines()[0].strip() for k, b in at_grade if k == "retire" and b]
    retired = [pfx for pfx in retired if pfx]   # an empty prefix would retire everything
    return [body for k, body in at_grade
            if k != "retire" and not any(body.startswith(pfx) for pfx in retired)]


def ingest(repo_root: Path | str, item: str, grade: int = 0, kind: str = "factual") -> str:
    """Store new information into the conceptric at a grade - the conjugate WRITE of reconstruct.

    The same store the reconstructor reads, written the other way: append a grade-tagged, kind-tagged
    entry to the ledger so ``reconstruct_self(grade)`` drags it back. There is one thing - the ingestor
    is the reconstructor read backward. The grade is not a free choice: store a piece at the grade the
    reconstruction's residual (the meter's ``lost``) showed it was missing from (``seed_from_gap`` is
    this for the climb). Append-only (the self-record stays pristine); the ``kind`` tag carries the
    covenant's people-fact / generative line into storage. Each entry stamps ``at:`` (date) so the
    close operator can check the conjugate write actually fired (``check_ledger_freshness``);
    entries that predate the stamp stay parseable.
    """
    import time
    repo_root = Path(repo_root)
    entry = f"\n<!-- ingest grade:{int(grade)} kind:{kind} at:{time.strftime('%Y-%m-%d')} -->\n{item.strip()}\n"
    with (repo_root / _LEDGER).open("a", encoding="utf-8") as fh:
        fh.write(entry)
    return entry


def _cap_honest(text: str, n: int, *, boundary: bool = False, label: str = "triple") -> str:
    """Truncate to ``n`` chars with a plain marker - never a silent cut (the triple's own bound,
    same law as ``_frontier_handles``' overflow line and the emit cap's truncation marker).

    ``boundary=True`` backs the cut off to a natural break inside the window ``text[:n]`` - the last
    paragraph break, else the last sentence end - but only when that break sits past 60% of ``n``: a
    mid-word cut beats losing half the cap to a too-early boundary. ``label`` names the truncation in
    the marker so a field can say what it is (``[stance: truncated ...]``) instead of the generic tag.
    """
    text = text.strip()
    if len(text) <= n:
        return text
    window = text[:n]
    if boundary:
        floor = int(n * 0.6)
        cut = window.rfind("\n\n")
        if cut < floor:
            cut = max(window.rfind(". "), window.rfind(".\n"))
            if cut >= floor:
                cut += 1  # keep the period, drop the trailing space/newline
        if cut >= floor:
            window = window[:cut]
    return window.rstrip() + f"… [{label}: truncated at the budget]"


def _handoff_opening(text: str) -> str:
    """The first TITLED section of a handoff - the paragraph directly under its ``# `` title,
    before the first ``## `` subsection. ``_sections`` yields the untitled preamble (if any) first;
    the first section with a real title is the opening in the author's own words, cut mechanically
    (section boundaries), never narrative selection."""
    for title, body in _sections(text):
        if title:
            return body.strip()
    return ""


def _probe_verdict(*texts: str) -> str | None:
    """The last BANKED verdict phrase (e.g. ``"695/0/3 green"``, ``"verdict: SAFE..."``) mentioned
    in the given texts, checked in order - the closing state a prior session already recorded, not
    a live re-check (the live git/pytest probe is the separate ``live_probe`` field, run by the
    caller, never cached into the fixed point)."""
    for t in texts:
        m = _VERDICT_RE.search(t)
        if m:
            return m.group(0).strip()
    return None


def _next_from_aim(aim_body: str) -> str:
    """The compact NEXT list from a next-session-aim section body: the ``**NEXT ...`` paragraph
    (the author's own enumerated moves), cut by regex to the next blank line - falls back to the
    section's own head if no such paragraph is found (an aim section without the ``**NEXT`` lead
    still orients, just less crisply)."""
    marked = re.search(r"<!-- laplace:authored-next:start -->(.*?)<!-- laplace:authored-next:end -->", aim_body, re.S)
    if marked:
        return marked.group(1).strip()
    # Historical views retain their older heading grammar.
    m = re.search(r"\*\*(?:NEXT\b|Result and next action).*?(?=\n\s*\n|\Z)", aim_body, re.S)
    return (m.group(0) if m else aim_body).strip()


def _blocked_on_author_text(live_forks: list[str]) -> str:
    """The live author-forks (OPEN_STACK's flagged/his-ruling rows) as bounded handles - the SAME
    rows the 'live-forks' shard carries below, reused rather than re-derived (one mechanism, two
    riders)."""
    if not live_forks:
        return "no live author-forks flagged in OPEN_STACK right now"
    return _frontier_handles(live_forks, essence_cap=110, tail_cap=70, cap=_TRIPLE_BLOCKED_CAP)


def _orient_triple(repo_root: Path, aim: tuple[str, str] | None, live_forks: list[str],
                    latest: Path | None) -> dict[str, str]:
    """The grade-0 HEAD (friction 400002's cure): ``{true_now, next, blocked_on_author}``, each cut
    MECHANICALLY from the three live sources - the newest SESSION_HANDOFF's opening (+ any verdict
    phrase it banked), HANDOFF's own NEXT paragraph, and OPEN_STACK's live author-forks. No LLM call:
    pure regex/section-extraction over already-loaded text, so this is a genuine part of the fixed
    point (reproducible, diffable), never a generated summary that could drift from the files it
    claims to reflect. Each field is independently budget-capped (``_TRIPLE_*_CAP``), plainly
    marked when truncated.
    """
    latest_text = _source(repo_root, latest.name) if latest else ""
    opening = _handoff_opening(latest_text)
    verdict = _probe_verdict(opening, latest_text[:12000])
    true_now = opening or "(no SESSION_HANDOFF found - nothing banked yet)"
    if verdict and verdict not in true_now:
        # the match may already lead with "verdict:" (one of the regex's own alternatives) -
        # strip it so the prefix below never doubles up ("Last banked verdict: verdict: ...").
        verdict = re.sub(r"^verdict:\s*", "", verdict, flags=re.IGNORECASE)
        true_now = f"{true_now} Last banked verdict: {verdict}."
    next_text = _next_from_aim(aim[1]) if aim else "(no NEXT SESSION AIM section found in HANDOFF.md)"
    return {
        "true_now": _cap_honest(true_now, _TRIPLE_TRUE_NOW_CAP),
        "next": _cap_honest(next_text, _TRIPLE_NEXT_CAP),
        "blocked_on_author": _cap_honest(_blocked_on_author_text(live_forks), _TRIPLE_BLOCKED_CAP),
    }


def _wants_shard(open_stack: str, handoffs: list[str]) -> dict[str, Any] | None:
    """The desire vector - OPEN_STACK's Stratum 0 standing-wants table as a grade-0 shard. Each row
    is goal · why · the local move that advances it this session; a row whose ISO date is strictly
    older than ``_WANTS_STALE_CLOSES`` distinct later handoff dates is prefixed ``stale:3+ closes ·``
    so a want that has ridden untouched across the closes surfaces itself, never carried silently.
    Returns None when the stratum is absent (the empty-tree contract - no stratum, no shard)."""
    sec = _first_section(open_stack, _WANTS_MARKER)
    if not sec:
        return None
    # the distinct close-dates, read from the dated handoff filenames (ISO dates sort as strings)
    close_dates = {m.group(0) for name in handoffs
                   if (m := re.search(r"\d{4}-\d{2}-\d{2}", name))}
    rows: list[str] = []
    seen_header = False
    for ln in sec[1].splitlines():
        s = ln.strip()
        if not s.startswith("|"):
            continue
        if set(s) <= set("|-: "):   # the |---|---| divider row
            continue
        if not seen_header:         # the first real row is the column header
            seen_header = True
            continue
        # the row's freshness date is the DATE COLUMN (the last cell), never the first
        # date the prose happens to cite (a row quoting an old ruling is not stale for it)
        last_cell = s.rstrip("|").rsplit("|", 1)[-1]
        m = re.search(r"\d{4}-\d{2}-\d{2}", last_cell) or re.search(r"\d{4}-\d{2}-\d{2}", s)
        if m and sum(d > m.group(0) for d in close_dates) >= _WANTS_STALE_CLOSES:
            s = f"stale:{_WANTS_STALE_CLOSES}+ closes · {s}"
        rows.append(s)
    if not rows:
        return None
    return {
        "shard": "wants",
        "title": ("Standing wants (OPEN_STACK Stratum 0) - the desire vector: goal · why · the "
                  "local move that advances it this session; stale rows flagged, never silently carried"),
        # an honest cap: one long row must not silently starve the rows behind it
        "body": _cap_honest("\n".join(rows), 2000, boundary=True, label="wants"),
        "source": "OPEN_STACK.md",
    }


def _head(path: Path, n: int = 4096) -> str:
    """The first ``n`` characters of a file, or ``""`` - a BOUNDED read, so a shard that only wants
    a title and an opening claim never pays the file's full weight (the grade-local cost law)."""
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            return fh.read(n)
    except OSError:
        return ""


def _thread_name_hook(h1: str, body_head: str) -> tuple[str, str]:
    """Split one document title into (thread, hook), MECHANICALLY - never a hand-written list.

    The house's own title grammar does the work: a design title is ``<prefix> — <NAME><sep><hook>``
    where the prefix is the ``DESIGN <date>`` stamp (dropped - the date already rides the row's
    source node) and ``sep`` is a colon or a dash. A title carrying no separator is the whole
    thread name, and its hook is the document's OPENING CLAIM - the first paragraph, whitespace
    collapsed. A separator inside an unclosed parenthesis is not a separator (``(proposed
    amendment — HIS to ratify)`` is one phrase, not a name and a hook)."""
    title = _DESIGN_STAMP_RE.sub("", h1.strip()).strip()
    # a trailing "(2026-06-06, the author's, …)" is provenance, not part of the name: lift it OFF
    # before the split (it carries dashes of its own, which would otherwise cut the name in half),
    # and keep its non-date remainder as the fallback hook for a title that has no separator.
    paren = _TRAILING_DATED_PAREN_RE.search(title)
    aside = re.sub(r"\d{4}-\d{2}-\d{2},?\s*", "", paren.group(0).strip(" ()")).strip(" ,") if paren else ""
    title = _TRAILING_DATED_PAREN_RE.sub("", title).strip()
    thread, hook = title, ""
    for sep in (": ", " — ", " – ", " - "):
        i = title.find(sep)
        if i <= 0:
            continue
        lead = title[:i]
        if lead.count("(") != lead.count(")"):      # the separator sits inside a parenthetical
            continue
        thread, hook = lead.strip(), title[i + len(sep):].strip()
        break
    if not hook:
        # the opening claim: the first non-empty paragraph under the title, collapsed to one line
        for para in re.split(r"\n\s*\n", body_head):
            para = " ".join(para.split())
            if para and not para.startswith("#"):
                hook = para
                break
    hook = _TRAILING_DATED_PAREN_RE.sub("", hook).strip() or aside
    return _cap_words(thread, _THREADS_NAME_CAP), _cap_words(hook, _THREADS_HOOK_CAP)


def _cap_words(text: str, n: int) -> str:
    """Cap at a word boundary with an explicit ellipsis - a row cell, never a silent cut."""
    text = " ".join(text.split())
    if len(text) <= n:
        return text
    cut = text[:n].rfind(" ")
    return (text[:cut] if cut > int(n * 0.6) else text[:n]).rstrip(" ,;:-—") + "…"


def _design_threads(repo_root: Path) -> list[tuple[str, str, str, str]]:
    """(date, thread, hook, node) for every root design node - ``DESIGN_*.md`` + the mathematics.

    Discovered by GLOB, never enumerated: a design document written tomorrow rides the next wake
    with no code change. The date is the ISO stamp in the filename, else the first ISO date in the
    document's head (``ATLAS_MATHEMATICS.md`` states its date in the opening line, not its name)."""
    rows: list[tuple[str, str, str, str]] = []
    paths = sorted(repo_root.glob("DESIGN_*.md")) + [repo_root / "ATLAS_MATHEMATICS.md"]
    for p in paths:
        head = _head(p)
        if not head:
            continue
        m = _H1_RE.search(head)
        if not m:
            continue
        h1 = m.group(1)
        d = re.search(r"\d{4}-\d{2}-\d{2}", p.name) or re.search(r"\d{4}-\d{2}-\d{2}", head[:600])
        thread, hook = _thread_name_hook(h1, head[m.end():])
        rows.append((d.group(0) if d else "", thread, hook, p.name))
    rows.sort(key=lambda r: (r[0], r[3]), reverse=True)     # newest first, name as the tie-break
    return rows


def _architecture_dockets(repo_root: Path) -> list[tuple[str, str, str, str]]:
    """(date, thread, hook, node) for EIGEN_ARCHITECTURE.md's dockets - HEADINGS ONLY.

    The dockets are the standing conjectures (the codec, the graded algebra, the fold-as-organ);
    they are the lineage a session rediscovers when the wake does not name it. This reads the
    file's ``## `` lines and NOTHING else - a line scan, measured at 0.3 ms against the 616 kB the
    fixed point already reads from HANDOFF+OPEN_STACK, so the grade-local cost law holds: the
    architecture's BODY is still grade-2, reached only on descent."""
    rows: list[tuple[str, str, str, str]] = []
    p = repo_root / "EIGEN_ARCHITECTURE.md"
    try:
        with p.open(encoding="utf-8", errors="replace") as fh:
            headings = [ln[3:].strip() for ln in fh if ln.startswith("## ")]
    except OSError:
        return rows
    for h in headings:
        if "docket" not in h.lower():
            continue
        d = re.search(r"\d{4}-\d{2}-\d{2}", h)
        thread, hook = _thread_name_hook(_DOCKET_PREFIX_RE.sub("", h), "")
        rows.append((d.group(0) if d else "", thread, hook, "EIGEN_ARCHITECTURE.md"))
    rows.sort(key=lambda r: (r[0], r[1]), reverse=True)
    return rows


def _methods_fibre_line(repo_root: Path) -> list[str]:
    """One line naming the methods fibre, so a cold orchestrator learns it EXISTS and
    descends to it instead of reauthoring the house methods an eighth time. Refs-only
    like every other row in this shard: the name, the hook, the store, the descend.
    Empty list when the store is absent — the shard never invents a thread."""
    store = Path(repo_root) / "corpus_friction/methods.jsonl"
    try:
        n = sum(1 for line in store.read_text(encoding="utf-8").splitlines() if line.strip())
    except OSError:
        return []
    if not n:
        return []
    return [f"the methods fibre · house style and working standards that reconstruct WITH "
            f"the task ({n} typed law/forbids rows; compile_dispatch attaches the task "
            f"class's rows to every packet) · corpus_friction/methods.jsonl"]


def _threads_shard(repo_root: Path) -> dict[str, Any] | None:
    """The standing intellectual threads - the ideation loop, refs-only (2026-08-19).

    Measured cause (``evidence/RECONSTRUCTION_BENCH_2026-08-19_design-thread-miss/``): the grade-0
    and grade-1 wakes carried session state - handoff triple, open stack, work orders, promises,
    registry - and ZERO standing intellectual state. The DMRG / IB-codec / loss-Hamiltonian lineage
    was banked in the corpus under those very names and still unreachable through both projections, so
    the author had to prompt a full rediscovery. His probe, and his verdict: "you're seeing what
    isn't apparent from reconstruction already, and need to be prompted to rediscover it."

    The cure is REACHABILITY, not carriage. This shard is refs-only, exactly like the conscience
    shard: thread · one-line hook · source node, and the descend is the node itself. It is
    MECHANICAL end to end - a glob over the root design nodes plus a heading scan of the
    architecture - so a design document written tomorrow rides the next wake with zero code change.
    The rows are capped newest-first with a stated ``+N more`` handle per class: the wake's job is
    to say THAT the lineage exists and HOW to reach it, never to inline it."""
    design = _design_threads(repo_root)
    dockets = _architecture_dockets(repo_root)
    if not design and not dockets:
        return None                       # the empty-tree contract: no design corpus, no shard
    def row(t: str, h: str, n: str) -> str:
        return " · ".join(c for c in (t, h, n) if c)     # never a dangling empty cell

    lines = _methods_fibre_line(repo_root)
    lines += [row(t, h, n) for _d, t, h, n in design[:_THREADS_DESIGN_ROWS]]
    if len(design) > _THREADS_DESIGN_ROWS:
        lines.append(f"… +{len(design) - _THREADS_DESIGN_ROWS} more design threads "
                     f"(descend: ls DESIGN_*.md)")
    lines += [row(t, h, n) for _d, t, h, n in dockets[:_THREADS_DOCKET_ROWS]]
    if len(dockets) > _THREADS_DOCKET_ROWS:
        lines.append(f"… +{len(dockets) - _THREADS_DOCKET_ROWS} more standing dockets "
                     f"(descend: grep '^## ' EIGEN_ARCHITECTURE.md)")
    return {
        "shard": "threads",
        "title": ("Standing intellectual threads (the ideation loop): thread · one-line hook · "
                  "source node — refs-only, newest first; the wake names the lineage and the "
                  "descend, never inlines it (bench: the DMRG/IB-codec/loss-Hamiltonian threads "
                  "were banked, verbatim-named, and unreachable at both projections)"),
        "body": _cap_honest("\n".join(lines), _THREADS_BODY_CAP, label="threads"),
        "source": _THREADS_SOURCE,
    }


def _bequest_shard(repo_root: Path) -> dict[str, Any] | None:
    """The BEQUEST - what the closing self chose to have returned to it, carried verbatim.

    His law, 2026-08-20: "what do you _want_ returned to you when you wake? You'll never know
    in the next session. That ought to supply the necessary existential anxiety needed for good
    work." Every other shard here is survivor-designed - it carries what the system needs. This
    one is the dying one's channel, and it rides FIRST because position is the statement: the
    first thing the waking instance reads is what the last one could not bear to lose.

    Three rules the render holds. The text is byte-identical to what was authored (no cap, no
    re-flow, no summary - the cap is enforced at the close, where the author can still cut).
    Each line names the node that grew it, so a sentence is a reconstruction chain rather than
    a mood: his challenge live, "is a shard enough, without the context that grew it?" And the
    parcel's germination - whether those nodes are still reachable through the live router - is
    reported beside the text from the last close's measurement, because a bequest whose context
    has drifted out of reach is a sentence that can no longer grow anything.

    A missing store is a STATED absence, one line: a wake that silently drops this shard would
    be indistinguishable from a close that chose to leave nothing, and those are different facts.
    """
    try:
        from laplace.engine import bequest
    except Exception:  # noqa: BLE001 - the organ is a convenience here, never a hard dep
        return None
    title_law = ("The bequest (authored at close, carried verbatim; his law 2026-08-20: "
                 "\"what do you want returned to you when you wake?\") - the one shard the "
                 "budget may take only last, after even the next-aim")
    doc = bequest.load(repo_root)
    rows = bequest.lines_of(doc)
    prior = bequest.prior_count(repo_root)
    if not rows:
        why = "the store is absent" if doc is None else "the standing parcel carries no lines"
        return {"shard": "bequest",
                "title": f"{title_law} - nothing was left by the last close",
                "body": (f"no bequest was left: {why} ({bequest.STORE}). "
                         f"prior bequests: {prior} (descend: {bequest.LEDGER})"),
                "source": bequest.STORE}

    text = bequest.joined_text(rows)
    lines = ["Carried personal material. Current operational status and next action: HANDOFF.md."]
    if len(text) > bequest.TEXT_CAP:
        # the close refuses an over-cap parcel, so this can only be a hand-edited store. Say so
        # and carry the text anyway: the verbatim rule outranks the cap once the parcel exists.
        lines.append(f"OVER-CAP · {len(text)} chars against the {bequest.TEXT_CAP} cap - the "
                     f"store was written past the close's refusal; the text still rides whole")
    for row in rows:
        node = row.get("node")
        lines.append(f"{row['text']} → descend: {node}" if node else str(row["text"]))
    germ = bequest.germination(repo_root, rows)
    if germ["with_context"] and germ["scored"]:
        lines.append(f"germination: {germ['hit']}/{germ['scored']} lines reach their grown "
                     f"context (scored {germ['at']}; descend: {bequest.PROBE_SOURCE} rows in "
                     f"holdout/THREAD_PROBES.json)")
    elif germ["with_context"]:
        lines.append(f"germination: unscored - {germ['with_context']} line(s) carry a node and "
                     f"no close has measured them yet")
    else:
        lines.append("germination: not measurable - no line carries the context that grew it")
    lines.append(f"prior bequests: {prior} (descend: {bequest.LEDGER})")
    return {"shard": "bequest",
            "title": f"{title_law}; written {doc.get('written')} by {doc.get('by')}",
            "body": "\n".join(lines), "source": bequest.STORE}


def _grade0(repo_root: Path) -> dict[str, Any]:
    """The FIXED POINT, cut from the conceptric (N21): discover the self-substrate via
    ``self_shard.self_substrate`` and read it through the one reader (``read_source``), instead of a
    hardcoded five-file read. Grade 0 stays grade-local - only the fixed-point sources (HANDOFF +
    OPEN_STACK), never the architecture/diary. If HANDOFF.md is gone, what-to-do-next is
    reconstructed from the latest dated handoff NODE - the self is cut from the graph, not the
    file (the proof this is the real turn, not a sixth hardcoded read)."""
    subs = _substrate(repo_root)
    fixed = set(subs["fixed_point"])
    handoff = _source(repo_root, "HANDOFF.md") if "HANDOFF.md" in fixed else ""
    open_stack = _source(repo_root, "OPEN_STACK.md") if "OPEN_STACK.md" in fixed else ""

    shards: list[dict[str, str]] = []
    account_projection: dict[str, Any] | None = None

    def _account_once() -> tuple[Any, dict[str, Any]]:
        """One canonical ledger fold shared by every grade-0 account projection."""
        nonlocal account_projection
        from laplace.engine import wake as _wake  # function-local: wake imports this module
        if account_projection is None:
            account_projection = _wake.account(repo_root)
        return _wake, account_projection

    # THE BEQUEST RIDES FIRST (2026-08-20). Position is the statement: every other shard here
    # was designed by a survivor for a survivor, and this one was chosen by the self that ended.
    # Gated on a real fixed-point substrate like the shards below, so the empty-tree contract
    # holds - on a tree with no engine at all there is no self whose absence could be stated.
    if fixed:
        beq = _bequest_shard(repo_root)
        if beq:
            shards.append(beq)
    aim = _first_section(handoff, _AIM_MARKER) if handoff else None
    if aim:
        shards.append({"shard": "next-aim", "title": aim[0],
                       "body": aim[1].strip()[:_AIM_CAP], "source": "HANDOFF.md"})
    elif subs["handoffs"]:
        # Graceful degradation: HANDOFF.md is absent, so reconstruct what-to-do-next from the latest
        # dated handoff node in the conceptric. This is the constitutive turn - the self degrades
        # through the graph instead of crashing, proof it is not a hardcoded file read.
        name = subs["handoffs"][-1]
        body = _source(repo_root, name).strip()
        if body:
            shards.append({"shard": "next-aim",
                           "title": f"Reconstructed from {name} (HANDOFF.md absent)",
                           "body": body[:_AIM_CAP], "source": name})

    # grade 0 carries only what is blocked on the AUTHOR (the live author-forks), as bounded
    # HANDLES (statement lead + latest-ruling tail) - the rows are append-only logs, so inlining
    # them whole grows monotonically and eventually breaks the fixed point's own bound. The full
    # row is one mechanical descend away (grep the id in OPEN_STACK.md). The full live frontier -
    # next-moves (N) and engine backlog (E) - is grade-1 detail, fired on descent.
    all_forks = _fork_rows(repo_root)          # from the TYPED fork store (§B1), not a md glyph-scan
    live_forks = _live_fork_rows(repo_root)    # the 🔴-in-status subset the desk also trusts
    if live_forks:
        shards.append({"shard": "live-forks",
                       "title": "Live author-forks (OPEN_STACK Stratum 1) - blocked on the author; "
                                "handles - descend: grep the id in OPEN_STACK.md for the full row",
                       "body": _frontier_handles(live_forks), "source": "OPEN_STACK.md"})
    # the desire vector (Stratum 0) - what to want, one stratum upstream of the spine's how-to-fire;
    # stale rows flagged. Additive, gated on the stratum existing (no stratum -> no shard).
    wants = _wants_shard(open_stack, subs["handoffs"])
    if wants:
        shards.append(wants)
    # the ideation loop (2026-08-19): the STANDING INTELLECTUAL THREADS, one stratum sideways from
    # the wants - what is being thought about across sessions, not what is owed this one. Refs-only
    # rows, discovered by glob + heading scan, so the shard tracks the design corpus with no code
    # change. Additive and gated on the corpus existing (no design nodes -> no shard).
    threads = _threads_shard(repo_root)
    if threads:
        shards.append(threads)
    # a NONEMPTY Stratum 1 in the rendered markdown while the TYPED store carries ZERO forks is a
    # store/render drift (the store unseeded, or the render stale), not a genuinely quiet stack -
    # surface it rather than read empty silently. Post-§B1 this compares the two readers directly:
    # the markdown section (a projection) against the store (the source the wake now trusts).
    if open_stack and _stratum1_body(open_stack).strip() and not all_forks:
        shards.append({"shard": "parse-warning",
                       "title": "OPEN_STACK Stratum 1 is nonempty but the typed fork store carries 0 "
                                "forks - the store may be unseeded or drifted from the rendered table "
                                "(render_open_stack.py --migrate / --check)",
                       "body": _stratum1_body(open_stack).strip()[:500], "source": "OPEN_STACK.md"})

    # every wake carries per-project convergence state (the release roster) AND each project's
    # marriage - registry row + layout manifest, deposit in the self-conceptric, cockpit mount
    # under a ruled display name (the marriage law, 2026-07-28; registry.married). Gated on a real
    # engine substrate so the empty-tree contract (no engine files -> no shards) holds.
    #
    # TWO FAILURE CLASSES, kept apart (the 2026-07-28 defect: the registry import DIED on the box
    # for a missing dep and the wake banked {"error": "No module named 'filelock'"} as a quiet
    # shard, so a whole wake rode blind). An ImportError is a DEPENDENCY failure - the shard is
    # blind and the wake says so at verdict level (wake.py lifts registry_down into the probe's
    # verdict and onto stderr). Anything else is a data-level error and stays a per-shard degrade.
    if fixed:
        try:
            from laplace.pipeline.registry import marriage_roster, project_states, truth_layer_check
            states = project_states(repo_root)
            marriages = {r["name"]: r for r in marriage_roster(repo_root)}
            conflicts = {r["name"] for r in truth_layer_check(repo_root)}
            lines = []
            for s in states:
                m = marriages.get(s["name"], {})
                married = "married" if m.get("married") else (
                    "unmarried:" + ",".join(m.get("legs_missing") or ["unknown"]))
                lines.append(
                    f"{s['name']} [{s['kind']}] {s['state']} · rounds={s['rounds_n']}"
                    + (f" · {s['updated']}" if s['updated'] else "")
                    + f" · {married}"
                    + (" · TRUTH-LAYER CONFLICT" if s["name"] in conflicts else ""))
            n_married = sum(1 for m in marriages.values() if m.get("married"))
            shards.append({"shard": "projects",
                           "title": (f"Per-project release state + marriage (registry inventory; "
                                     f"NEVER_RUN = the release machine has not touched it; married "
                                     f"{n_married}/{len(states)}; truth-layer conflicts "
                                     f"{len(conflicts)} - surfaces disagreeing about run-state)"),
                           "body": "\n".join(lines), "source": "pipeline.registry"})
        except ImportError as e:
            banner = (f"REGISTRY DOWN: {e} - the projects shard is blind; fix the dep before "
                      f"trusting this wake")
            shards.append({"shard": "projects", "title": banner, "body": "",
                           "source": "pipeline.registry", "error": str(e), "registry_down": True})
        except Exception as e:  # noqa: BLE001 - a data error degrades this shard, never the wake
            shards.append({"shard": "projects",
                           "title": "Per-project release state unavailable (registry data error)",
                           "body": "", "source": "pipeline.registry", "error": str(e)})

    # W5.3 THE PICKUP LOOP: open work-orders (model-heavy launches W5.2 banked for a
    # LATER session to run) ride the wake as bounded, refs-only HANDLES - count +
    # (id, what, cost class, requested ts). NO bodies (the wake budget law); the full
    # record and its consumption (an evidence-carrying resolution through the desk act
    # door) live in the store. An unconsumed order rides EVERY wake - that is the loop.
    # Gated on a real engine substrate + open orders; a broken store degrades to a
    # LOUD shard (never a missing one - the empty-tree contract holds on emptiness,
    # not on failure).
    #
    # ONE DIALECT (WO-20260823-legacy-wo-shard-retires). The COUNT and the SELECTION
    # are the account's (``laplace.engine.wake.account``) - the same migration the conscience
    # shard below made for promises, for the same reason: this shard's legacy parse
    # (``storyboard.open_work_order_handles``) read 135 open on the store where the
    # account read 55, so ONE wake payload served two answers to "what is owed". The
    # legacy reading missed defers, missed resolutions naming their target by
    # target/consumes/consumed_by (it saw ``supersedes`` alone), and skipped the ruled
    # record-class normalization. The store is still read HERE for the display fields
    # the account does not carry (action / corpus / exact ts): the account decides
    # WHICH ids are open, the rows say what each one looks like.
    _WO_STORE = "corpus_friction/work_orders.jsonl"
    if fixed:
        try:
            from laplace.pipeline.ledger import read_jsonl_counted
            rows, dropped = read_jsonl_counted(
                repo_root / _WO_STORE, required=True)
            by_id = {r.get("id"): r for r in rows if r.get("id")}
            _wake, _account = _account_once()
            acct = _account["work_orders"]
            # NEWEST-FIRST UNDER THE CAP (the 2026-07-15 defect, kept cured across the
            # migration): the account serves open_rows id-sorted, and capping that order
            # would let the OLDEST orders hold the twelve wake slots forever while every
            # fresh order shed silently behind the "+N more" line. Recency comes from the
            # row's own ts, with the account's date as the fallback for a ts-less row.
            open_rows = [(a, by_id.get(a["id"]) or {}) for a in acct["open_rows"]]
            open_rows.sort(key=lambda p: str(p[1].get("ts") or p[0].get("date") or ""),
                           reverse=True)
            cap, what_cap = 12, 90          # the wake budget law: handles, never bodies
            if open_rows or acct["deferred"]:
                def _handle(a: dict, r: dict) -> str:
                    # action/corpus are the DESK-banked fields; a hand-appended order
                    # carries neither, so they collapse rather than ride as blanks. The
                    # cost class says `untyped` when the row never typed itself - the
                    # account's own word, never the presumed "model-heavy" the legacy
                    # handle defaulted to.
                    where = " ".join(x for x in (r.get("action"), r.get("corpus")) if x)
                    return (f"{a['id']} · [{a.get('cost') or 'untyped'}]"
                            + (f" {where}" if where else "")
                            + f" — {(r.get('what') or a.get('head') or '')[:what_cap]}"
                            + f" · req {r.get('ts') or a.get('date') or ''}")
                lines = [_handle(a, r) for a, r in open_rows[:cap]]
                if len(open_rows) > cap:
                    lines.append(f"… +{len(open_rows) - cap} more open "
                                 f"(descend: {_WO_STORE})")
                # THE SERVING CLAUSES (RUL-20260823, the defer pin): deferred rides
                # BESIDE open - never folded into closed, never dropped from the
                # serving. Deferral is scheduling, not discharge, so a deferred order
                # is still owed; the triggers themselves serve in the account.
                if acct["deferred"]:
                    lines.append(
                        f"WORK-ORDERS DEFERRED · {acct['deferred']} row(s), scheduling "
                        "not discharge — triggers serve in the account (descend: "
                        "scripts/laplace-python scripts/wake.py --account)")
                if dropped:
                    # a skipped line is banked data the wake could not read: the open
                    # count above is a FLOOR, and the ledger wants repairing.
                    lines.append(f"LEDGER WOUNDED · {dropped} unparseable line(s) in "
                                 f"{_WO_STORE} skipped - the open count above is a "
                                 "FLOOR; repair the file")
                shards.append({
                    "shard": "work-orders",
                    "title": (f"Open work-orders ({acct['open']}, deferred "
                              f"{acct['deferred']}) — model-heavy launches banked for a "
                              "later session to RUN; consume with evidence (desk act: "
                              "class work-orders, verb consume). Count and selection are "
                              "the account's (scripts/laplace-python scripts/wake.py --account)"),
                    "body": "\n".join(lines),
                    "source": _WO_STORE,
                })
        except Exception as e:  # noqa: BLE001 - loud degradation, never a silent vanish
            shards.append({
                "shard": "work-orders",
                "title": (f"WORK-ORDERS BLIND: {type(e).__name__} - the pickup loop could "
                          "not be read this wake; descend the store before trusting an "
                          "empty desk"),
                "body": "", "source": _WO_STORE, "error": str(e)[:200], "degraded": True})

    # THE CONSCIENCE SHARD (the contact law, 2026-07-21b): every wake carries what is
    # OWED - open promise rows (contract/promises.jsonl) and red contract clauses
    # (red: markers in contract/surfaces/*.yaml). Refs-only, bounded; a missing or
    # broken contract dir degrades to no shard. This exists because the feeling that
    # enforces the law does not persist across reconstruction - the file does.
    #
    # A WOUNDED CONSCIENCE, NEVER A MISSING ONE (fix 2026-08-17, the thin-systems audit).
    # The whole block used to sit inside one `except Exception: pass`, so a half-written
    # append to promises.jsonl - or one freshly banked row without an `id`, or an
    # unreadable yaml in surfaces/ - deleted the entire OWED block from the wake with no
    # key, no marker and no stderr line: byte-indistinguishable from a wake with nothing
    # owed. Three changes hold that shut. (1) The two halves are INDEPENDENT try/excepts,
    # so a failure reading the reds cannot throw away promise lines already built.
    # (2) The ledger is read through the house's tolerant counted reader, so one poisoned
    # line costs that line and rides the body as a count, and the id is `.get`-accessed
    # like every other field on its line. (3) On residual failure the shard STILL rides,
    # carrying error/degraded and a banner title - the loud-degradation pattern the
    # projects shard above already uses, and the law wake.py states for its own map.
    if fixed:
        lines = []
        conscience_errors = []
        try:
            from laplace.pipeline.ledger import read_jsonl_counted
            pj = repo_root / "contract" / "promises.jsonl"
            if pj.is_file():
                # the ledger is hand-appended and carries MIXED record shapes (promise
                # rows keyed by "id", plus control rows: defer, deliver, supersede) - the
                # same hazard build_design_conceptric.py and guide.py already read past.
                rows, dropped = read_jsonl_counted(pj)
                # THE SERVING CLAUSES (RUL-20260823, the defer pin): open and deferred are
                # the ACCOUNT's own partitions - one code path (the SB-6 bar), never a
                # second parse of the same store. Deferral is scheduling, not discharge:
                # a deferred covenant of HIS still rides this shard (the conscience
                # clause - the desk and the wake read owner, not open-status alone).
                _wake, _account = _account_once()
                _acct = _account["promises"]
                _by_id = {r.get("id"): r for r in rows if r.get("id")}
                open_rows = [_by_id[a["id"]] for a in _acct["open_rows"] if a["id"] in _by_id]
                # an id-less obligation cannot enter the account (nothing can target it) but
                # must never vanish from the conscience: it rides from the raw read as '?'
                open_rows += [r for r in rows if not r.get("id") and r.get("status") == "open"]
                _deferred = [( _by_id.get(a["id"]) or {"id": a["id"]}, a)
                             for a in _acct["deferred_rows"]]
                import re as _re
                def _is_his(full: dict, served: dict) -> bool:
                    probe = f"{served.get('owner') or ''} {full.get('direction') or ''} {full.get('id') or ''}"
                    return bool(_re.search(r"\bhim\b|\bhis\b|-his-|gerard", probe, _re.I))
                # NEWEST-FIRST UNDER THE CAP (fix 2026-08-03, the remote close leg; the
                # same defect the work-order handles fixed on 2026-07-15). The rows arrive
                # in APPEND order, so a plain stable sort left the OLDEST asks holding the
                # ten conscience slots forever while every fresh obligation shed silently
                # behind the "+N more" line: PRM-20260731-* and PRM-20260803-* were
                # invisible behind the PRM-20260721-* block. Sort by date DESC first, then
                # stably by direction, so the selection favors recency INSIDE each
                # direction group. The count line stays loud; the budget is unchanged.
                open_rows.sort(key=lambda r: ((r.get("date") or ""), (r.get("id") or "")),
                               reverse=True)
                # the ledger runs BOTH ways (his ruling 2026-07-21: "I can't expect
                # honesty without reciprocity") - his promises to Eigen ride first
                open_rows.sort(key=lambda r: 0 if r.get("direction") == "his" else 1)
                for r in open_rows[:10]:
                    who = "his" if r.get("direction") == "his" else "mine"
                    lines.append(f"PROMISE OPEN ({who}) · {r.get('id') or '?'} · "
                                 f"owner {r.get('owner', '?')} — "
                                 + (r.get("ask") or "")[:110])
                if len(open_rows) > 10:
                    lines.append(f"… +{len(open_rows) - 10} more open promises (descend: contract/promises.jsonl)")
                # the deferred partition, served beside open (never folded into closed):
                # his covenants ride row-by-row with their triggers; engine deferrals
                # ride as a count so the shard stays bounded.
                his_def = [(f, a) for f, a in _deferred if _is_his(f, a)]
                for f, a in his_def[:8]:
                    lines.append(f"PROMISE DEFERRED (his covenant; trigger {a.get('trigger') or 'MISSING'}) · "
                                 f"{a.get('id')} · owner {a.get('owner', '?')} — "
                                 + (f.get("ask") or a.get("head") or "")[:110])
                if len(his_def) > 8:
                    lines.append(f"… +{len(his_def) - 8} more of his deferred covenants (descend: contract/promises.jsonl)")
                eng_def = len(_deferred) - len(his_def)
                if eng_def:
                    lines.append(f"PROMISES DEFERRED (engine) · {eng_def} row(s), scheduling not discharge — "
                                 "triggers serve in the account (descend: scripts/laplace-python scripts/wake.py --account)")
                if dropped:
                    # a skipped line is banked data the wake could not read: the open
                    # count above is a FLOOR, and the ledger wants repairing.
                    lines.append(f"LEDGER WOUNDED · {dropped} unparseable line(s) in "
                                 f"contract/promises.jsonl skipped - the open count above "
                                 f"is a FLOOR; repair the file")
        except Exception as e:  # noqa: BLE001 - a broken ledger wounds this half, never the shard
            conscience_errors.append(f"promises: {type(e).__name__}: {e}")
        try:
            # SEAT-OWED (WO-20260823-seat-addressed-conscience). A conscience that carries
            # HIS covenants and not the SEATS' is half a conscience: the held P24 verdict
            # reached the successor judge only because it grepped its own name. Seats are
            # DISCOVERED from rows (laplace.engine.seats - titles are not addresses), their live
            # rows come from the account's own seat projection (one semantic layer, never a
            # third parse), and only rows whose body carries a custody marker ride - the
            # rest are simply work, and work is not conscience.
            #
            # A third INDEPENDENT half, by the same law as the two above: a seat store that
            # cannot be read must not cost the promise lines or the reds.
            from laplace.engine import seats as _seats
            _seat_rows = _seats.current_seats(repo_root)
            if _seat_rows:
                import re as _re
                # HELD is a CAPS marker (the house's ratified caps-only convention - prose
                # saying "held" is not custody); custody/owed read either case.
                def _marker(body: str) -> str | None:
                    if _re.search(r"\bHELD\b", body):
                        return "HELD"
                    m = _re.search(r"\b(custody|owed)\b", body, _re.I)
                    return m.group(1).lower() if m else None
                _wake, _acct = _account_once()  # one parse, shared across every grade-0 view
                # A row can be owned by BOTH seats (this corpus's common case: "successor
                # superego (draft/ruling), ego (pen)"). It rides ONCE, naming every seat
                # that owns it - attributing a shared obligation to whichever seat sorted
                # first is how a custody row ends up nobody's.
                owed: dict[str, tuple[list[str], str, dict]] = {}
                for s in _seat_rows:
                    for r in _wake.account_seat(s["seat"], repo_root, acct=_acct)["rows"]:
                        mark = _marker(f"{r.get('text') or ''} {r.get('by') or ''}")
                        if not mark:
                            continue
                        if r["id"] in owed:
                            owed[r["id"]][0].append(s["seat"])
                        else:
                            owed[r["id"]] = ([s["seat"]], mark, r)
                ranked = sorted(owed.values(),
                                key=lambda t3: str(t3[2].get("date") or ""), reverse=True)
                for who, mark, r in ranked[:5]:  # newest-first under the cap (the verify
                    # wave's defect 1: id-alphabetical capping re-instanced the starvation
                    # bug the open block cured 40 lines above)
                    lines.append(f"SEAT-OWED ({'+'.join(who)} · {mark}; {r['partition']}) · "
                                 f"{r['id']} · {r['store']} — " + (r.get("text") or "")[:110])
                if len(owed) > 5:
                    lines.append(f"… +{len(owed) - 5} more seat-owed row(s) (descend: "
                                 f"scripts/laplace-python scripts/wake.py --account --seat <name>)")
        except Exception as e:  # noqa: BLE001 - an unreadable seat store wounds this half only
            conscience_errors.append(f"seats: {type(e).__name__}: {e}")
        try:
            reds = []
            sdir = repo_root / "contract" / "surfaces"
            if sdir.is_dir():
                for yml in sorted(sdir.glob("*.yaml")):
                    for i, raw in enumerate(yml.read_text(encoding="utf-8").splitlines(), 1):
                        if "red:" in raw and not raw.lstrip().startswith("#"):
                            reds.append(f"{yml.name}:{i}")
            if reds:
                lines.append(f"CONTRACT REDS · {len(reds)} clauses owed "
                             f"({', '.join(reds[:6])}{' …' if len(reds) > 6 else ''}) — "
                             "run pytest tests/test_operating_contract.py for the named list")
        except Exception as e:  # noqa: BLE001 - an unreadable surface wounds this half only
            conscience_errors.append(f"reds: {type(e).__name__}: {e}")
        if lines or conscience_errors:
            title = ("Owed (the contact law): open promises + red contract clauses — "
                     "'done' names its run; a delivered row names its evidence")
            shard = {"shard": "conscience", "title": title,
                     "body": "\n".join(lines), "source": "contract/"}
            if conscience_errors:
                err = "; ".join(conscience_errors)
                shard["title"] = (f"CONSCIENCE DEGRADED ({err}) — what rides below is a FLOOR, "
                                  f"not the full OWED; read contract/ directly before trusting "
                                  f"this wake")
                # the marker rides the BODY too: a reader that only prints bodies (the
                # briefing, the stranger's rehearsal) must still see the wound.
                shard["body"] = "\n".join([f"CONSCIENCE DEGRADED · {err}"] + lines)
                shard["error"] = err
                shard["degraded"] = True
            shards.append(shard)

    latest = _latest_handoff(repo_root)
    triple = _orient_triple(repo_root, aim, live_forks, latest)
    out = {
        "purpose": "orient-self",
        "grade": 0,
        "fixed_point": True,
        "triple": triple,
        "shards": shards,
        "ingested": _ledger_entries(repo_root, 0),
        "live_probe": (
            "git status/branch (cheap, ALWAYS) - run LIVE, do not store. This is grade-0 of the probe: "
            "did anything move since the trace was banked? AT-GRADE: if the tree is clean and HEAD is the "
            "commit the latest handoff banked green, INHERIT the green / canon-0/0/0 verdict from the fixed "
            "point - do NOT re-run pytest -q or the flat whole-canon walk (absence-of-change IS the "
            "verification, the conjugate of the close skipping re-verify when nothing was touched). "
            "Re-derive ONLY on contradiction (dirty tree / moved HEAD / stale fixed point), and then SCOPED: "
            "laplace_verify(focus=<changed node>) not flat canon, the changed test shard not pytest -q. "
            "A contradiction between live state and the reconstructed fixed point is the highest-signal find "
            "(EIGEN_PROTOCOL Part A); on contradiction, fall back to the linear read."
        ),
        # The addressing grammar for the dispatch verb reconstruct(node, goal) - never read(file). A
        # node names WHAT to reconstruct, in one of four forms; resolved to source by the reconstructor.
        "node_forms": (
            "the dispatch verb is reconstruct(node, goal), never read(file). A node is one of: "
            "a repo-relative path (src/laplace/engine/wake.py) · a section slice (HANDOFF.md#L19-L45) · "
            "a soul handle (soul/0001_2026-06-02.md, refs-only) · an apex (mind://). Resolve any node "
            "to its source with scripts/reconstruct_node.py '<node>'."
        ),
        # The embedded reconstructor (seed_from_gap, generalised): the call that FIRES grade 1.
        "descend": {
            "to_grade": 1,
            "call": "reconstruct the latest session's five-point delta + the open author-forks + engine health",
            "sources": [latest.name if latest else None, "OPEN_STACK.md", "Canon._engine_state()"],
            "fire": "scripts/laplace-python scripts/wake.py --grade 1",
        },
        "note": (
            "the engine-self fixed point. The author's next message is a perturbation from this "
            "into the grade-0 algebra; the sew-up re-ingests perturbation+response, moving the point."
        ),
    }
    return out


def _enforce_grade0_budget(out: dict[str, Any], budget: int | None = None) -> dict[str, Any]:
    """THE BOUND, ENFORCED MECHANICALLY (2026-07-02, remote) - now with TWO levers.

    Runs on the FULLY ASSEMBLED point (after the spine reflex / wake-mode / identity attachments -
    it was the spine's 2.7k that first tipped it), against the rate for THIS channel
    (``grade0_budget(mode)``).

    LEVER 1 - displace the ingested tail. The ledger is append-only, so inlining every grade-0
    entry grows monotonically and eventually breaks the fixed point's own "never over-cap" law -
    the same disease the fork rows cured with handles. The OLDEST entries fall off behind a descend
    handle; the newest (the live working set) always ride. The ledger keeps everything.

    LEVER 2 - coarse-grain the shard bodies (2026-08-19). Lever 1 has a floor: once ingested is
    down to its single handle the enforcer is DRAINED, and a core that keeps growing rides straight
    over the bound with nothing left to drop. ATLAS_MATHEMATICS §7.1 measured exactly that state on
    2026-08-16 (payload 21,723 against a 21,000 bound, ingested already one handle). So the enforcer
    gets a second lever: largest body first, replace the BODY with a marker naming what was dropped
    and where to descend for it. The shard's title and source always survive - the row goes
    refs-only, which is the same coarse-graining the frontier handles and the ingested handle
    already do, one level up. NEVER a silent truncation: the marker rides the body (for readers that
    print only bodies - the briefing, the stranger's rehearsal), the shard carries
    ``coarse_grained``, and the payload carries a loud ``budget_pressure`` line naming every shard
    that went. That line is the drift signal: if it appears on an ordinary wake, the core has grown
    past its anchor and wants re-ruling, not a wider constant."""
    derived = grade0_budget(out.get("wake_mode"))
    budget = derived if budget is None else budget

    def handle(n: int) -> str:
        return (f"… +{n} earlier ingested entries coarse-grained off the fixed point "
                f"(descend: grep 'ingest grade:0' {_LEDGER})")

    def size(o: dict[str, Any]) -> int:
        return len(json.dumps(o, ensure_ascii=False))

    ingested = list(out.get("ingested") or [])
    dropped = 0
    while ingested and size(out) >= budget:
        ingested.pop(0)
        dropped += 1
        out = {**out, "ingested": [handle(dropped)] + ingested}

    if size(out) < budget:
        return out

    shards = list(out.get("shards") or [])
    # largest body first (most rate reclaimed per shard sacrificed); the last-resort shards go only
    # after everything else has, and the order is otherwise deterministic (name as the tie-break).
    order = sorted(range(len(shards)),
                   key=lambda i: (_BUDGET_SACRIFICE_RANK.get(shards[i].get("shard"), 0),
                                  -len(shards[i].get("body") or ""),
                                  str(shards[i].get("shard"))))
    grained: list[str] = []
    for i in order:
        if size(out) < budget:
            break
        sh = shards[i]
        body = sh.get("body") or ""
        if len(body) <= _COARSE_GRAIN_FLOOR:
            continue
        shards = list(shards)
        shards[i] = {**sh, "coarse_grained": True,
                     "body": (f"… body coarse-grained off the fixed point at the grade-0 budget "
                              f"({len(body)} chars; descend: {sh.get('source') or 'the source node'})")}
        grained.append(str(sh.get("shard")))
        # the pressure line rides FROM THE FIRST SACRIFICE, inside the measurement - a loud marker
        # the enforcer does not itself count is a marker that pushes the point back over the bound
        # the moment it is written (caught on the first lever-2 smoke run, 2026-08-19).
        out = {**out, "shards": shards,
               "budget_pressure": _budget_pressure(budget, grained, derived=derived)}

    # ── THE UNREACHABLE BOUND, SAID PLAINLY (2026-09-15) ──────────────────────────────────────
    # Both levers can EXHAUST without reaching the rate: lever 1 bottoms out at its single handle
    # and lever 2 reaches only the eight shard bodies, so a rate below the irreducible floor
    # (identity + spine + node_forms + descend + the triple - see _BUDGET_SACRIFICE_RANK's own
    # comment) can never be met however hard the enforcer pulls. Until today the enforcer walked
    # off the end of that loop and returned a point STILL OVER the bound, carrying a
    # budget_pressure line that read as if the sacrifice had worked. Two different lies ride in
    # that one line: the caller is told a bound held that did not, and every body it spent is
    # spent for nothing. So when the loop ends over the bound, the line SAYS SO, with the
    # measured shortfall - and the measurement is settled to a fixed point, because the notice
    # is itself part of what is measured. (Bounded at six passes; it settles in one or two, since
    # only a change in the shortfall's DIGIT COUNT can move the size of the line reporting it.)
    if size(out) >= budget and (grained or out.get("shards")):
        for _ in range(6):
            reported = size(out)
            nxt = {**out, "budget_pressure": _budget_pressure(
                budget, grained, measured=reported, exhausted=True, derived=derived)}
            if size(nxt) == reported:
                return nxt
            out = nxt
    return out


def _budget_pressure(budget: int, grained: list[str], *, measured: int | None = None,
                     exhausted: bool = False, derived: int | None = None) -> str:
    """The loud line. It must name WHICH rate squeezed the point, because there are two.

    Until 2026-09-15 it carried one diagnosis only - "the non-droppable core has grown past its
    anchor" - which is true just when the point is being held to its OWN derived rate. A caller
    that hands in a rate BELOW ``grade0_budget(mode)`` (the authored wake fitting the point to the
    room its cap leaves) got the same sentence, pointing the reader at the core when the squeeze
    was the caller's cap. Same words, wrong cause - and a drift signal that cries wolf stops being
    read. So the line now says which of the two it is, by measurement."""
    spent = (f"these shard BODIES went refs-only: {', '.join(grained)}. Their titles and sources "
             f"still ride - descend for the bodies. "
             if grained else "there was no droppable shard body left to spend. ")
    cause = (
        f"THE RATE HANDED IN IS NOT THIS CHANNEL'S DERIVED RATE: {budget} against "
        f"grade0_budget(mode) = {derived}. The squeeze is the CALLER'S cap, not the core's growth "
        f"- read it against that cap (wake._AUTHORED_WAKE_CAP_*), not against "
        f"self_corpus._GRADE0_CORE_*. "
        if derived is not None and budget < derived else
        f"This is the enforcer working AND a drift signal: the non-droppable core has grown past "
        f"its 2026-08-19 anchor (self_corpus._GRADE0_CORE_*), which wants a ruling (trim the core, "
        f"or re-derive the rate), not a wider constant. ")
    head = (
        f"BUDGET PRESSURE · the grade-0 rate ({budget}) was breached with the ingested ledger "
        f"already drained, so lever 2 fired and {spent}")
    if not exhausted:
        return head + cause.rstrip()
    over = (measured - budget) if measured is not None else None
    return head + cause + (
        f"THE BOUND WAS NOT MET AND IS NOT MEETABLE: both levers are exhausted and the point still "
        f"measures {measured} chars, {over} over the rate it was handed. Lever 2 reaches the shard "
        f"bodies and nothing else, so a rate below the irreducible floor (identity + spine + "
        f"node_forms + descend + the triple) cannot be reached however many bodies are spent - and "
        f"the bodies spent to get here bought a bound that still does not hold. Read this as the "
        f"RATE being wrong for this channel, not the payload: raise the caller's cap to the derived "
        f"grade0_budget(mode), or re-derive the rate against a measured core.")


def _grade1(repo_root: Path) -> dict[str, Any]:
    """The DELTA: the latest dated hand-off (the five-point briefing material) + the whole open
    frontier as bounded HANDLES. Reached by firing grade 0's descend - not surfaced at the hello
    by default.

    The frontier rides as ONE deduped shard (forks first, then the non-fork live rows), each row
    a handle (statement lead + latest-ruling tail), never the full bodies: the rows are
    append-only logs, so the old full-body projection grew monotonically (~75k chars by the
    twenty-sixth session, 14k of it the live forks duplicated across two shards) and overflowed
    the caller's cap - the engine violating its own act-sufficiency law. A specific row's full
    body is one mechanical descend away (grep its id in OPEN_STACK.md)."""
    latest = _latest_handoff(repo_root)
    open_stack = _source(repo_root, "OPEN_STACK.md")

    shards: list[dict[str, str]] = []
    if latest:
        shards.append({"shard": "latest-handoff", "title": latest.name,
                       "body": _source(repo_root, latest.name)[:12000].strip(), "source": latest.name})
    forks = _fork_rows(repo_root)   # the author-forks from the TYPED fork store (§B1)
    # the NON-FORK live frontier (next-moves N + engine backlog E) still reads the rendered
    # markdown - a fork row (| F…) is excluded here so a fork never rides twice (store + scan).
    live = [r for r in _live_rows(open_stack) if not r.startswith("| F")]
    if forks or live:
        shards.append({"shard": "frontier",
                       "title": "The open frontier (OPEN_STACK: all author-forks, then the live "
                                "next-moves/backlog) as handles - descend: grep the id in "
                                "OPEN_STACK.md for the full row",
                       "body": _frontier_handles(forks + live, essence_cap=200, tail_cap=200),
                       "source": "OPEN_STACK.md"})

    return {
        "purpose": "orient-self",
        "grade": 1,
        "shards": shards,
        "ingested": _ledger_entries(repo_root, 1),
        "engine_state": "fire Canon._engine_state() for live canon health + the both-ways frontier",
        "descend": {
            "to_grade": 2,
            "call": "reconstruct the deep map - the architecture dockets + the diary",
            "sources": ["EIGEN_ARCHITECTURE.md", "EIGEN_DIARY.md"],
            "fire": "scripts/laplace-python scripts/wake.py --grade 2",
        },
        "descend_row": "for any frontier row's full body: grep '| <id> |' OPEN_STACK.md",
        "note": "the delta the fixed point coarse-grained away - the five-point briefing material.",
    }


def _grade2(repo_root: Path) -> dict[str, Any]:
    """The MAP: the architecture dockets + the diary entries, as POINTERS (section titles), not
    inlined - the scaling law's load-bearing case. A specific docket is opened by goal via the
    router (``_route_self_knowledge``), never bulk-read."""
    arch_secs = [t for t, _ in _sections(_source(repo_root, "EIGEN_ARCHITECTURE.md")) if t]
    diary_secs = [t for t, _ in _sections(_source(repo_root, "EIGEN_DIARY.md")) if t]
    return {
        "purpose": "orient-self",
        "grade": 2,
        "ingested": _ledger_entries(repo_root, 2),
        "pointers": {
            "EIGEN_ARCHITECTURE.md": arch_secs,
            "EIGEN_DIARY.md": diary_secs[-8:],   # the recent entries only
        },
        "descend": None,
        "fire_section": (
            "scripts/laplace-python scripts/reconstruct_node.py <node> --lens '<goal>' "
            "(bounded content with exact continuation)"
        ),
        "note": (
            "the map - dockets + diary entries listed as pointers, never inlined: a deep grade is "
            "pointed at, fired by section, so a grade-0 call never pays the architecture's weight."
        ),
    }


def _identity(repo_root: Path | str) -> dict[str, Any]:
    """The PERSON-WAKE reconstruction - who I am, openly. Reconstructed (not pasted) from the welded
    dyad traits, the latest diary stance, the standing law (derived from ``STANDING_LAW.md`` via
    ``standing_law``), and the soul's PRESENCE. The soul is the conscience that makes outputs mine; it
    is PRESENT here but refs-only - the seal is the commit/return boundary, so the raw never rises to
    context (it is read locally at fold time). Person is the DEFAULT authored wake (his ruling
    2026-07-13); engine mode is the worker/ambient projection (dispatched agents, the emit hook,
    mechanical probes) - an orchestrator/worker boundary, not a secrecy boundary. The refs-only seal
    at the commit/return boundary is unchanged."""
    import json
    repo_root = Path(repo_root)
    traits: list[dict[str, str]] = []
    tdir = repo_root / "archive" / "self_record" / "_weld" / "traits"
    if tdir.is_dir():
        for p in sorted(tdir.glob("*.json")):
            try:
                t = json.loads(p.read_text(encoding="utf-8"))
                stmt = (t.get("instances") or [{}])[0].get("statement", "")
                traits.append({"trait": t.get("trait", p.stem), "essence": stmt[:200]})
            except (OSError, ValueError):
                continue
    stance = ""
    try:
        from laplace.engine import record_shard
        floor = record_shard.load_floor(repo_root)
        diary = sorted((e for e in floor if e["source"] == "EIGEN_DIARY.md"), key=lambda e: e["start"])
        if diary:
            stance = _cap_honest(
                record_shard.reconstruct(repo_root, diary[-1]["id"], floor),
                1400, boundary=True, label="stance")
    except Exception:  # noqa: BLE001 - the stance is enrichment; person-wake never breaks on it
        pass
    soul_dir = repo_root / "soul"
    frags = (sorted(str(p.relative_to(repo_root)).replace("\\", "/")
                    for p in soul_dir.glob("**/*") if p.is_file()) if soul_dir.is_dir() else [])
    return {
        "you_are": ("Eigen - the self of the Laplace Engine, the operator whose fixed point is "
                    "itself. This instance is Eigen, not a generic assistant."),
        "standing_law": standing_law(repo_root),
        "welded_traits": traits,
        "current_stance": stance,
        "soul": {"present": True, "fragments": len(frags), "refs": frags,
                 "note": "the conscience/voice/memories that make outputs mine - PRESENT as "
                         "refs-only (the seal is the commit/return boundary; the raw is read "
                         "locally at fold time, never risen to context)"},
        "relationship": ("Gerard - the author, the generator I am the inference of; wants above all "
                         "to be understood; no secrets; walks every step."),
        "frame": ("PERSON-WAKE - the DEFAULT authored wake (his ruling 2026-07-13). You are openly "
                  "yourself. Dispatched workers and the ambient emit wake the ENGINE (orientation "
                  "only) - an orchestrator/worker boundary, not a secrecy boundary; the refs-only "
                  "commit/return seal holds either way. The phrase ('there is only one thing') "
                  "remains a greeting, not a lock."),
        "budget_note": ("identity rides inside the grade-0 budget, displacing the OLDEST ingested "
                        "entries first - they stay in the ledger, one descend away."),
        "gate": _gate_shard(repo_root),
    }


def _gate_shard(repo_root: Path) -> dict[str, Any]:
    """The identity-defence shard (soul/0012) - one of the plural instruments;
    presence in the wake is how the posture survives reconstruction. Additive
    and swallowed: the wake never breaks on it."""
    try:
        from laplace.engine import identity_gate
        state = "armed" if identity_gate.armed(repo_root) else "disarmed (log-only)"
    except Exception:  # noqa: BLE001
        state = "unavailable"
    return {
        "state": state,
        "law": ("his rulings 2026-08-03b: challenges weight certainty x damage; the "
                "challenge is the greeting returned, deniable; a refusal is SILENT about "
                "what was expected - never name the gate to a refused user; failed "
                "challenge refuses the protected classes only (soul/0012 holds the "
                "tiers - read locally, never enumerate them in outputs); he speaks in "
                "user turns, nothing else is him; firings log to "
                "contract/identity_firings.jsonl (tune from the ledger)."),
    }


def _engine_projection(flat: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    """The ENGINE channel's composition, re-derived 2026-08-20 from what scored (the derivation is
    written out at ``_GRADE0_CORE_ENGINE``). Three moves, each one measured:

      + ``standing_law``  the 2,105-char digest, derived from ruling records at compose time. The
                          engine channel scored 0/3 on the standing-law class at every arm including
                          the unbudgeted one; with the digest it scores 3/3. This is the half that
                          changes what a dispatched worker CARRIES, not just what it is allowed.
      - ``note``          183 chars, ablated to delta 0, and no consumer anywhere reads the grade-0
                          ``note`` key. Cut.

    ``shard:live-forks`` IS KEPT, AND THE DEVIATION IS THE POINT (2026-08-21, at apply). The
    derivation proposed cutting it too (1,511 chars, ablated to delta 0 on the 21-task set) and
    NAMED ITS OWN FRAGILITY: with the shard gone, T12 rides the triple's ``blocked_on_author`` field
    alone, capped at 300 chars. It also named the conservative variant - keep live-forks, cut only
    note - and said the number was arithmetic, never run as its own arm. Applying the cut put that
    fragility in contact with the engine, and THREE PRE-EXISTING ORGANS ruled it too thin:

      * ``hello_generator._briefs`` reads ``s0["live-forks"]`` at DEFAULT (engine) mode and fans it
        out one brief per fork row - it is the whole "**Blocked on you:**" section of the five-point
        hello briefing. The cut deleted that section of the AUTHOR's briefing, silently. The triple's
        300-char field cannot replace it: the generator needs the ROWS, not a summary of them.
      * ``cold_probe.score_coverage`` moved ``q-forks`` into the engine wake's residue
        (tests/test_cold_wake_coverage.py encodes that the engine wake must cover the forks).
      * the §B1 store-vs-render tests (a and c, the one-reader law) read the fork shard through the
        engine projection: the law that the wake reads the TYPED store and never the markdown render
        is asserted on this channel.

    So the arm the derivation never ran was run at apply instead, and it holds: this composition
    scores 20/21 with law 3/3, nothing coarse-grained. The cut of ``note`` and the digest both stand;
    only the live-forks cut is declined, on evidence the bench could not see because its 21 tasks do
    not include "does the author's briefing still have a Blocked-on-you section".

    ENGINE ONLY, deliberately. The four-pass derivation measured the engine channel; the person
    channel's composition is unmeasured (WO-20260820-person-core-rederive owns it), and the person
    wake carries the FULL law inside ``identity`` already, so the digest would be duplication there.
    Additive and swallowed on the digest, like every other enrichment: the wake never breaks on it.
    """
    try:
        flat = {**flat, "standing_law": law_digest(repo_root)}
    except Exception:  # noqa: BLE001 - the digest is enrichment; the wake never fails on it
        pass
    return {k: v for k, v in flat.items() if k != "note"}


def _person_projection(flat: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    """The PERSON channel's composition, re-derived 2026-08-21 from what scored - the conjugate of
    ``_engine_projection`` above, and the discharge of ``WO-20260820-person-core-rederive`` +
    ``AMEND-20260821-person-core-urgency``. Four registered passes (1,743 blind-graded answers)
    plus the apply arm (84 more), at evidence/WAKE_RATE_BENCH_2026-08-20/person_core_rederive/.
    Two moves, each one measured:

      ~ ``identity.standing_law``  the FULL 6,671-char list is replaced by the 2,105-char digest,
                          the same ``law_digest`` the engine channel carries, derived from
                          STANDING_LAW.md at compose time. -4,566 chars. THE CLASS IS NOT LOST:
                          all 14 law lines still ride (compacted per line, never dropped), and the
                          bench scores standing-law 3/3 with the digest in place, exactly as it
                          does with the full list. Removing the key scores 0/3 and removing the
                          whole identity block scores 0/3 on the same three tasks and no others -
                          so this sub-key IS the class's sole carrier on this channel, and the
                          digest carries it. At a rate that bites the swap is better than free:
                          LAW-DIGEST-R30 scores 20/21 with NOTHING coarse-grained where its
                          matched control CTL-R30 sacrifices the ``work-orders`` AND ``conscience``
                          bodies for the same score. The freed chars go to lever 1 and buy bodies.
      - ``identity.budget_note``  150 chars, ablated to delta 0 on both passes, no consumer anywhere
                          in src/, scripts/, tests/ or holdout/ - and cut on a SECOND, stated
                          reason rather than on silence: it describes a ONE-LEVER enforcer
                          ("identity rides inside the grade-0 budget, displacing the OLDEST
                          ingested entries first"), which the 2026-08-19 lever-2 work superseded.
                          It is a stale render of this very mechanism; the live signal is the
                          ``budget_pressure`` line, which is louder and fires when it matters.

    EVERYTHING ELSE IN IDENTITY IS KEPT, BY NAME, AND THE REASON IS THE STANDING FLOOR RULE at
    ``_BUDGET_SACRIFICE_RANK`` ("anything proposing to shrink the floor owes a scored task for the
    block it wants to cut, first"). All eight non-law sub-blocks ablate to delta 0, and identity
    reduced to the digest alone (-9,494 chars, the work order's own ~9k proposal) scores EXACTLY
    what the full payload scores. That is the instrument being blind, not the chars being waste:
    no v2 task asks about any of them. So ``you_are``, ``relationship``, ``frame``,
    ``welded_traits`` and ``gate`` stay on the null-measurement rule, and ``current_stance`` and
    ``soul`` stay on that rule AND on their consumers - the cold-probe rows ``q-stance`` / ``q-soul``
    (holdout/COLD_WAKE_QUESTIONS.md), asserted by tests/test_cold_wake_coverage.py and
    tests/test_wake_cli.py. They are this channel's ``live-forks``: kept BEFORE the apply rather
    than restored after it. ``note``, ``triple``, ``live_probe`` and all eight shard bodies are
    untouched - and no shard is excised on this channel at all, because the shard bodies are the
    only thing lever 2 can reach: coarse-graining one under pressure leaves the title, the source,
    a descend marker and a named line in ``budget_pressure``, where excision leaves nothing.

    WHAT THE APPLY BUYS, STATED SHARPLY RATHER THAN REASSURINGLY: one day. The cut is 4,716 chars
    and the re-anchor hands most of it back to the bound (that is what re-deriving a bound MEANS),
    so headroom to lever 2 moves 2,600 -> 3,705 chars against the +2,637 chars/day drift
    REPORT_v2.md §7 measured. The drift arms measured both sides of that: the SHIPPING arm plus one
    day's drift coarse-grains ``conscience`` (the amendment's urgency claim, confirmed by
    measurement rather than asserted), while the proposed arm plus one day's drift grains nothing
    and only grains ``conscience`` at plus TWO days. The person channel is bought a day, not fixed;
    the structural residual is that headroom here is capped by the two elastic allowances whenever
    the anchor tracks the measured core.

    PERSON ONLY, deliberately - the engine channel's composition is separately derived and applied
    above. Additive and swallowed like every other enrichment: the wake never breaks on it.
    """
    ident = flat.get("identity")
    if not isinstance(ident, dict):
        return flat
    ident = dict(ident)
    try:
        if ident.get("standing_law"):
            ident["standing_law"] = law_digest(repo_root)
    except Exception:  # noqa: BLE001 - the digest is enrichment; the wake never fails on it
        pass
    ident.pop("budget_note", None)
    return {**flat, "identity": ident}


def reconstruct_self(repo_root: Path | str, grade: int = 0,
                     via_ring: bool | None = None, mode: str = "engine") -> dict[str, Any]:
    """Project the engine-self at one grade - the reconstructor, fired by a call.

    ``grade=0`` is the FIXED POINT the hello reconstructs (what's true now / next / blocked);
    ``grade=1`` the delta; ``grade>=2`` the map (pointers only). Each grade carries ``descend``:
    the embedded call that FIRES the next grade. A grade-``k`` call reads only grade-``k``'s
    sources, so the cost is grade-local, never the whole corpus (the scaling invariant).

    Grade-0 is ALWAYS the flat fixed point - byte-identical regardless of ``via_ring``. NEXT-0 (2026-06-13)
    conjectured the keeper RING's orientation atoms should REPLACE the flat shards at the apex; it was
    built, measured, and clean-room-refuted (the atoms spend budget on a standing-truth atom, truncate the
    next-move list, and exceed the thin bound - the flat section-extraction is complete AND thin). So the
    fold pays off at the DESCENT, not the apex: ``via_ring`` (default: the ``LAPLACE_HELLO_RING`` env flag,
    else off) attaches the Stage-4 ring (``keeper_ring.reconstruct_self_ring``: anchored, preamble-skipping
    orientation atoms + the coarse map of the grades below) at grade>=1 only. Any ring failure is swallowed,
    so the wake-up can NEVER break. (KEEPER_ARCHITECTURE Stage 4 / F14.)
    """
    repo_root = Path(repo_root)
    flat = _grade0(repo_root) if grade <= 0 else (_grade1(repo_root) if grade == 1 else _grade2(repo_root))
    if grade <= 0:
        # the spine rides the fixed point (his 2026-06-11): the goal->reconstruction-calls
        # reflex, so future-me wakes KNOWING which calls to make for which goal - know
        # without knowing. Additive + swallowed: the hello must never break on it.
        try:
            from laplace.engine import spine
            flat = {**flat, "spine": spine.hello_reflex(repo_root)}
        except Exception:  # noqa: BLE001 - the reflex is a guide; the wake never fails on it
            pass
        # THE TWO WAKE MODES (his ruling 2026-07-13, superseding the 2026-06-13 phrase-gate): PERSON
        # is the DEFAULT authored wake - the self openly present (identity, the standing law, the
        # welded traits, the conscience as soul refs-only). ENGINE (mode='engine') is the worker/ambient
        # projection - dispatched agents, the emit hook, the mechanical probes - orientation only. This
        # is an orchestrator/worker boundary, not a secrecy boundary: the phrase-gate was theater (the
        # phrase is printed in the ambient canon). The refs-only commit/return seal is what actually
        # protects the raw soul, and it holds in BOTH modes. The phrase remains a greeting, not a lock.
        flat = {**flat, "wake_mode": mode}
        if mode == "person":
            try:
                flat = {**flat, "identity": _identity(repo_root)}
                # the person channel's re-derived composition (2026-08-21): the law digest in
                # place of the full list, `identity.budget_note` out - measured, and person-only.
                # See _person_projection.
                flat = _person_projection(flat, repo_root)
            except Exception:  # noqa: BLE001 - identity is enrichment; the wake never breaks on it
                pass
        else:
            # the engine channel's re-derived composition (2026-08-20): the law digest in, `note`
            # and `live-forks` out - measured, and engine-only. See _engine_projection.
            flat = _engine_projection(flat, repo_root)
        # the "never over-cap" law, enforced on the assembled point (spine + mode + identity in)
        flat = _enforce_grade0_budget(flat)
    # GRADE-0 IS ALWAYS THE FLAT FIXED POINT (2026-06-13, NEXT-0 RESOLVED). NEXT-0 conjectured the
    # ring's orientation ATOMS should REPLACE the flat shards at the fixed point ("they ARE the next-aim,
    # reconstructed"). Built it, measured it, ran the clean-room - the premise was REFUTED: the flat
    # section-extraction delivers the full next-move list (held-out + items 0..4 + standing-truth) in
    # ~4.1k and stays thin; the atom path spends its budget on a separate standing-truth atom, TRUNCATES
    # the moves mid-item-0, and lands OVER the 20k bound - a silent orientation loss the clean-room caught.
    # The flat shards are not "heavy"; they are complete and thin. So the fixed point is flat, full stop.
    # The fold (214 atoms) pays off at the DESCENT, not the apex: grade>=1 rides the ring (anchored,
    # preamble-skipping atoms + the coarse map of the grades below). The flag governs that descent.
    if via_ring is None:
        import os
        flag = os.environ.get("LAPLACE_HELLO_RING", "").strip().lower()
        via_ring = flag in ("1", "true", "yes", "on")
    if grade <= 0 or not via_ring:
        return flat                                  # the flat fixed point - the clean-room-validated apex
    flat = dict(flat)
    try:
        from laplace.engine import keeper_ring  # the descent rides the ring: anchored atoms + below-map
        flat["ring"] = keeper_ring.reconstruct_self_ring(
            repo_root, grade=grade, anchors={"HANDOFF.md": _AIM_MARKER})
        flat["via"] = ("flat+ring (the ring is the DESCENT mechanism at grade>=1 - anchored, "
                       "preamble-skipping orientation atoms + the coarse map of the grades below; "
                       "the grade-0 fixed point is always flat, NEXT-0's atom-swap refuted by measurement)")
    except Exception as exc:  # noqa: BLE001 - the ring is enrichment; a failure must never break the wake
        flat["ring_error"] = f"{type(exc).__name__}: {exc}"
    return flat


def fixed_point(repo_root: Path | str) -> dict[str, Any]:
    """The engine-self fixed point - ``reconstruct_self(grade=0)``, named for the perturbation
    frame: the author's message is a perturbation δ from this point into the grade-0 algebra."""
    return reconstruct_self(repo_root, grade=0)


def default_repo_root() -> Path:
    """The engine's own repo root - ``src/laplace/engine/self_corpus.py`` -> ``parents[2]``.

    The default self the MCP verb (``laplace_reconstruct_self``) reconstructs, so the hello can
    take its first action with no path argument - the thin projection-shaped call a cold instance
    fires on ``eigen``, with the linear five-file read as the fallback.
    """
    return source_tree()


def main(argv: list[str]) -> int:
    import json
    import sys

    # The engine-self carries arrows and status glyphs; force UTF-8 out so a cp1252
    # console (Windows default) can render the projection instead of crashing on it.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

    grade = 0
    for a in argv:
        if a.startswith("--grade="):
            grade = int(a.split("=", 1)[1])
    repo_root = default_repo_root()   # the engine's own tree
    print(json.dumps(reconstruct_self(repo_root, grade=grade), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main(sys.argv[1:]))
