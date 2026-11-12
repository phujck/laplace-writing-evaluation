"""The SHARED TOY CORPUS of the ATLAS-P1 contract, as typed rows.

This module is the single row inventory every lane-C clause executes against.  It is
data, not a method: no clause may introduce a row that is not here, and no clause may
state a corpus size that disagrees with ROW_COUNT / SPAN_ROW_COUNT below.

Inventory
---------
8 span-bearing rows  r1..r8   (one per dialogue turn t1..t8; these are the only rows
                               with text, so they are the only rows an observation map
                               or a cosine control can score)
2 derived state rows r5b, r8b (typed states extracted from the text of t5 and t8; they
                               carry no text of their own and inherit the witness span
                               of the turn that asserted them)
--------------------------------------------------------------------------------
10 typed rows in typed_row_store; 8 rows in observation_map.

Null sentinel
-------------
NULL is the explicit sentinel (None here; INT32_MIN in the column tensors).  In an
interval containment test a null valid_from reads as -infinity and a null valid_to as
+infinity.  A null is never zero and never silently skipped.

Value dictionaries
------------------
speaker  : user | assistant                 (the ROLE of the turn)
subject  : self | Ana | Miso | ...          ('self' is the account holder / first
                                             person.  The first lane-C draft wrote the
                                             Q3 condition as `subject==speaker`; the
                                             value is renamed `self` because `speaker`
                                             is also a column name and the collision
                                             made r7's typing unreadable.)
kind     : event | state | intent | preference | assertion | correction | question
polarity : asserted | negated | hypothetical | attributed

Date convention
---------------
event_date stores the LOWER bound of the event's interval and date_precision names the
interval's width, so the upper bound is derived mechanically (day -> +0d, week -> +6d,
month -> last day of month, year -> Dec 31).

state_validity_convention@v1 (DECLARED, lane B owns it, lane C consumes it)
---------------------------------------------------------------------------
For a kind==state row:
  * an explicit start surface sets valid_from; otherwise, when the row asserts a
    PRESENT state, valid_from = the session's date (the earliest date at which the
    record witnesses the state) at day precision;
  * an explicit end surface sets valid_to; otherwise valid_to = null (open);
  * when the row asserts a PAST state (a past-tense copula with an explicit end and no
    start surface), valid_from = null (unbounded below).
r8b is the third case: "it was Sheffield, until March" gives an end and no start.
"""

from __future__ import annotations

import datetime as _dt

# --------------------------------------------------------------------------- sessions
SESSIONS = {
    "s1": _dt.date(2026, 1, 5),   # Monday
    "s2": _dt.date(2026, 2, 10),
    "s3": _dt.date(2026, 3, 15),
}

D = _dt.date

COLUMNS = (
    "row_id", "span_id", "session_id", "ordinal", "speaker", "kind", "predicate",
    "subject", "object", "entity", "place", "polarity", "attributed_to", "claim_id",
    "jurisdiction", "valid_from", "valid_to", "event_date", "date_precision", "source_id",
)

# Every column of typed_row_store for every toy row.  span_id t_i is the turn whose
# bytes witness the row.
ROWS = [
    dict(row_id="r1",  span_id="t1", session_id="s1", ordinal=1, speaker="user",
         kind="event", predicate="adopt", subject="self", object="Miso", entity="Miso",
         place=None, polarity="asserted", attributed_to="user", claim_id="c1",
         jurisdiction="J1", valid_from=None, valid_to=None, event_date=D(2025, 12, 29),
         date_precision="week", source_id="src_chat"),
    dict(row_id="r2",  span_id="t2", session_id="s1", ordinal=2, speaker="user",
         kind="state", predicate="residence", subject="Ana", object="Porto", entity="Ana",
         place="Porto", polarity="asserted", attributed_to="user", claim_id="c2",
         jurisdiction="J1", valid_from=D(2026, 1, 5), valid_to=None, event_date=None,
         date_precision="none", source_id="src_chat"),
    dict(row_id="r3",  span_id="t3", session_id="s2", ordinal=1, speaker="user",
         kind="event", predicate="vet_visit", subject="Miso", object=None, entity="Miso",
         place=None, polarity="asserted", attributed_to="user", claim_id="c3",
         jurisdiction="J1", valid_from=None, valid_to=None, event_date=D(2026, 2, 10),
         date_precision="day", source_id="src_chat"),
    dict(row_id="r4",  span_id="t4", session_id="s2", ordinal=2, speaker="user",
         kind="intent", predicate="move", subject="self", object="Lisbon", entity="Lisbon",
         place="Lisbon", polarity="hypothetical", attributed_to="user", claim_id="c4",
         jurisdiction="J1", valid_from=None, valid_to=None, event_date=None,
         date_precision="none", source_id="src_chat"),
    dict(row_id="r5",  span_id="t5", session_id="s3", ordinal=1, speaker="user",
         kind="event", predicate="move", subject="self", object="Lisbon", entity="Lisbon",
         place="Lisbon", polarity="asserted", attributed_to="user", claim_id="c5",
         jurisdiction="J1", valid_from=None, valid_to=None, event_date=D(2026, 3, 15),
         date_precision="day", source_id="src_chat"),
    dict(row_id="r5b", span_id="t5", session_id="s3", ordinal=1, speaker="user",
         kind="state", predicate="residence", subject="self", object="Lisbon",
         entity="Lisbon", place="Lisbon", polarity="asserted", attributed_to="user",
         claim_id="c5b", jurisdiction="J1", valid_from=D(2026, 3, 15), valid_to=None,
         event_date=None, date_precision="none", source_id="src_chat"),
    dict(row_id="r6",  span_id="t6", session_id="s3", ordinal=2, speaker="user",
         kind="event", predicate="meet", subject="Ana", object="Miso", entity="Miso",
         place=None, polarity="asserted", attributed_to="user", claim_id="c6",
         jurisdiction="J1", valid_from=None, valid_to=None, event_date=D(2026, 3, 15),
         date_precision="day", source_id="src_chat"),
    dict(row_id="r7",  span_id="t7", session_id="s3", ordinal=3, speaker="assistant",
         kind="state", predicate="residence", subject="self", object="Leeds",
         entity="Leeds", place="Leeds", polarity="asserted", attributed_to="assistant",
         claim_id="c7", jurisdiction="J1", valid_from=None, valid_to=None, event_date=None,
         date_precision="none", source_id="src_chat"),
    dict(row_id="r8",  span_id="t8", session_id="s3", ordinal=4, speaker="user",
         kind="state", predicate="residence", subject="self", object="Leeds",
         entity="Leeds", place="Leeds", polarity="negated", attributed_to="user",
         claim_id="c7", jurisdiction="J1", valid_from=None, valid_to=None, event_date=None,
         date_precision="none", source_id="src_chat"),
    dict(row_id="r8b", span_id="t8", session_id="s3", ordinal=4, speaker="user",
         kind="state", predicate="residence", subject="self", object="Sheffield",
         entity="Sheffield", place="Sheffield", polarity="asserted", attributed_to="user",
         claim_id="c8", jurisdiction="J1", valid_from=None, valid_to=D(2026, 3, 31),
         event_date=None, date_precision="month", source_id="src_chat"),
]

ROW_BY_ID = {r["row_id"]: r for r in ROWS}
ROW_COUNT = len(ROWS)                 # 10 typed rows

# --------------------------------------------------------------------------- spans
SPAN_TEXT = {
    "t1": "I adopted a cat named Miso last week.",
    "t2": "My sister Ana lives in Porto.",
    "t3": "Miso had her first vet visit today.",
    "t4": "I'm thinking of moving to Lisbon.",
    "t5": "We moved - I live in Lisbon now.",
    "t6": "Ana visited us and met Miso.",
    "t7": "Earlier you said you lived in Leeds.",
    "t8": "No, I never lived in Leeds - it was Sheffield, until March.",
}
SPAN_ORDER = ["t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8"]
SPAN_ROW = {"t1": "r1", "t2": "r2", "t3": "r3", "t4": "r4",
            "t5": "r5", "t6": "r6", "t7": "r7", "t8": "r8"}
SPAN_ROW_COUNT = len(SPAN_ORDER)      # 8 span-bearing rows (the observation map's domain)

# --------------------------------------------------------------------------- relations
# relation_table rows: (relation_kind, src_row_id, dst_row_id, witness_span_id, located_count)
#
# `mentions` links a row to every entity it names; postings in anchor_index are built
# from these.  It is stored as row -> row by naming, for each entity, the rows that
# name it; the read uses only the posting lists, never the mentions edges themselves.
MENTIONS = {           # entity -> rows that name it (the anchor_index posting lists)
    "Miso":      ["r1", "r3", "r6"],
    "Ana":       ["r2", "r6"],
    "Lisbon":    ["r4", "r5", "r5b"],
    "Leeds":     ["r7", "r8"],
    "Sheffield": ["r8b"],
    "Porto":     ["r2"],
    "self":      ["r1", "r4", "r5", "r5b", "r7", "r8", "r8b"],
}

# Row-row edges for the WALK.  For a typed row r whose predicate p is in the
# relation_kind dictionary, lane B emits an edge (kind=p, src=r, dst=r_a) to every row
# r_a that names one of r's arguments (its subject or its object).  Self-loops dropped.
# On the toy the only predicate in the walk dictionary is `meet`, carried by r6.
RELATIONS = [
    ("meet",     "r6", "r2",  "t6", 1),   # r2 names Ana, r6's subject
    ("meet",     "r6", "r1",  "t6", 1),   # r1 names Miso, r6's object
    ("meet",     "r6", "r3",  "t6", 1),   # r3 names Miso, r6's object
    ("corrects", "r8", "r7",  "t8", 1),   # "No, I never lived in Leeds"
]
# argument slots of each walk relation kind (which columns carry its entities)
ARGUMENT_SLOTS = {"meet": ("subject", "object")}

WALK_KINDS = ("meet",)
RESIDUAL_KINDS = {"corrects": "correction"}

# --------------------------------------------------------------------------- questions
QUESTIONS = {
    "Q1": "Which happened first: Miso's vet visit or the move to Lisbon?",
    "Q2": "In how many sessions did I mention Miso?",
    "Q3": "Where do I live now?",
    "Q4": "Did I ever live in Leeds?",
    "Q5": "Who has met Miso?",
    "Q6": "Did I ever live in Manchester?",
}
QUESTION_ORDER = ["Q1", "Q2", "Q3", "Q4", "Q5"]   # Q6 is the empty-mask case (C.11)
GOLD = {"Q1": "the vet visit", "Q2": 3, "Q3": "Lisbon", "Q4": False,
        "Q5": {"Ana"}, "Q6": False}


def date_upper(d, precision):
    """Upper bound of an interval stored as (lower bound, precision)."""
    if d is None:
        return None
    if precision == "day":
        return d
    if precision == "week":
        return d + _dt.timedelta(days=6)
    if precision == "month":
        nxt = _dt.date(d.year + (d.month == 12), (d.month % 12) + 1, 1)
        return nxt - _dt.timedelta(days=1)
    if precision == "year":
        return _dt.date(d.year, 12, 31)
    return d


def contains(valid_from, valid_to, when):
    """Interval containment with null sentinels: null from = -inf, null to = +inf."""
    if valid_from is not None and when < valid_from:
        return False
    if valid_to is not None and when > valid_to:
        return False
    return True
