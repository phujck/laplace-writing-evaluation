"""The declaration a door makes about itself, and the help generated from it.

The friction report of 2026-10-01 measured what a hand-written contract costs.
`help` for the 73 deployed operations returned 220,797 characters, mean 3,025,
and two operations were 90,761 of it: `concept_change` 49,285 and
`structure_change` 41,476, of which 75.3 per cent was a byte-identical duplicate
of itself --- the owner contract embedded once inside the action by
`src/laplace/writing_contracts.py:550` and returned a second time beside it by
`src/laplace/writing_tools.py:271`.  And the sharpest finding was the opposite of
the expected one: three of the four guard facts an arriving caller had to be told
out of band *were stated*, in the third clause of a precondition inside 41,476
characters.  "The repair is not more prose; it is less."

So a door does not describe itself in sentences next to its fields.  It
**declares** itself, and the example below is the exact text a proof executes --- every
line between the two markers, dedented and not rewritten:

    # RUNNABLE EXAMPLE (executed verbatim, marker to marker, by
    # tests/test_generated_contract.py::test_the_module_docstring_example_runs_verbatim)
    from laplace.native.declarations import Declaration, Rule
    from laplace.writing.schemas import SCHEMAS

    declaration = Declaration(
        operation="section_change",
        homes=("block", "plan"), payload=SCHEMAS["section_change"],
        effects=("source section", "reader-plan occurrence"),
        rules=(Rule("identity", field="expected_plan_revision", home="plan",
                    door="src/laplace/project_structure.py:308",
                    says="the plan home's token"),))
    # END RUNNABLE EXAMPLE

`declare("section_change", ...)` is those same arguments through the registry: it builds this
`Declaration` and records it, and refuses a second declaration for an operation --- so in any
process that has imported this module, which is every production process, a `declare` call
cannot run twice and is not a runnable example.  Until the closing read of 2026-10-02 this
paragraph showed one and said "that call is executable as written, and it was run to check
that", while the proof rewrote the call into a `Declaration(...)` before executing it and
`SCHEMAS` was not importable from here at all: a description beside a check the check did not
make, in the module that exists to end those.  The runnable form above is what the proof runs.

There is no handler keyword to pass: `Declaration` has no such field, so typing one raises
`TypeError`, and `tests/test_generated_contract.py` asserts that the deleted keyword appears
nowhere in this docstring --- so the example cannot teach it again, which is exactly how
`review_surface.py:1394-1397`, the docstring this module's last paragraph is about, went five
verbs stale.  `help section_change` renders that rule's door as
`src/laplace/project_structure.py:308@706a8204`; the next paragraph says why.

The act --- the verb, the concept, every other (verb, concept) this operation is, and the
line that dispatches it --- is not an argument: `declare` reads it from the route table
(`src/laplace/native/verbs.py`, generated from `tests/grammar_spec/mapping.csv` and
`tools/writing_verbs/http_routes.csv`) and REFUSES a declaration that states it, so what
help renders is what the dispatch routes on.

and everything a caller reads is generated from that declaration:

  * `help {operation}` --- the declaration rendered once, with the **live tokens**
    of this project filled into `expected`, bounded.
  * `help {}` --- the catalogue, indexed from the same declarations.
  * the operating brief's operation contract, which now carries the declarations'
    digest and the route to read one, not a second copy of all of them
    (`src/laplace/writing/operating.py`).
  * the refusal's repair block (`src/laplace/writing_tools.py:1089`), whose
    `expected` is minted here rather than described.

Three properties are structural, not intended:

1. **A rule names the home, never only the field.**  `Rule(kind="identity")`
   refuses a `home` outside `grammar.HOME_KINDS` and renders the read that serves
   it from `HOME_KINDS[home].read`, so the sentence a caller sees cannot name a
   field without naming where its value comes from.  That is the grammar's one
   sentence (`evidence/.../grammar/GRAMMAR.md` section 0) made unavoidable here.
2. **A rule contains meaningful text.** Type, nonempty content, owner identity and
   clause coverage are checked independently of length. Context size is measured
   at the public help and native registration surfaces; long text is no evidence
   of semantic abstraction or faulty structure.
3. **A declaration does not name its handler.**  `dispatch_site` reads the door's
   own text and returns the line that routes the operation, so `handler` is a
   RESOLVED citation and a typed `handler` is a `TypeError`.  The first version of
   this module typed one per operation, and measured on the identity x contract
   merge, **33 of the 73 were wrong or stale**: ten cited
   `src/laplace/writing_tools.py:213`, the unknown-KEY validation set, and six cited
   the banked-row helpers at `:1145-1151`, so a third of the declarations pointed a
   caller at a guard or at post-processing instead of at the code that runs the
   operation.  A declaration and its handler cannot drift apart, because there is
   only one of them: the door's own text, read when the help is rendered.
   A `Rule.door` is still typed, and `tools/door_citations.py` measures what that
   costs in the current tree; its live census is the measured count. Historical
   literals carry `<file>:<line>@706a8204`; resolved SourceSite anchors carry the
   serving source digest. `help` explains this distinction in `line_numbers`,
   so a caller can tell which source supplied the coordinate.

*Conventional default refused*: **a docstring convention.**  The obvious cure for
a contract that drifts from its code is to generate the contract from the
handler's docstring.  A docstring is prose with a new address: it cannot be
compared, it cannot carry a home, and nothing fails when it is wrong.  The
measured end state of that default is in this tree already ---
`src/laplace/review_surface.py:1394-1397`, a docstring the route itself calls
"the ONE roster", listing 8 verbs while the door accepts 13
(`src/laplace/review_surface.py:1253-1257`), stale by five including the verb
through which every word of the friction report was written.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from laplace.core import grammar as g

# Historical migration segmentation only; never an acceptance limit for authored text.
MIGRATION_CHUNK_CHARS = 160
# A `file:line` is a coordinate in ONE tree, and every lane of this campaign moves lines.
# `handler` is RESOLVED at render time from the door's own text, so it is a coordinate in the
# tree that answers.  A `Rule.door` is still typed, and it was typed against the campaign base:
# Current coordinate coverage and drift are measured by tools/door_citations.py.
# Literal doors retain the historical source coordinate; resolved SourceSite
# anchors carry the serving source digest. The census tests validate range,
# declared-source identity, attribution and the expiry condition directly.
#
# Historical reconciliation found prose tallies describing different trees and
# disagreeing even within one comment. The 2026-10-02 closing read and subsequent
# storage/latency changes exposed that duplicated truth: inserting code moves
# coordinates without changing door meaning. Keep that rationale and provenance,
# while reading current counts from the instrument instead of maintaining another
# numeric copy here. The canonical campaign marker below remains historical.
BASE_REVISION = "706a8204"
#: The marker is a SHIM and carries a shim's expiry, in the grammar's own form.  Its trigger
#: is in code, not in prose: when `tools/door_citations.py` reports
#: `coordinates_whose_line_holds_other_code_in_the_shipped_tree == 0` the typed coordinates no
#: longer drift, `cited()` adds nothing, and the 10,541 characters the law costs across the 73
#: responses (tools/help_cost_parts.py) are given back.  The assertion that the number is
#: still non-zero is in the same test, so the day it reaches zero this shim fails loudly
#: instead of outliving its reason.
BASE_REVISION_EXPIRY = ("retire `cited()` and this marker when tools/door_citations.py reports "
                        "zero drifted coordinates, on WRITING-RECONCILIATION replay parity; "
                        "review 2026-11-01")
# stated once per help response; kept short because every operation's help carries it (D2 help cost)
COORDINATE_LAW = ("@%s: historical commit; @sha256: serving source file; `handler`: this tree."
                  % BASE_REVISION)
#: The SECOND shim this module ships, on the same footing as the first.  The `acts` block
#: (rendered in `help_payload`, where `value["acts"]` is set from `writing_verbs.acts_for`)
#: publishes, in every one of the 73 help
#: responses, what the route table already says --- and it exists only because the table lives
#: in `tests/grammar_spec/mapping.csv`, where a caller cannot read it.  It costs 11,743
#: characters of help (`tools/help_cost_parts.py`).  Until this commit it carried no trigger at
#: all, while the comment in `tests/test_generated_contract.py` claimed one, which is the
#: disease this campaign is about: a description beside a check that the check does not make.
#: The trigger is now a number an instrument prints and a proof asserts:
#: `tools/acts_block_expiry.py` reports
#: `caller_doors_publishing_the_whole_mapping` --- how many single responses a caller can
#: obtain carry every distinct (verb, concept) pair the table holds.  Today 0 (the catalogue is
#: closest, with 80 of 130 (2026-10-20, in-harness join: 91 rows; the instrument prints it): it carries one pair per
#: operation, because an operation name hides more than one act and two names can be one act.  The
#: 73 this line said until the closing read of 2026-10-02 was the row count, which the
#: instrument never printed; 75 (2026-10-05, S2 settings-three-ways) and 80 (2026-10-06, S3
#: dispatch-build's five dispatch operations) are the row count after each was declared.
#: The day a door
#: publishes the mapping, the number is non-zero, the proof asserting it is still 0 goes red,
#: and these 11,743 characters are given back instead of the shim outliving its reason.
ACTS_BLOCK_EXPIRY = ("retire `acts` when tools/acts_block_expiry.py reports a caller door "
                     "publishing the whole mapping, on WRITING-RECONCILIATION replay "
                     "parity; review 2026-11-01")


class SourceSite(str):
    """A resolved coordinate bound to the source bytes that supplied its line."""

    def __new__(cls, coordinate: str, source_sha256: str):
        value = super().__new__(cls, coordinate)
        value.source_revision = "sha256:" + source_sha256
        return value

    def __getnewargs__(self):
        return str(self), self.source_revision.removeprefix("sha256:")


def cited(door: str) -> str:
    """Keep historical literals and current source anchors attributable separately."""
    return "%s@%s" % (door, getattr(door, "source_revision", BASE_REVISION)) if door else door


RULE_KINDS = ("identity", "one-of", "enum", "state", "order", "scope", "shape", "header")
_HANDLER = re.compile(r"^[A-Za-z0-9_./-]+\.py:\d+$")
TOOL_DOOR = "src/laplace/writing/operations.py"
_PACKAGE = Path(__file__).resolve().parents[1]   # the executing laplace package (as core.checkout.package_root)
_SITES: dict[tuple[str, str], str] = {}
_SOURCE_BYTES: dict[str, bytes] = {}
_QUOTED = re.compile(r"""["']([A-Za-z_][A-Za-z0-9_]*)["']""")


def _text(rel: str) -> list[str]:
    return _source_bytes(rel).decode("utf-8", errors="replace").split("\n")


def _source_bytes(rel: str) -> bytes:
    # Coordinate caches already bind this process's source. Read it once so the
    # anchor and digest describe the same bytes, without hashing per operation.
    if rel not in _SOURCE_BYTES:
        _SOURCE_BYTES[rel] = _serving_source(rel).read_bytes()
    return _SOURCE_BYTES[rel]


def _source_site(rel: str, line: int) -> SourceSite:
    return SourceSite("%s:%d" % (rel, line),
                      hashlib.sha256(_source_bytes(rel)).hexdigest())


def _dispatch_span(lines: list[str]) -> tuple[int, int]:
    """The line range of `_execute`, the one function in the tool door that dispatches.

    WHY THE SEARCH IS SCOPED, measured on the whole-system merge.  Unscoped, this function
    answered `store_artifact` with `writing_tools.py:958`, which is
    `elif operation=="store_artifact":` inside `_compact_write_response` --- post-processing of
    a result already produced, not the code that produces it.  Its real dispatch is the shared
    branch at `:482`, exactly as `dispatch_site`'s own docstring says ("`store_artifact` is the
    one operation whose only dispatch is shape 3"), and the route table said `:482` too.  The
    same shape in the other direction: the route table answered `literature_discover` with
    `:665`, inside `read_output_digest`.  So each of the two resolvers the two syntheses
    brought was wrong about exactly one operation, and both errors were a match OUTSIDE the
    dispatch function.  Scoped, there is nothing outside it to match.

    S1 B8 split the one function into `_execute` (admission, then one family) and its
    `_execute_<family>` dispatchers, placed contiguously after it; the region is all of them and
    ends at the next top-level statement that is not one of them.
    """
    first = last = 0
    for number, line in enumerate(lines, 1):
        if line.startswith("def _execute("):
            first = number
        elif first and line[:1] not in ("", " ", "\t", "#") and not line.startswith("def _execute_"):
            return first, number - 1
    return first, len(lines)


def dispatch_site(operation: str) -> str:
    """`src/laplace/native/tools.py:<line>` --- the line that DISPATCHES this operation,
    found in the door's own text rather than typed into the declaration.

    A typed line number is a coordinate in one tree, and every lane of this campaign edits
    this file.  Measured on the identity x contract merge: 33 of the 73 typed handlers were
    wrong or stale --- ten cited `writing_tools.py:213`, the unknown-KEY validation set, and
    six cited the banked-row helpers at `:1145-1151`, so `handler` pointed a caller at a
    guard or at post-processing instead of at the code that runs the operation.  The shapes
    below are the door's whole dispatch vocabulary, in order of specificity:

      1. `if operation == "<op>":` / `elif operation=="<op>":`  (the chain)
      2. `"<op>": (owner, route, method),`                      (the routes table)
      3. `if operation in {"<op>", ...}:`                       (one shared branch)

    Artifact operations resolve their explicit adapter and concrete implementation
    from writing.artifacts.declaration_sites, shared with route generation.
    For the remaining legacy branches, shape 3 is tried ONLY when 1 and 2 find nothing, and then only at the NARROWEST such
    set, because the two widest `operation in {...}` lines in this file are not dispatch at
    all: `:213` validates unknown keys for ten operations and `:324` overwrites `by` for
    four. A policy guard is not an artifact dispatch.
    """
    key = (TOOL_DOOR, operation)
    if key in _SITES:
        return _SITES[key]
    from laplace.projects import artifacts
    if operation in artifacts.OPERATION_OWNERS:
        sites = artifacts.declaration_sites("\n".join(_text(TOOL_DOOR)),
            "\n".join(_text("src/laplace/projects/artifacts.py")))
        _SITES[key] = sites[operation]["handler"]
        return _SITES[key]
    lines = _text(TOOL_DOOR)
    first, last = _dispatch_span(lines)
    exact = ('operation == "%s"' % operation, 'operation=="%s"' % operation,
             "operation == '%s'" % operation, "operation=='%s'" % operation,
             '"%s": (' % operation, "'%s': (" % operation)
    for number, line in enumerate(lines, 1):
        if first <= number <= last and any(shape in line for shape in exact):
            _SITES[key] = _source_site(TOOL_DOOR, number)
            return _SITES[key]
    shared = [(len(_QUOTED.findall(line)), number) for number, line in enumerate(lines, 1)
              if first <= number <= last and "operation in {" in line
              and operation in _QUOTED.findall(line)]
    shared.sort()
    if shared and (len(shared) == 1 or shared[0][0] < shared[1][0]):
        _SITES[key] = _source_site(TOOL_DOOR, shared[0][1])
        return _SITES[key]
    raise ValueError(
        "%r is declared but nothing in %s dispatches it: no `operation == %r`, no routes "
        "entry and no unambiguous shared branch. A declaration cannot name a handler the "
        "door does not have." % (operation, TOOL_DOOR, operation))


def anchored_site(rel: str, anchor: str) -> str:
    """`<rel>:<line>` for a handler outside the tool door, found by its own source text.

    The HTTP door's five declarations name handlers in four other owners, and two of those
    line numbers drifted in this merge alone (`writing_projects.py:209` -> `:217`,
    `review_surface.py:3480` -> `:3508`), because the identity lane added lines above them.
    An anchor is the line's own text, so the citation is resolved, never typed.
    """
    key = (rel, anchor)
    if key in _SITES:
        return _SITES[key]
    hits = [number for number, line in enumerate(_text(rel), 1) if anchor in line]
    if len(hits) != 1:
        raise ValueError(
            "the handler anchor %r occurs %d times in %s; a handler anchor names exactly "
            "one line" % (anchor, len(hits), rel))
    _SITES[key] = _source_site(rel, hits[0])
    return _SITES[key]
_DOOR = re.compile(r"^[A-Za-z0-9_./-]+\.py:[0-9][0-9,:-]*$")


def read_call(raw: str) -> str:
    """The read call alone, without the grammar's commentary about it.

    `HomeKind.read` also carries commentary for some homes. Rules and expected rows
    publish the actionable call; the home's full commentary remains in the grammar.
    """
    text = str(raw or "")
    for separator in ("  (", " (the ", " (NOT ", " (identical", " (pipeline"):
        head = text.split(separator)[0]
        if head != text:
            text = head
    return text.strip()


def clauses(text: str) -> list[str]:
    """Historical segmentation of the pinned migration contract, preserving its chunks.

    The migration from the hand-written table used this function and the coverage proof
    in tests/test_generated_contract.py uses it again, on the pinned base-commit text,
    to show that every clause of every old precondition is carried by some rule.  It
    therefore lives here, with its historical segmentation, and not in the one-time migration
    script: a proof that imported its own splitter from the tool it is checking would
    prove only that the tool agrees with itself.
    """
    parts = re.split(r"(?<=[.;])\s+", str(text).strip())
    out: list[str] = []
    for part in parts:
        part = part.strip()
        while len(part) >= MIGRATION_CHUNK_CHARS:
            cut = max(part.rfind(", ", 0, MIGRATION_CHUNK_CHARS), part.rfind(" \u2014 ", 0, MIGRATION_CHUNK_CHARS),
                      part.rfind(" and ", 0, MIGRATION_CHUNK_CHARS))
            if cut < 40:
                cut = part.rfind(" ", 0, MIGRATION_CHUNK_CHARS)
            if cut < 40:
                out.append(part[:MIGRATION_CHUNK_CHARS - 1])
                part = part[MIGRATION_CHUNK_CHARS - 1:].strip()
                continue
            out.append(part[:cut].rstrip(" ,"))
            part = part[cut:].lstrip(" ,").strip()
        if part:
            out.append(part)
    return [clause for clause in out if clause]


def _strings(value: Any) -> list[str]:
    """Every string inside a nested structure, for migration coverage inspection."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [line for item in value.values() for line in _strings(item)]
    if isinstance(value, (list, tuple)):
        return [line for item in value for line in _strings(item)]
    return []


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str,
                      separators=(",", ":"))


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode()).hexdigest()


@dataclass(frozen=True)
class Rule:
    """One obligation of one door, typed, attached to a field and to the line that enforces it."""

    kind: str
    says: str
    field: str = ""
    home: str = ""
    read: str = ""
    door: str = ""
    fields: tuple[str, ...] = ()
    values: tuple[Any, ...] = ()
    carries: tuple[Any, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in RULE_KINDS:
            raise ValueError("rule kind must be one of %r (got %r)" % (RULE_KINDS, self.kind))
        if not isinstance(self.says, str) or not self.says.strip():
            raise ValueError("a rule with nothing to say is not a rule")
        if self.kind == "identity":
            if self.home not in g.HOME_KINDS:
                raise ValueError(
                    "an identity rule names the home its field's value comes from, and the "
                    "home is one of the %d kinds of GRAMMAR.md section 2; %r is not one. A "
                    "field without a home is the defect this module exists to end."
                    % (len(g.HOME_KINDS), self.home))
            if not self.field:
                raise ValueError("an identity rule names the field the door compares")
        if self.home and self.home not in g.HOME_KINDS:
            raise ValueError("unknown home kind %r" % (self.home,))
        if self.door and not _DOOR.match(self.door):
            raise ValueError(
                "a rule's door is the file:line that enforces it, so a reader can check it; "
                "%r is not one" % (self.door,))

    def rendered(self) -> dict[str, Any]:
        """The sentence, generated from the structure.  Nothing here is typed twice."""
        home = g.HOME_KINDS.get(self.home) if self.home else None
        row: dict[str, Any] = {"rule": self.kind, "says": self.says}
        if self.field:
            row["field"] = self.field
        if self.fields:
            row["fields"] = list(self.fields)
        if self.values:
            row["one_of"] = list(self.values)
        if home is not None:
            row["home"] = self.home
            row["read"] = self.read or read_call(home.read)
            # `bytes` --- the minting recipe --- is NOT rendered here.  It is one
            # sentence per home in GRAMMAR.md section 2 and for `authoring-state` it is
            # a paragraph; repeating it beside every rule that mentions the home put
            # 21,558 characters back into help in the first version of this module, which
            # is the disease, not the cure.  The home's name is the handle; the recipe is
            # read once, from the grammar.
        if self.door:
            row["enforced_at"] = cited(self.door)
        return row


@dataclass(frozen=True)
class Declaration:
    """What one deployed operation is: its verb, its concept, the homes it guards."""

    operation: str
    payload: Mapping[str, Any]
    homes: tuple[str, ...] = ()
    effects: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    recoverable: tuple[str, ...] = ()      # the contract's `recoverable_errors`
    errors: tuple[str, ...] = ()           # the contract's own `errors`, a different list
    extras: Mapping[str, Any] = field(default_factory=dict)
    rules: tuple[Rule, ...] = ()
    does: str = ""
    # A handler is RESOLVED, never typed: `handler_anchor` names the line's own text for a
    # door outside `writing_tools.py`, and the tool door needs nothing at all, because the
    # operation's own name finds its dispatch.  `handler` is the rendered citation.
    handler_anchor: str = ""
    # Public caller tokens are distinct from guards used by a downstream executor.
    caller_expected: bool = True
    turn_bound: bool = False
    turn_door: str = ""
    header: str = ""
    header_door: str = ""
    door: str = "tool"
    variants: str = ""
    protocol: str = ""
    route: str = ""
    # A diagnostic interface projection resolves these exact source anchors.  They live
    # on the declaration, beside its request and response semantics, rather than in a
    # second route registry.  Missing or ambiguous anchors refuse module import.
    consumer_anchors: Mapping[str, str] = field(default_factory=dict)
    response_anchors: Mapping[str, str] = field(default_factory=dict)
    # A part of this door's help that is PRODUCED, never typed: ``{key: "module:function"}``,
    # called when help renders.  The same shape as ``handler_anchor`` and ``expected`` --- a
    # reference resolved at read time instead of a copy that can go stale --- and the reason
    # it exists: model choice is one table (``src/laplace/pipeline/schema.py`` ``TIERS``),
    # and the door, the HTTP catalogue and the composer must read THAT, not a transcription
    # of it in a declaration.  Excluded from ``version`` for the same reason ``expected`` is:
    # it is a live reading, not a clause of the contract.
    derived: Mapping[str, str] = field(default_factory=dict)
    # Actionable owner-produced schemas are exact contract substance. Unlike
    # live observational derived fields, their value also participates in the
    # existing per-action digest; help alone carries their full shape.
    contract_derived: Mapping[str, str] = field(default_factory=dict)

    # ----------------------------------------------------------------- #
    # THE ACT, read from the route table on every access and never stored
    # ----------------------------------------------------------------- #
    # Stored at import time they were a copy with a short life: a row changed after import
    # moved the dispatch and left `help` answering the old verb, which is the two-tables
    # defect again with a shorter fuse.  Read through, `help` cannot disagree with the
    # dispatch even for one call.
    @property
    def acts(self) -> tuple[tuple[str, str], ...]:
        from laplace.native import verbs as writing_verbs
        return writing_verbs.pairs_for(self.operation)

    @property
    def verb(self) -> str:
        return self.acts[0][0]

    @property
    def concept(self) -> str:
        return self.acts[0][1]

    @property
    def also(self) -> tuple[tuple[str, str], ...]:
        return self.acts[1:]

    # ONE handler resolver, not two.  The contract x dispatch synthesis read the dispatch
    # line out of the route table (`writing_verbs.site_for`) and the identity x contract
    # synthesis read it out of the door's own text (`dispatch_site`); the merge briefly
    # defined BOTH as `handler`, which in a class body means the second silently wins ---
    # two tables again, with no error to find it by.  The surviving resolver is the one
    # below, because it is the only one that also answers for the five HTTP declarations,
    # whose handlers are in four other owners and have no route-table row.  That the two
    # agree on every tool-door operation is a check, not a claim:
    # tests/test_generated_contract.py::test_the_two_handler_resolvers_agree.

    def __post_init__(self) -> None:
        if self.verb not in g.VERBS:
            raise ValueError("verb must be one of the nine: %r (got %r)" % (g.VERBS, self.verb))
        if self.concept:
            g.concept_altitude(self.concept)
            obj = g.concept_object(self.concept)
            if obj not in g.HOME_KINDS:
                raise ValueError("the object half of %r is not a home kind" % (self.concept,))
        for raw in self.homes:
            if raw.rstrip("?") not in g.HOME_KINDS:
                raise ValueError("declared home %r is not one of the %d kinds"
                                 % (raw, len(g.HOME_KINDS)))
        if not isinstance(self.does, str):
            raise ValueError("a declaration summary must be text")
        if self.handler_anchor and ":" not in self.handler_anchor:
            raise ValueError("handler_anchor is <path>.py:<exact source text>; got %r"
                             % (self.handler_anchor,))
        if not _HANDLER.match(self.handler):
            raise ValueError("handler must resolve to <path>.py:<line>; got %r"
                             % (self.handler,))
        if self.turn_bound and not self.turn_door:
            raise ValueError("a turn-bound door names the line that refuses without the turn")
        if self.header and not self.header_door:
            raise ValueError("a header precondition names the line that enforces it")
        for label, anchor in {**self.consumer_anchors, **self.response_anchors}.items():
            if not label or ":" not in anchor:
                raise ValueError("interface anchors are named <path>:<exact source text>")
            rel, _, text = anchor.partition(":")
            anchored_site(rel, text)
        for line in list(self.outputs) + list(self.errors) + list(self.recoverable):
            if not isinstance(line, str) or not line.strip():
                raise ValueError("published outputs, errors and recovery must be nonempty text")

    @property
    def handler(self) -> str:
        """The line that runs this operation, resolved from the tree every time."""
        if self.handler_anchor:
            rel, _, anchor = self.handler_anchor.partition(":")
            return anchored_site(rel, anchor)
        return dispatch_site(self.operation)

    @property
    def altitude(self) -> str:
        return g.concept_altitude(self.concept) if self.concept else ""

    @property
    def pairs(self) -> tuple[tuple[str, str], ...]:
        return ((self.verb, self.concept),) + tuple(self.also)

    def guard_fields(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(rule.field for rule in self.rules
                                   if rule.kind == "identity" and rule.field))

    @property
    def methods(self) -> tuple[str, ...]:
        from laplace.native import verbs as writing_verbs
        return writing_verbs.http_methods(self.operation) if self.door == "http" else ()

    @property
    def source_operation(self) -> str:
        from laplace.native import verbs as writing_verbs
        return (writing_verbs.http_source_operation(self.operation)
                if self.door == "http" else "")

    def http_rules(self) -> tuple[Rule, ...]:
        """Transport rules plus identity guards from the existing source operation."""
        inherited = ()
        if self.source_operation:
            owner = DECLARATIONS.get(self.source_operation)
            if owner is None:
                raise ValueError("HTTP source operation has no deployed declaration: "
                                 + self.source_operation)
            inherited = tuple(rule for rule in owner.rules if rule.kind == "identity")
        return tuple(self.rules) + inherited

    def resolved_consumers(self) -> dict[str, str]:
        return {label: anchored_site(*anchor.split(":", 1))
                for label, anchor in self.consumer_anchors.items()}

    def resolved_responses(self) -> dict[str, str]:
        return {label: anchored_site(*anchor.split(":", 1))
                for label, anchor in self.response_anchors.items()}


DECLARATIONS: dict[str, Declaration] = {}
HTTP_DECLARATIONS: dict[str, Declaration] = {}


#: What a declaration may NOT state, because the route table states it: the act (verb,
#: concept, and the other pairs the operation is) and the line that dispatches it.
#: Before this synthesis both tables carried all four.  They agreed on all 73 operations
#: and 104 pairs --- and disagreed about `handler` the moment the two branches were merged,
#: because each lane's citations were written against its own copy of
#: `src/laplace/native/tools.py`: `structure_change`'s route said `:408` and its
#: declaration `:423` for one fact.  A second copy that agrees is still a second copy.
FROM_THE_TABLE = ("verb", "concept", "also", "handler")


def declare(operation: str, **kw: Any) -> Declaration:
    """Register one operation's declaration.  One per operation; a second is refused.

    The act is NOT an argument here.  `verb`, `concept`, `also` and `handler` are read from
    `writing_verbs` --- the generated route table, whose row source is the grammar packet's
    `mapping.csv` for the tool door and `tools/writing_verbs/http_routes.csv` for the HTTP
    door --- so `help` renders exactly what the dispatch routes on, and changing one row of
    that table changes both.  Passing one of them is refused by name.
    """
    stated = [key for key in FROM_THE_TABLE if key in kw]
    if stated:
        raise ValueError(
            "a declaration does not state %s: the route table does, and help reads it from "
            "there (src/laplace/native/verbs.py, generated from tests/grammar_spec/"
            "mapping.csv and tools/writing_verbs/http_routes.csv). Two tables for one fact "
            "is the defect this lane ends." % (", ".join(stated),))
    from laplace.native import verbs as writing_verbs
    writing_verbs.pairs_for(operation)          # refuses an operation the table does not route
    writing_verbs.site_for(operation)           # ... and one it routes without a dispatch line
    declaration = Declaration(operation=operation, **kw)
    registry = HTTP_DECLARATIONS if declaration.door == "http" else DECLARATIONS
    if operation in registry:
        raise ValueError("%r is already declared; one declaration per operation, so there "
                         "is no second copy to disagree with" % (operation,))
    registry[operation] = declaration
    return declaration


# ---------------------------------------------------------------------------
# The payload schemas an owner publishes itself.  These were built inside
# writing_contracts.exact_contract; they move here unchanged, because a schema
# generated from the owner's own contract is the opposite of a hand-written one.
# ---------------------------------------------------------------------------
def _object(required=(), properties=None, *, additional=False):
    return {"type": "object", "required": list(required),
            "properties": properties or {}, "additionalProperties": additional}


_STRING = {"type": "string"}


def _variants_structure_change() -> dict:
    from laplace.manuscript.project_structure import operation_contract
    deployed = operation_contract()
    result = {}
    for name, variant in deployed['operations'].items():
        properties = {**variant['properties'], 'operation': {'const': name}}
        op = properties.get('op')
        if isinstance(op, dict) and op.get('variants'):
            properties['op'] = {'oneOf': [_object(row['required'], row['properties'])
                                         for row in op['variants'].values()]}
        result[name] = {**_object(variant['required'], properties),
                        **{key:variant[key] for key in ('oneOf','allOf') if key in variant}}
    return result


def _variants_concept_change() -> dict:
    from laplace.research.concepts import operation_contract
    deployed = operation_contract()
    out = {}
    for name, variant in deployed["operations"].items():
        required = [key for key in variant["required"] if key != "project"]
        properties = {key: rule for key, rule in variant["properties"].items() if key != "project"}
        properties["operation"] = {"const": name}
        schema = _object(required, properties)
        if variant.get("requires_any"):
            schema["allOf"] = [{"anyOf": [{"required": [key]} for key in group]}
                               for group in variant["requires_any"]]
        out[name] = schema
    return out


def _variants_logical_plan_change() -> dict:
    from laplace.research.concepts import logical_plan_operation_contract
    from laplace.research.mathematical_records import source_reference_schema
    deployed = logical_plan_operation_contract()
    strings = {key: _STRING for key in ("node", "meaning", "parent", "source_ref", "source",
                                        "relation", "rationale", "work_kind",
                                        "discharge_condition", "state", "disposition", "by")}
    strings["source_ref"] = source_reference_schema()
    strings["kind"] = {"enum": deployed["object_kinds"]}
    strings["relation"] = {"enum": deployed["relations"]}
    strings["work_kind"] = {"enum": deployed["work_kinds"]}
    strings["state"] = {"enum": deployed["states"]}
    strings["target"] = {"oneOf": [_object(tuple(rule["required"]),
                                          {key: ({"const": name} if key == "kind" else _STRING)
                                           for key in rule["required"]})
                                   for name, rule in deployed["obligation_target"].items()]}
    strings["evidence"] = {"type": "array", "items": {"type": ["string", "object"]}}
    out = {}
    for name, rule in deployed["operations"].items():
        allowed = list(rule["required"]) + list(rule.get("optional") or [])
        if name == "update_obligation":
            allowed.extend(["evidence", "disposition"])
        allowed = list(dict.fromkeys(allowed + ["by"]))
        properties = {"operation": {"const": name}, "base_revision": _STRING,
                      **{key: strings[key] for key in allowed}}
        if name == "connect":
            properties["target"] = _STRING
        out[name] = _object(tuple(["operation", "base_revision", *rule["required"]]), properties)
    return out


def _variants_concept_tree() -> dict:
    from laplace.research.concepts import tree_contract
    deployed = tree_contract()
    schema = _object([key for key in deployed["required"] if key != "project"],
                     {key: rule for key, rule in deployed["properties"].items()
                      if key != "project"})
    schema["allOf"] = [{"if": {"properties": {"direction": {"const": direction}},
                               "required": ["direction"]},
                        "then": {"required": rule["requires"]}}
                       for direction, rule in deployed.get("navigation", {}).items()]
    return {"navigate": schema}


def _variants_repository() -> dict:
    from laplace.projects.writing_sources import operation_contract
    deployed = operation_contract()
    out = {}
    for name, variant in deployed["operations"].items():
        schema = _object(variant["required"],
                         {key: rule for key, rule in variant["properties"].items()
                          if key != "project"})
        if name in {"read", "view"}:
            schema["allOf"] = [{"if": {"properties": {"path": {"pattern": "\\.[pP][dD][fF]$"}},
                                       "required": ["path"]},
                                "else": {"not": {"anyOf": [{"required": ["page"]},
                                                           {"required": ["page_count"]}]}}}]
        out[name] = schema
    return out


def _variants_section_change() -> dict:
    """Project the conditional schema into complete, discoverable owner forms."""
    import copy
    from laplace.writing.schemas import SCHEMAS
    base = SCHEMAS["section_change"]
    result = {}
    for name in base["properties"]["operation"]["enum"]:
        schema = copy.deepcopy(base)
        schema["properties"]["operation"] = {"const": name}
        for condition in schema.pop("allOf", []):
            selector = condition["if"]["properties"]["operation"]
            if name not in selector.get("enum", [selector.get("const")]):
                continue
            consequence = condition["then"]
            schema["required"].extend(consequence.get("required", []))
            schema.setdefault("allOf", []).append(consequence)
        result[name] = schema
    return result


def _variants_help() -> dict:
    """The current help selector shape added after the byte-exact migrated base schema."""
    return {"current": DECLARATIONS["help"].payload}


def _variants_visual_create() -> dict:
    from laplace.pipeline.visual_production import authoring_contract
    deployed = authoring_contract()
    out = {name: _object(("spec",), {"spec": variant})
           for name, variant in deployed["variants"].items()}
    out["update"] = _object(("spec", "expected_revision"),
                            {"spec": deployed["patch"], "expected_revision": _STRING})
    return out


_VARIANTS = {"section_change": _variants_section_change,
             "structure_change": _variants_structure_change,
             "concept_change": _variants_concept_change,
             "logical_plan_change": _variants_logical_plan_change,
             "concept_tree": _variants_concept_tree,
             "help": _variants_help,
             "repository": _variants_repository,
             "visual_create": _variants_visual_create}

_PROTOCOLS = {"producer_execution_contract":
              ("laplace.research.research_runs", "producer_execution_contract")}


def _owner_examples_visual_create() -> dict:
    from laplace.pipeline.visual_production import authoring_contract
    return dict(authoring_contract()["examples"])


#: Examples an OWNER publishes, per renderer, and therefore not hand-written: they come
#: from `visual_production.authoring_contract()["examples"]` and change when the renderer
#: does.  The 72 deleted examples were literals in writing_contracts.py; these are not,
#: and dropping them in the first pass broke thirteen of the tree's own visual tests,
#: which is how the distinction was found.  The hand-written `update` entry that sat
#: beside them (`"expected_revision": "COPY visuals.specs[id].spec_revision EXACTLY"`) is
#: NOT restored: that one was a literal, and the generated example carries the live token.
_OWNER_EXAMPLES = {"visual_create": _owner_examples_visual_create}


def owner_examples(operation: str) -> dict:
    builder = _OWNER_EXAMPLES.get(operation)
    return builder() if builder else {}


def visual_create_template(kind: str | None = None, *, payloads: bool = True) -> dict:
    """The complete visual_create authoring template, derived from the deployed renderer validator.

    Every required and optional spec field per kind, the exactly-one choices and the owner example come from
    ``visual_production.authoring_contract()``: this is a projection of that one policy for agent help,
    refusals and context, never a second copy. ``kind`` narrows the template to one renderer. ``payloads=False``
    keeps help bounded: each kind names its owner example in the examples section instead of repeating it.
    """
    import copy
    from laplace.pipeline.visual_production import authoring_contract
    deployed = authoring_contract()
    names = [kind] if kind in deployed["variants"] else sorted(deployed["variants"])

    def row(name):
        variant = deployed["variants"][name]
        required = list(variant["required"])
        return {"required": required,
                "optional": sorted(set(variant["properties"]) - set(required)),
                **({"exactly_one_of": [branch["required"][0] for branch in variant["oneOf"]]}
                   if variant.get("oneOf") else {}),
                **({"payload": copy.deepcopy(deployed["examples"][name])} if payloads else
                   {"example": name, "payload_read": {"operation": "help",
                                                      "payload": {"operation": "visual_create", "section": "examples"}}})}
    patch = deployed["patch"]
    return {"schema_version": "laplace.visual-create-template/1", "operation": "visual_create",
            "validator": "laplace.pipeline.visual_production.authoring_contract",
            "top_level": {"new": ["spec"], "same_id_edit": ["spec", "expected_revision"]},
            "kinds": {name: row(name) for name in names},
            "same_id_edit": {"required": ["spec.id", "expected_revision"],
                             "owner_managed": sorted(key for key, shape in patch["properties"].items()
                                                     if shape.get("readOnly")),
                             "read": {"operation": "visuals", "payload": {"id": "<spec id>"}},
                             "token": "specs[0].spec_revision"},
            "note": "Example values are illustrative, not project evidence."}


_OWNER_TEMPLATES = {"visual_create": visual_create_template}


def owner_template(operation: str, *, compact: bool = False) -> dict:
    """An owner-derived authoring template for help, refusals and context, or {} (no hand-written fallback)."""
    builder = _OWNER_TEMPLATES.get(operation)
    return builder(payloads=not compact) if builder else {}


def _admit_visual_create(payload: Mapping[str, Any]) -> None:
    """Refuse an incomplete visual brief once, completely, against the renderer the caller chose.

    The generic admission reports the nearest branch of the five-way union, so a brief naming kind "artifact"
    with one stray top-level field was told that plot's source_data was missing, and a brief without kind
    learned one required field per attempt. This selects the variant by the declared discriminator (spec.kind,
    or expected_revision for a same-ID edit), names every missing or unsupported field and carries the
    validator-derived template. Canonical guard tokens and every valid brief fall through unchanged to the
    generic admission.
    """
    from jsonschema import Draft202012Validator
    if not isinstance(payload, Mapping) or payload.get("expected"):
        return
    spec = payload.get("spec")
    update = "expected_revision" in payload
    if update and not isinstance(payload.get("expected_revision"), str):
        refused = PayloadAdmissionError("visual_create",
            "Payload rejected at expected_revision: it is only for a same-ID edit and must be the exact "
            "spec_revision string from visuals; omit it to create a new visual.")
        refused.template = visual_create_template()
        raise refused
    table = variants("visual_create")
    kind = spec.get("kind") if isinstance(spec, Mapping) else None
    name = "update" if update else kind
    if not isinstance(spec, Mapping) or not isinstance(name, str) or name not in table:
        kinds = ", ".join(sorted(key for key in table if key != "update"))
        refused = PayloadAdmissionError("visual_create",
            "Payload rejected at spec.kind: a new visual names kind " + kinds + " (a same-ID edit supplies "
            "expected_revision instead); every new spec also needs id, title, question and caption plus that "
            "kind's fields. The returned template lists each kind's complete required fields and an example payload.")
        refused.template = visual_create_template()
        raise refused
    errors = list(Draft202012Validator(table[name]).iter_errors(dict(payload)))
    if not errors:
        return
    missing, unsupported, invalid = [], [], []
    for error in errors:
        where = ".".join(str(part) for part in error.absolute_path)
        prefix = where + "." if where else ""
        if error.validator == "required" and isinstance(error.instance, Mapping):
            missing.extend(prefix + str(field) for field in error.validator_value if field not in error.instance)
        elif error.validator == "additionalProperties" and isinstance(error.instance, Mapping):
            allowed = set(error.schema.get("properties") or {})
            unsupported.extend(prefix + str(field) for field in error.instance if field not in allowed)
        else:
            invalid.append((where or "payload") + ": " + error.message[:160])
    missing = sorted(dict.fromkeys(missing))
    unsupported = sorted(dict.fromkeys(unsupported))
    parts = (["missing " + ", ".join(missing[:16])] if missing else []) \
        + (["unsupported " + ", ".join(unsupported[:16])] if unsupported else []) \
        + (["invalid " + "; ".join(invalid[:6])] if invalid else [])
    label = "same-ID edit" if update else kind + " brief"
    refused = PayloadAdmissionError("visual_create",
        "Payload rejected at payload: this visual_create " + label + " is incomplete: " + "; ".join(parts)
        + ". The returned template is the current renderer validator's complete field set for this kind.")
    refused.template = visual_create_template(None if update else kind)
    refused.missing, refused.unsupported = missing, unsupported
    raise refused


def variants(operation: str) -> dict[str, dict]:
    declaration = DECLARATIONS.get(operation)
    if declaration is None or not declaration.variants:
        return {}
    return {name: _identity_input_schema(operation, name, schema)
            for name, schema in _VARIANTS[declaration.variants]().items()}


def supported_suboperation(operation: str, payload: Mapping[str, Any]) -> dict:
    """Resolve only the declaration's discriminator, not arbitrary nested fields.

    Indexed variants and flat/union owner schemas are equally authoritative.
    A supported flat value need not be a separately addressable help variant.
    """
    declaration = DECLARATIONS[operation]
    table = variants(operation)
    discriminator = "action" if operation == "repository" else "operation"
    supplied = payload.get(discriminator)
    if operation == "visual_create":
        spec = payload.get("spec")
        supplied = ("update" if "expected_revision" in payload else spec.get("kind")) if isinstance(spec, Mapping) else None
    elif isinstance(supplied, Mapping):
        supplied = supplied.get("kind") if operation == "structure_change" else None

    def values(schema):
        field = schema.get("properties", {}).get(discriminator, {})
        result = set(field.get("enum", ()))
        if isinstance(field.get("const"), str):
            result.add(field["const"])
        # Only complete outer branches declare this operation's discriminator.
        for axis in ("anyOf", "oneOf"):
            for branch in schema.get(axis, ()):
                result.update(values(branch))
        return result

    choices = set(table) | values(declaration.payload)
    supported = isinstance(supplied, str) and supplied in choices
    return {"supplied": supplied, "supported": supported,
            "variant": supplied if supported and supplied in table else None,
            "choices": sorted(choices)}


def source_write_guidance() -> dict:
    """The source read and operating help share the native edit recipe."""
    return {**DECLARATIONS["apply_revision"].extras["source_write_recipe"],
            "write": {"operation": "apply_revision",
                      "payload": generated_example("apply_revision")}}


def _reject_caller_expected(operation: str, payload: Mapping[str, Any], *, header=False) -> None:
    declaration = DECLARATIONS.get(operation)
    if declaration is not None and not declaration.caller_expected and (header or "expected" in payload):
        raise PayloadAdmissionError(operation,
            "This operation uses recorded current-turn source reads, not caller expected tokens. "
            "Read source for the exact span, then apply_revision with edits[] containing "
            "file, line_start, line_end, before and after; omit expected. "
            "A fresh read does not rebase an existing proposal automatically.")


def _variant_routes(operation: str, variant: str):
    """Routes for this owner variant, preserving the route table's guard forms."""
    from laplace.native import verbs as writing_verbs
    routes = writing_verbs.routes_for(operation)
    selected = tuple(route for route in routes
                     if ("operation", variant) in route.selector)
    return selected or routes


def _identity_input_schema(operation: str, variant: str,
                           schema: Mapping[str, Any]) -> dict[str, Any]:
    """Expose an owner's already-supported canonical-token or legacy-guard choice."""
    return _owner_guard_schema(operation, schema, _variant_routes(operation, variant))


from laplace.core import admission  # noqa: E402  (here, so the declaration lines above keep their cited numbers)


class PayloadAdmissionError(admission.AdmissionRefused):
    """The native door's shape refusal (core.admission.AdmissionRefused): its response names help from this table."""

    def response(self) -> dict:
        help_operation = getattr(self,"help_operation",self.operation)
        help_read = {"operation":"help", "payload":({"operation":help_operation}
                     if help_operation in DECLARATIONS else {})}
        response = {"ok":False, "operation":self.operation, "error":str(self),
                    "refused":{"kind":"shape", "said":str(self), "homes":[],
                               "needed":{"help":help_read}}, "help":help_read}
        # An owner-derived authoring template (visual_create) travels with the refusal it explains.
        template = getattr(self, "template", None)
        if template:
            response["template"] = template
        for key in ("missing", "unsupported"):
            if getattr(self, key, None):
                response["refused"][key] = list(getattr(self, key))
        return response


def owner_input_schema(operation: str) -> dict:
    """One existing declaration/owner input, including proven guard alternatives."""
    if operation in {"authoring/proposals", "authoring/proposal-preview"}:
        from laplace.manuscript.proposal_navigation import contract
        return contract()
    if operation=='authoring/proposal-decision':
        from laplace.manuscript.reconciliation import decision_contract
        return decision_contract(project_required=False)
    if operation in HTTP_DECLARATIONS:
        return dict(HTTP_DECLARATIONS[operation].payload)
    declaration = DECLARATIONS.get(operation)
    if declaration is None:
        raise PayloadAdmissionError(operation, "Unknown project operation")
    table = variants(operation)
    if table:
        return {"anyOf":list(table.values())}
    return _owner_guard_schema(operation, declaration.payload)


def _owner_guard_schema(operation: str, schema: Mapping[str, Any], routes=None) -> dict:
    """Compose canonical guards at the outer owner object, never nested effects."""
    from laplace.native import verbs as writing_verbs
    from laplace.core import identity_doors
    routes = routes if routes is not None else writing_verbs.routes_for(operation)
    eligible = [route for route in routes if writing_verbs.owner_accepts_expected(route)]
    if not eligible:
        return dict(schema)
    digest_names = {name for route in eligible for name, _homes, form, _optional in route.guards
                    if form == "digest"}

    expected_choice = {"required":["expected"],"properties":{"expected":{"minItems":1}}}
    # THE NONEMPTY GUARD INVARIANT (D1, 2026-10-15): a legacy guard alternative admits a payload only when any
    # canonical `expected` it ALSO carries is nonempty. An empty canonical presence beside valid legacy guards is a
    # malformed guard, refused at admission before any owner read or write; absent `expected` with legacy guards and
    # nonempty canonical tokens are admitted exactly as before. (Null or non-array `expected` is refused by the
    # outer property, identity_doors.EXPECTED_FIELD.)
    def legacy_choice(item):
        return {**item, "required": list(item["required"]),
                "properties": {**(item.get("properties") or {}), "expected": {"minItems": 1}}}
    def guard_group(row):
        out = dict(row)
        choices = out.get("anyOf")
        if choices and all(item.get("required") and set(item["required"]) <= digest_names for item in choices):
            out["anyOf"] = [expected_choice, *[legacy_choice(item) for item in choices]]
        return out

    def outer(value):
        out = dict(value)
        # A top-level union contains complete owner objects (application forms,
        # profile bases). Never rewrite nested properties, items or effect text.
        if "properties" not in out:
            for axis in ("anyOf", "oneOf"):
                if axis in out: out[axis] = [outer(item) for item in out[axis]]
            return out
        out = guard_group(out)
        out["properties"] = {**out["properties"],"expected":out["properties"].get("expected",dict(identity_doors.EXPECTED_FIELD))}
        if "allOf" in out: out["allOf"] = [guard_group(item) for item in out["allOf"]]
        legacy = [name for name in out.get("required",[]) if name in digest_names]
        if legacy:
            out["required"] = [name for name in out["required"] if name not in legacy]
            out["allOf"] = [*out.get("allOf",[]), {"anyOf":[expected_choice, legacy_choice({"required": legacy})]}]
        return out
    return outer(schema)


def _admit_schema(operation: str, payload: Mapping[str, Any], schema: Mapping[str, Any]) -> None:
    admission.admit_literal_by(operation, payload, schema, refusal=PayloadAdmissionError)
    if operation == 'literature_import' and 'original' in payload:
        from laplace.research.literature import retained_import_validation, RetainedImportRejected
        rejected=retained_import_validation(payload)
        if rejected:raise RetainedImportRejected(rejected)
    if operation == "help":
        try: validate_help_request(payload)
        except ValueError as exc:
            refused=PayloadAdmissionError(operation,str(exc))
            if isinstance(payload.get("operation"),str) and payload['operation'] in DECLARATIONS:
                refused.help_operation=payload['operation']
            raise refused from exc
    if operation == "author_history" and payload.get("view") == "activity":
        from laplace.work.history import validate_activity_query
        try: validate_activity_query(payload)
        except ValueError as exc: raise PayloadAdmissionError(operation,str(exc)) from exc
    if operation == "structure" and payload.get("projection") == "guard":
        # the guard selector policy is refused with its read route, not with the union's nearest
        # branch error (Sol guard-selector-policy, 2026-10-14); the declared schema says the same
        from laplace.manuscript.reader_plan import guard_section_id
        try: guard_section_id(payload)
        except ValueError as exc: raise PayloadAdmissionError(operation,str(exc)) from exc
    if operation == "visual_create":
        _admit_visual_create(payload)
    admission.admit_shape(operation, payload, schema, refusal=PayloadAdmissionError)


def validate_owner_payload(operation: str, payload: Mapping[str, Any], *, project: str, requested_by: str = "") -> None:
    """Complete owner-call admission, before classification/baseline/owner work."""
    from laplace.native import verbs as writing_verbs
    value = admission.request_value(operation, payload, project=project, requested_by=requested_by, refusal=PayloadAdmissionError)
    _reject_caller_expected(operation, payload)
    schema = owner_input_schema(operation)
    admission.admit_attribution(operation, value, requested_by=requested_by, refusal=PayloadAdmissionError)
    _admit_schema(operation, value, schema)
    if operation in DECLARATIONS:
        route = writing_verbs.route_for_operation(operation, value)
        # The composed schema above already decided type and emptiness (the nonempty guard invariant);
        # nonempty tokens obey the one rule (identity_doors.expected_tokens) and this route's homes.
        if value.get("expected"):
            if route is None or not writing_verbs.owner_accepts_expected(route):
                raise PayloadAdmissionError(operation, "This owner does not accept canonical expected tokens")
            _admit_tokens(operation, value["expected"], route, value)


def _admit_tokens(operation, expected, route, value, *, header=False):
    from laplace.core import identity_doors
    # The one canonical presence rule (identity_doors.expected_tokens), shared with every HTTP/public guarded
    # entry. The OUTER Request header (`header=True`) may be empty: no header tokens.
    try: tokens = list(identity_doors.expected_tokens(expected, allow_empty=header))
    except ValueError as exc: raise PayloadAdmissionError(operation, str(exc)) from exc
    allowed = {home.rstrip("?") for _name, homes, _form, _optional in route.guards for home in homes.split("|")}
    if any(token.kind not in allowed for token in tokens):
        raise PayloadAdmissionError(operation, "expected contains a home not declared by this route")
    # Do not sort, deduplicate, retarget or inspect tokens. Owners compare exact
    # ordered scoped identities against current facts after shape admission.
    for name, homes, _form, optional in route.guards:
        if expected and not optional and name not in value and not any(token.kind in {home.rstrip("?") for home in homes.split("|")} for token in tokens):
            raise PayloadAdmissionError(operation, "Missing declared guard coverage for " + name)
    return tokens


def validate_request_payload(request, route, *, project: str) -> None:
    """Pure supplied values/selectors before any span/counter materialization."""
    from laplace.core import grammar
    from laplace.native import verbs as writing_verbs
    if not isinstance(request.by,str):
        raise PayloadAdmissionError(route.operation,"Requested attribution must be text")
    try: request.by.encode("utf-8")
    except UnicodeError as exc: raise PayloadAdmissionError(route.operation,"Requested attribution must be UTF-8 text",requested_by=request.by) from exc
    value = dict(request.payload)
    _reject_caller_expected(route.operation, value, header=bool(request.expected))
    if "project" in value and value["project"] != project:
        raise PayloadAdmissionError(route.operation,"Payload project conflicts with the bound project",requested_by=request.by)
    # Coverage is checked after carriers have been restored, so supplied guards
    # count without being materialized or replaced by guessed defaults.
    tokens = []
    # Existing codec restores selectors/carriers without reading physical bytes.
    try:
        _operation, value = writing_verbs.to_owner_call(request, route=route,
            preserve_expected=bool(request.expected) and writing_verbs.owner_accepts_expected(route),
            materialize=False)
    except ValueError as exc:
        raise PayloadAdmissionError(route.operation,str(exc),requested_by=request.by) from exc
    value = {key:item for key,item in value.items() if key != "project"}
    if request.by and value.get("by") and request.by != value["by"]:
        raise PayloadAdmissionError(route.operation,"Outer requested attribution conflicts with literal owner by",requested_by=request.by)
    tokens = _admit_tokens(route.operation, request.expected, route, value, header=True)
    if request.expected and not writing_verbs.owner_accepts_expected(route):
        scope_error = writing_verbs.expected_scope_error(request, route, project)
        if scope_error:
            raise PayloadAdmissionError(route.operation,scope_error,requested_by=request.by)
    deferred = set()
    for name, homes, form, _optional in route.guards:
        if name not in value and form in {"text","counter"} and any(token.kind in {home.rstrip("?") for home in homes.split("|")} for token in tokens):
            deferred.add(name)
    schema = owner_input_schema(route.operation)
    if deferred:
        def obligations(row):
            out = dict(row)
            if "required" in out: out["required"] = [name for name in out["required"] if name not in deferred]
            for axis in ("anyOf","oneOf","allOf"):
                if axis in out: out[axis] = [obligations(item) for item in out[axis]]
            return out
        schema = obligations(schema)
    try: _admit_schema(route.operation, value, schema)
    except PayloadAdmissionError as exc:
        exc.requested_by = request.by
        raise


def http_lossless_query(route: str, method: str) -> bool:
    """Declared transport opt-in; legacy routes retain their blank defaults."""
    policies = set()
    for declaration in HTTP_DECLARATIONS.values():
        if declaration.route != route or method not in declaration.methods:
            continue
        policy = declaration.extras.get("lossless_query", False)
        if not isinstance(policy, bool):
            raise ValueError("Invalid declared query policy for " + route)
        policies.add(policy)
    if len(policies) > 1:
        raise ValueError("Ambiguous declared query policy for " + route)
    return policies.pop() if policies else False


def help_http_contract() -> dict[str, Any]:
    """Help selectors from their native owner, plus explicit human binding."""
    value = json.loads(json.dumps(DECLARATIONS["help"].payload))
    binding = {"project": {"type": "string", "minLength": 1},
               "turn_id": {"type": "string", "minLength": 1},
               "mode": {"enum": ["work", "review", "revise", "discuss"]},
               # the help owner's declarations (areas, journeys, controls) need no role:
               # they are the workspace's own description, not an operation's contract
               "view": {"enum": list(HELP_OWNER_CONCEPTS)}}
    value["properties"].update(binding)
    value.pop("required", None)
    for axis in value["oneOf"]:
        if "maxProperties" in axis:
            axis.clear()
            axis["propertyNames"] = {"enum": list(binding)}
        else:
            names = axis["propertyNames"]
            allowed = names.get("enum", [names.get("const")])
            axis["propertyNames"] = {"enum": allowed + list(binding)}
    value["allOf"] = [{"oneOf": [
        {"required": ["project", "turn_id"], "not": {"anyOf": [{"required": ["mode"]}, {"required": ["view"]}]}},
        {"required": ["project", "mode"], "not": {"anyOf": [{"required": ["turn_id"]}, {"required": ["view"]}]}},
        {"required": ["view"], "propertyNames": {"enum": ["project", "view"]}}]}]
    return value


def validate_help_request(payload: Mapping[str, Any]) -> None:
    """Validate one public help selector against the active help declaration.

    Draft 2020-12 reads the deployed declaration, rather than a second partial
    interpreter restating its keywords. Semantic names then resolve through the
    existing declaration and variant owners; no selector is accepted and ignored.
    """
    from jsonschema import Draft202012Validator

    schema = DECLARATIONS["help"].payload
    value = {key: item for key, item in payload.items() if key != "project"}
    errors = list(Draft202012Validator(schema).iter_errors(value))
    error = next((item for item in errors if item.validator == "dependentRequired"),
                 errors[0] if errors else None)
    if error is not None:
        detail = error.message
        if error.validator == "dependentRequired":
            for key, dependencies in error.validator_value.items():
                missing = [dependency for dependency in dependencies
                           if key in value and dependency not in value]
                if missing:
                    detail = "%s requires %s" % (key, ", ".join(missing))
                    break
        elif error.validator == "oneOf":
            detail = ("use one selector axis: bare, concept, operation with optional "
                      "variant, door, or route with optional method and http_operation")
        location = ".".join(str(part) for part in error.absolute_path) or "payload"
        raise ValueError("help selector rejected at %s: %s; selectors are never ignored"
                         % (location, detail))
    operation = value.get("operation")
    if operation is not None and operation not in DECLARATIONS:
        raise ValueError("Unknown operation; bare help lists deployed concepts and operations.")
    if "variant" in value:
        table = variants(str(operation))
        if value["variant"] not in table:
            raise ValueError("Unknown variant for %s; exact operation help lists variants."
                             % operation)
    if "context" in value:
        declaration = DECLARATIONS[str(operation)]
        schema = _selected_schema(declaration, value.get("variant"))
        fields = set(schema.get("properties") or {})
        for axis in ("oneOf", "anyOf"):
            for branch in schema.get(axis) or ():
                fields.update(branch.get("properties") or {})
        unknown = set(value["context"]) - fields
        if unknown:
            raise ValueError("help context fields do not belong to this operation variant: "
                             + ", ".join(sorted(unknown)))
        start, end = value["context"].get("line_start"), value["context"].get("line_end")
        if start is not None and end is not None and start > end:
            raise ValueError("help context line_start must not exceed line_end")


def protocol(operation: str) -> Any:
    declaration = DECLARATIONS.get(operation)
    if declaration is None or not declaration.protocol:
        return None
    module_name, func = _PROTOCOLS[declaration.protocol]
    import importlib
    return getattr(importlib.import_module(module_name), func)()


# ---------------------------------------------------------------------------
# Live tokens.  `expected` is not described; it is minted, here, from the homes
# the declaration names, through grammar.identity --- the ONE minting function.
# ---------------------------------------------------------------------------
_WITHIN_KEYS = ("path", "file", "source_file", "node", "section_id", "id", "key", "stage",
                "spec_id", "result_id", "run_id", "citekey", "files", "line_start", "line_end")


def _within(payload: Mapping[str, Any] | None) -> str:
    if not payload:
        return ""
    for key in _WITHIN_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, list) and value and isinstance(value[0], str):
            return value[0]
    block = payload.get("block")
    if isinstance(block, Mapping) and isinstance(block.get("file"), str):
        return str(block["file"])
    return ""


def expected_tokens(operation: str, *, project: str = "", root: Path | str | None = None,
                    payload: Mapping[str, Any] | None = None, variant: str | None = None) -> list[dict[str, Any]]:
    """One row per home this door guards: the live token, or what would obtain it.

    A row is the whole answer to "what do I put in this field": the home, the name
    the door asks for it under, the read that serves it, and --- when this project
    and payload are enough to resolve the home --- the token itself, minted by
    `grammar.identity`.  Nothing is recomputed here and no digest is invented: a
    recipe-O home carries the owner's own published string.
    """
    declaration = DECLARATIONS.get(operation)
    if declaration is None:
        return []
    asked: dict[str, list[str]] = {}
    for rule in declaration.rules:
        if rule.kind == "identity" and rule.home:
            names = asked.setdefault(rule.home, [])
            if rule.field not in names:            # one name per home per door, not three
                names.append(rule.field)
    rows: list[dict[str, Any]] = []
    from laplace.native import verbs as writing_verbs
    routes = (_variant_routes(operation, variant) if variant else
              (writing_verbs.route_for_operation(operation, payload or {}),))
    routes = tuple(route for route in routes if route is not None)
    allowed = ({home.rstrip('?') for route in routes for _name, homes, _form, _optional in route.guards
                for home in homes.split('|')} if routes else None)
    within = _within(payload)
    for raw in declaration.homes:
        optional = raw.endswith("?")
        kind_name = raw.rstrip("?")
        if allowed is not None and kind_name not in allowed:
            continue
        kind = g.HOME_KINDS[kind_name]
        row: dict[str, Any] = {"home_kind": kind_name, "optional": optional,
                              "asked_for_as": asked.get(kind_name, []),
                              "read": read_call(kind.read)}
        home_id = ""
        if kind.id_is == "project":
            home_id = project
        elif kind.id_is.startswith("project + ") and within:
            home_id = "%s::%s" % (project, within)
        if home_id and project:
            row["home"] = "%s:%s" % (kind_name, home_id)
            try:
                row["token"] = str(g.identity(g.Home(kind_name, home_id), project=project,
                                              root=Path(root) if root else None))
            except NotImplementedError as exc:
                row["token"] = None
                row["closes"] = kind.closes or str(exc)
            except Exception as exc:                      # a home this project does not have
                row["token"] = None
                row["absent"] = "%s: %s" % (type(exc).__name__, str(exc)[:120])
        else:
            row["token"] = None
            row["needs"] = kind.id_is
        rows.append(row)
    return rows


def generated_example(operation: str, *, project: str = "", root: Path | str | None = None,
                      variant: str | None = None,
                      payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """A payload built from the schema's own required keys, with live tokens in the
    identity fields.  Nothing in it was typed by a person: the hand-written examples
    this replaces were 72 literals in writing_contracts.py, and two of them named
    objects that do not exist in any project ("REQUEST-example", "sha256:current")."""
    declaration = DECLARATIONS.get(operation)
    if declaration is None:
        return {}
    schema = _selected_schema(declaration, variant)
    # Build the selector/object shape without injecting an identity.  That shape selects
    # the route, whose existing guard form says whether the owner expects a digest or
    # content.  The previous generator mapped every canonical token to `asked_for_as` and
    # therefore put `rev:...` under legacy digest fields and even exact-content `before`.
    legacy_schema = _identity_example_branch(schema, canonical=False)
    seed = _example_from(legacy_schema, {}, declaration)
    from laplace.native import verbs as writing_verbs
    identity_context = {key: value for key, value in dict(payload or {}).items()
                        if key in _WITHIN_KEYS or key == "block"}
    fields = set(legacy_schema.get("properties") or {})
    for axis in ("oneOf", "anyOf"):
        for branch in legacy_schema.get(axis) or ():
            fields.update(branch.get("properties") or {})
    supplied = {key: value for key, value in identity_context.items() if key in fields}
    seed.update(supplied)
    route = writing_verbs.route_for_operation(operation, seed)
    context = {**seed, **identity_context}
    rows = expected_tokens(operation, project=project, root=root, payload=context, variant=variant)
    token_by_home = {row["home_kind"]: row.get("token") for row in rows
                     if row.get("token")}
    guards = route.guards if route is not None else ()

    required = [(name, homes, form) for name, homes, form, optional in guards
                if not optional]
    canonical = ("expected" in (schema.get("properties") or {})
                 and all(form == "digest" for _name, _homes, form in required))
    canonical_tokens = []
    for _name, homes, _form, _optional in guards:
        token = next((token_by_home.get(home.rstrip("?"))
                      for home in homes.split("|")
                      if token_by_home.get(home.rstrip("?"))), None)
        if token and token not in canonical_tokens:
            canonical_tokens.append(token)
    required_ready = all(any(token_by_home.get(home.rstrip("?"))
                             for home in homes.split("|"))
                         for _name, homes, _form in required)
    if canonical and required and required_ready:
        out = _example_from(_identity_example_branch(schema, canonical=True), {}, declaration)
        for name, _homes, form, _optional in guards:
            if form == "digest":
                out.pop(name, None)
        out.update(supplied)
        out["expected"] = canonical_tokens
        return out

    # A legacy digest field takes the digest published by its owner, never the complete
    # canonical token. Text/cursor/counter forms keep the content-shaped value generated
    # from the owner's schema. Route.guards is the one authority for that distinction.
    legacy_values = {}
    for name, homes, form, _optional in guards:
        if form in writing_verbs.CARRIERS:
            legacy_values[name] = "<%s>" % writing_verbs.CARRIERS[form]
            continue
        if form != "digest":
            continue
        token = next((token_by_home.get(home.rstrip("?"))
                      for home in homes.split("|")
                      if token_by_home.get(home.rstrip("?"))), None)
        if token:
            legacy_values[name] = g.parse(token).digest
        else:
            home = homes.split("|")[0].rstrip("?")
            legacy_values[name] = "<%s digest: read %s>" % (
                home, read_call(g.HOME_KINDS[home].read) or "the owner")
    out = _example_from(legacy_schema, legacy_values, declaration)
    out.update(supplied)
    return out


def _identity_example_branch(schema: Mapping[str, Any], *, canonical: bool) -> dict[str, Any]:
    """Select only the canonical or legacy identity branch when generating one example."""
    all_of = []
    found = False
    for row in schema.get("allOf") or ():
        choices = list(row.get("anyOf") or ())
        canonical_rows = [choice for choice in choices
                          if "expected" in (choice.get("required") or ())]
        if not canonical_rows:
            all_of.append(row)
            continue
        legacy_rows = [choice for choice in choices if choice not in canonical_rows]
        selected = canonical_rows if canonical else legacy_rows
        all_of.append({**row, "anyOf": selected or canonical_rows})
        found = True
    return {**schema, "allOf": all_of} if found else dict(schema)


def _selected_schema(declaration: Declaration, variant: str | None) -> Mapping[str, Any]:
    table = variants(declaration.operation)
    if table:
        if variant and variant in table:
            return table[variant]
        # One example selects one complete owner variant. A wrapper would hide that
        # variant's allOf obligations from identity-branch selection.
        return next(iter(table.values())) if not variant else table[sorted(table)[0]]
    schema = owner_input_schema(declaration.operation)
    if "properties" not in schema:
        for axis in ("anyOf","oneOf"):
            if schema.get(axis) and "properties" in schema[axis][0]:
                return schema[axis][0]  # One complete existing owner form per example.
    return schema


def _example_from(schema: Mapping[str, Any], tokens: Mapping[str, str],
                  declaration: Declaration) -> dict[str, Any]:
    """Fill a schema's obligations: `required`, the first branch of a choice, and the
    first option of each `anyOf` group.

    A choice does not REPLACE the enclosing object's requirements, it adds to them.  The
    first version of this took `oneOf[0]` and returned it alone, which produced
    `{"spec": {"tikz": "<tikz>"}}` for `visual_create tikz` --- missing the five keys the
    spec itself requires --- and the validation test over all 73 operations and every
    variant is what caught it.  So the branches are MERGED into the enclosing object.
    """
    if not isinstance(schema, Mapping):
        return {}
    required: list[str] = list(schema.get("required") or ())
    properties: dict[str, Any] = dict(schema.get("properties") or {})
    for key in ("oneOf", "anyOf"):
        options = schema.get(key) or []
        if options:
            required += list(options[0].get("required") or ())
            properties.update(options[0].get("properties") or {})
    for branch in schema.get("allOf") or ():
        required += list(branch.get("required") or ())
        properties.update(branch.get("properties") or {})
        options = branch.get("anyOf") or []
        if options:
            # the owner's `requires_any`: one of these keys, not all of them
            required += list(options[0].get("required") or ())
            properties.update(options[0].get("properties") or {})
    out: dict[str, Any] = {}
    for name in dict.fromkeys(required):
        out[name] = _value_for(name, properties.get(name) or {}, tokens, declaration)
    if not out and properties:
        # A door whose obligation is "one of these fields" states it in a RULE, not in
        # `required`: `literature_import` requires nothing in its schema and refuses
        # without `doi` or `metadata` plus `provenance` (src/laplace/writing_tools.py:218).
        # An example built from `required` alone is `{}`, which helps nobody, so the
        # declaration's own `one-of` rules fill one branch. This is the typed rule paying
        # for itself: the obligation was unreachable while it was a sentence.
        for rule in declaration.rules:
            if rule.kind != "one-of":
                continue
            for name in rule.fields:
                if name in properties:
                    out[name] = _value_for(name, properties[name], tokens, declaration)
                    break
            if out:
                break
    # Conditional obligations remain part of examples too. Evaluate only the
    # declared outer conditions against the example constructed so far.
    from jsonschema import Draft202012Validator
    for branch in schema.get("allOf", ()):
        condition = branch.get("if")
        selected = branch if condition is None else branch.get(
            "then" if Draft202012Validator(condition).is_valid(out) else "else", {})
        if selected:
            required_part = _example_from({**selected, "properties": properties}, tokens, declaration)
            for name, value in required_part.items():
                out.setdefault(name, value)
    # A map with `minProperties` and a value schema (`source_guards: {<file>: digest}`)
    # owes at least one entry; an empty object cannot be sent.
    minimum = schema.get("minProperties") or 0
    extra = schema.get("additionalProperties")
    if len(out) < minimum and isinstance(extra, Mapping):
        for index in range(minimum - len(out)):
            key = "<%s %d>" % (declaration.operation if hasattr(declaration, "operation") else "key", index + 1)
            out[key] = _value_for(key, extra, tokens, declaration)
    return out


def _value_for(name: str, rule: Mapping[str, Any], tokens: Mapping[str, str],
               declaration: Declaration) -> Any:
    form=rule.get('x-laplace-value-form')
    if form in ('text','cursor'):
        return '<'+str(rule.get('description') or ('exact source text' if form=='text' else 'returned pagination cursor'))+'>'
    if name in tokens:
        return tokens[name]
    if rule.get("const") is not None:
        return rule["const"]
    if rule.get("enum"):
        return rule["enum"][0]
    for example in rule.get('examples') or []:
        if isinstance(example,(dict,list)):
            from jsonschema import Draft202012Validator
            if Draft202012Validator(rule).is_valid(example):
                return json.loads(json.dumps(example))
    kind = rule.get("type")
    if isinstance(kind, list):
        kind = kind[0]
    if kind in ("integer", "number"):
        return max(1, int(rule.get("minimum") or 1))
    if kind == "boolean":
        return True
    if kind == "array":
        item = rule.get("items") or {}
        # An item may itself be a choice --- `writing_style_calibration.sources` is
        # `oneOf: [string, {path, line_start, line_end}]` --- so the branch that carries
        # obligations is chosen, and a scalar item stays a scalar.  Taking the first
        # branch blindly produced `[{}]` for that one schema, which `minItems: 1` then
        # rejected.
        if item.get("required") or item.get("properties") or item.get("type") == "object":
            # the item carries its own obligations; `_example_from` merges any choice
            # branch INTO them (concept_change set_source requires `path` and then
            # offers label-or-line-range as a oneOf, and the first version lost `path`)
            return [_example_from(item, tokens, declaration)]
        branches = item.get("oneOf") or item.get("anyOf") or [item]
        chosen = next((branch for branch in branches
                       if branch.get("required") or branch.get("properties")
                       or branch.get("type") == "object"), branches[0])
        if chosen.get("required") or chosen.get("properties") or chosen.get("type") == "object":
            return [_example_from(chosen, tokens, declaration)]
        if rule.get("minItems"):
            return [_value_for(name, chosen, tokens, declaration)]
        return []
    if (kind == "object" or rule.get("properties") or rule.get("required")
            or rule.get("oneOf") or rule.get("anyOf")):
        return _example_from(rule, tokens, declaration)
    if form=='digest':
        home=rule.get('x-laplace-value-home')
        return '<%s digest: read %s>' % (home,read_call(g.HOME_KINDS[home].read) or 'the owner')
    if name in {'before','after_before'}:
        return '<owner value meaning unavailable; inspect the exact operation field description>'
    if name in g.GUARD_NAMES:
        homes = g.GUARD_NAMES[name]
        return "<%s digest: read %s>" % (
            homes[0], read_call(g.HOME_KINDS[homes[0]].read) or "the owner")
    return _placeholder(name, rule)


def _placeholder(name: str, rule: Mapping[str, Any]) -> str:
    """`<field>`, unless the schema constrains the string --- then a legal value.

    `visual_create`'s spec id is `^(?=.*[A-Za-z0-9])[A-Za-z0-9_-]+$`, which `<id>`
    violates.  A placeholder that cannot be sent is the hand-written example's defect in
    a new form, so the pattern decides the shape.
    """
    pattern = rule.get("pattern")
    for example in rule.get('examples') or []:
        if (isinstance(example, str) and len(example) >= (rule.get('minLength') or 0)
                and (not pattern or re.search(pattern, example))):
            return example
    candidate = "<%s>" % name
    if pattern:
        safe = re.sub(r"[^A-Za-z0-9_-]", "-", name) or "example"
        # Owner identity forms (digest, candidate, application, read receipt) have fixed
        # shapes; a legal-shaped zero value is sent, never a word that cannot pass.
        shaped = ("sha256:" + "0" * 64, "PROP-" + "0" * 32, "WA-" + "0" * 32, "DEC-" + "0" * 32,
                  "READ-" + "0" * 32, "BLD-" + "0" * 32, "ART-" + "0" * 32)
        candidate = next((value for value in (safe, "example", "example1", *shaped)
                          if re.search(pattern, value)), "example1")
    minimum = rule.get("minLength") or 0
    if len(candidate) < minimum:
        candidate = (candidate + "-" * minimum)[:max(minimum, len(candidate))]
    return candidate


# ---------------------------------------------------------------------------
# help, generated.
# ---------------------------------------------------------------------------
VARIANT_INDEX_LIMIT = 3          # above this, the index is served and one variant on request
# Three, not six: `repository` has five variants and served 8,187 characters of nested
# schema to a caller who had already chosen one of them, and `visual_create` served
# every renderer's spec. The measurement that sets this is context-economy.md finding 4 ---
# "There is no altitude between the required keys and everything" --- so the altitude is
# the variant index plus the route to one variant.


def contract_semantics(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Identity of a published operation, excluding its implementation coordinates.

    Help retains exact source locations for inspection. Moving a handler or a
    rule within a file does not change its input, authority, effect or recovery,
    and must not force a native conversation to migrate. Restrict removal to the
    declaration's own metadata positions; source-line fields in payload schemas
    and examples remain semantic data.
    """
    value = {key: item for key, item in payload.items() if key not in {
        "handler", "line_numbers", "rules_enforced_at", "implementation"}}
    if isinstance(value.get("rules"), list):
        value["rules"] = [{key: item for key, item in rule.items() if key != "enforced_at"}
                          for rule in value["rules"]]
    if isinstance(value.get("turn_bound"), Mapping):
        value["turn_bound"] = {key: item for key, item in value["turn_bound"].items()
                               if key != "enforced_at"}
    return value


# THE HELP SECTIONS (D2 help cost, 2026-10-15). Default help is what a caller needs to act: the operation, role
# permission, verb/concept/altitude, what it does and its effects, the selectors and required fields, the guard homes
# (`expected`, `rules`), the reads and cures (outputs, errors, recipes, navigation reads), an example and its native
# request. Measured help for the deployed operations had grown to 349,104 characters against the held 220,767 cap,
# almost all of it in reference material: protocol documents repeated byte for byte across operations, whole nested
# schemas of the largest doors, long act lists and long output lists. That material is now served on request by the
# SAME owner, exactly: `help {operation, section}` (variant optional for `input`) returns the full value this
# function used to inline. The default carries `sections` naming every moved value with its size and the one read
# that returns it. Nothing is truncated: `help_payload(..., full=True)` is the complete rendering (the operating
# brief's exact_actions digest is computed over it, so it is unchanged), and a section read returns the exact value.
#: reference documents, always served as sections
HELP_REFERENCE_SECTIONS = ("source_effect_protocol", "execution_protocol", "binding_contract", "reader_state_contract",
                           "raw_source_protocol", "historical_source_protocol", "response_wire",
                           "engineering_validation_schema", "plan_publication_contract", "code_mode_image_recipe",
                           "action_units", "examples")
#: sized values: inline up to the limit, else a summary inline and the exact value as a section. M5 (2026-10-16):
#: input 900 -> 600 moved ten 604-809-character schemas (source, literature_bind, logical_plan, read_artifact, ...)
#: to their summary (required fields, every field name, selector enums) plus the exact `input` section, 3,071
#: characters, which admits the Work review door under the held cap instead of raising it.
HELP_INLINE_LIMITS = {"input": 600, "acts": 600, "outputs": 500}
HELP_SECTIONS = HELP_REFERENCE_SECTIONS + tuple(HELP_INLINE_LIMITS)


def _help_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str))


def help_input_summary(schema: Any, depth: int = 0) -> Any:
    """The selectors and required fields of a schema, without its nested bodies: required names, every field
    with its type, the values of enum/const fields (selectors), the property names an alternative admits, and
    each oneOf/anyOf/allOf alternative summarised the same way."""
    if not isinstance(schema, dict):
        return "value"
    if "enum" in schema:
        return {"enum": list(schema["enum"])}
    if "const" in schema:
        return {"const": schema["const"]}
    out: dict[str, Any] = {}
    if schema.get("required"):
        out["required"] = list(schema["required"])
    if schema.get("type") == "object" or "properties" in schema:
        properties = schema.get("properties") or {}
        if depth < 2:
            out["fields"] = {name: (help_input_summary(item, depth + 1) if isinstance(item, dict) and ("enum" in item or "const" in item)
                                    else item.get("type") if isinstance(item, dict) and isinstance(item.get("type"), str) else "value")
                             for name, item in properties.items()}
        elif properties:
            out["fields"] = sorted(properties)
    names = schema.get("propertyNames")
    if isinstance(names, dict) and ("enum" in names or "const" in names):
        out["names"] = list(names["enum"]) if "enum" in names else [names["const"]]
    if schema.get("maxProperties") == 0:
        out["empty"] = True
    if schema.get("dependentRequired"):
        out["dependent_required"] = schema["dependentRequired"]
    for axis in ("oneOf", "anyOf", "allOf"):
        if axis in schema:
            out[axis] = [help_input_summary(item, depth + 1) for item in schema[axis]]
    if not out:
        kind = schema.get("type")
        return kind if isinstance(kind, str) else "value"
    return out


def _help_default(operation: str, value: dict[str, Any]) -> dict[str, Any]:
    """The served default of a full help rendering (see THE HELP SECTIONS)."""
    out, moved = dict(value), {}
    for key in HELP_REFERENCE_SECTIONS:
        if key in out:
            moved[key] = _help_size(out.pop(key))
    # an explicitly selected variant IS the exact request for its input: it is never summarised
    if "input" in out and not value.get("selected_variant") and _help_size(out["input"]) > HELP_INLINE_LIMITS["input"]:
        moved["input"] = _help_size(out["input"])
        out["input_summary"] = help_input_summary(out.pop("input"))
    for key, keep in (("acts", 3), ("outputs", 2)):
        if key in out and _help_size(out[key]) > HELP_INLINE_LIMITS[key]:
            moved[key] = _help_size(out[key])
            out[key] = list(out[key])[:keep]
            out[key + "_total"] = len(value[key])
    if moved:
        payload = {"operation": operation, "section": "<name>"}
        if value.get("selected_variant"):
            payload["variant"] = value["selected_variant"]
        out["sections"] = {"read": {"operation": "help", "payload": payload}, "chars": moved}
    return out


def help_section(operation: str, section: str, value: dict[str, Any]) -> dict[str, Any]:
    """One exact section of a full help rendering, or a refusal naming the sections this operation has."""
    available = [key for key in HELP_SECTIONS if key in value]
    if section not in HELP_SECTIONS or section not in value:
        raise ValueError("help %s has no section %r; its sections: %s" % (operation, section, ", ".join(available) or "none"))
    return {"operation": operation, "section": section,
            **({"variant": value["selected_variant"]} if value.get("selected_variant") else {}),
            "value": value[section], "chars": _help_size(value[section]),
            "default_read": {"operation": "help", "payload": {"operation": operation}}}


def help_payload(operation: str, *, permitted: bool, project: str = "",
                 root: Path | str | None = None, variant: str | None = None,
                 payload: Mapping[str, Any] | None = None,
                 with_tokens: bool = True, section: str | None = None,
                 full: bool = False) -> dict[str, Any]:
    """The served help for one operation: the default projection, one exact `section`, or (`full=True`) the
    complete rendering (THE HELP SECTIONS above)."""
    value = _help_full(operation, permitted=permitted, project=project, root=root, variant=variant,
                       payload=payload, with_tokens=with_tokens)
    if section is not None:
        return help_section(operation, section, value)
    return value if full else _help_default(operation, value)


def _help_full(operation: str, *, permitted: bool, project: str = "",
               root: Path | str | None = None, variant: str | None = None,
               payload: Mapping[str, Any] | None = None,
               with_tokens: bool = True) -> dict[str, Any]:
    """One bounded help response, rendered from the declaration.

    `expected` carries the live tokens of `project`.  A door with more variants than
    VARIANT_INDEX_LIMIT serves the index of its variants and the exact route to one
    of them, because "there is no altitude between the required keys and everything"
    was measured as 41,476 characters for one operation
    (evidence/WRITING_FRICTION_2026-10-01/wave1/context-economy.md, finding 4).
    """
    declaration = DECLARATIONS.get(operation)
    if declaration is None:
        raise ValueError("no declaration is deployed for %r; help lists the deployed "
                         "operations" % (operation,))
    table = variants(operation)
    if variant is not None and (not isinstance(variant, str) or not variant
                                or variant not in table):
        raise ValueError("unknown variant for %s; exact operation help lists variants"
                         % operation)
    value: dict[str, Any] = {
        "operation": operation,
        "permitted": permitted,
        "verb": declaration.verb,
        "concept": declaration.concept,
        "altitude": declaration.altitude,
        "does": declaration.does,
        "effects": list(declaration.effects),
        "handler": declaration.handler,
        # The one sentence a caller needs to read every `file:line` in this response: the
        # resolved ones are in THIS tree, the typed ones carry the commit they are in.
        "line_numbers": COORDINATE_LAW,
    }
    from laplace.projects import artifacts
    if operation in artifacts.OPERATION_OWNERS:
        value["implementation"] = artifacts.declaration_sites(
            "\n".join(_text(TOOL_DOOR)),
            "\n".join(_text("src/laplace/projects/artifacts.py")))[operation]["implementation"]
    # The acts, from the one table the dispatch routes on.  `also` used to be a hand-typed
    # list of extra pairs beside a hand-typed headline pair; this is the whole row set, with
    # the old spelling each act answers to, which door it is reachable through, and --- for
    # an act whose old spelling is a shim --- the expiry that retires it.  A caller told to
    # use an old spelling is owed the news that it is going away.
    from laplace.native import verbs as writing_verbs
    acts = writing_verbs.acts_for(operation)
    value["acts"] = acts
    primary = writing_verbs.PRIMARY_ACT.get(operation)
    if primary and primary[2] != "no-selector":
        # Published only where it is news: for most of the 73 the primary act is the route a
        # payload with no selector takes, which is what `verb`/`concept` above already say.
        value["act_chosen"] = primary[2]
    # `also` is NOT rendered beside `acts`: it is the same pairs, minus the old spelling and
    # the door, so two renderings of one fact in one response.  `acts` is the whole list.
    value.update(resolved_derived(declaration))
    value.update(resolved_derived(declaration,contract=True))
    if with_tokens and declaration.caller_expected:
        value["expected"] = expected_tokens(operation, project=project, root=root,
                                            payload=payload, variant=variant)
    if table and len(table) > VARIANT_INDEX_LIMIT and not variant:
        value["variants"] = {name: {"required": schema.get("required", []),
                                    "fields": sorted(schema.get("properties") or {})}
                             for name, schema in sorted(table.items())}
        value["read_one_variant"] = {"operation": "help",
                                     "payload": {"operation": operation,
                                                 "variant": "<name above>"}}
    elif table:
        if variant and variant in table:
            value["input"] = table[variant]
        elif len(table) == 1:
            # one variant is not a choice: `concept_tree` has exactly one and wrapping it
            # in a one-element oneOf made the schema differ from the owner's for no reason
            value["input"] = next(iter(table.values()))
        else:
            value["input"] = {"oneOf": [table[name] for name in sorted(table)]}
        if variant:
            value["selected_variant"] = variant
    else:
        value["input"] = owner_input_schema(operation)
    # An identity rule generated from the home list says the same thing as its `expected`
    # row --- field, home, read, line --- so it is rendered ONCE, as the `expected` row.
    # Identity rules that carry a clause of the old contract keep their clause and stay.
    carried = [rule for rule in declaration.rules
               if not (rule.kind == "identity" and len(rule.carries) > 1
                       and rule.carries[1] == "home")]
    if carried:
        # The enforcing line is the operation's own dispatch for most of its rules, so it
        # is stated once and a rule names a line only where it differs.  Repeating
        # `"enforced_at": "src/laplace/writing_tools.py:224"` on all 314 rules cost 12,196
        # characters for one fact per operation.
        doors = [rule.door for rule in carried if rule.door]
        # Equal-frequency ties follow declaration order, independent of process
        # hash seed. Compressing repeated sites must not change contract identity.
        default = max(dict.fromkeys(doors), key=doors.count) if doors else ""
        rendered_rules = []
        for rule in carried:
            row = rule.rendered()
            if default and row.get("enforced_at") == cited(default):
                row.pop("enforced_at")
            rendered_rules.append(row)
        value["rules"] = rendered_rules
        if default:
            value["rules_enforced_at"] = cited(default)
    if declaration.outputs:
        value["outputs"] = list(declaration.outputs)
    if declaration.recoverable:
        value["recoverable_errors"] = list(declaration.recoverable)
    if declaration.errors:
        value["errors"] = list(declaration.errors)
    for key, extra in (declaration.extras or {}).items():
        if key in declaration.derived or key in declaration.contract_derived:
            continue  # A declared producer owns the rendered value; extras is its base.
        # `next_steps`, `recovery`, `scope_rules`, `source_locator_recipe` --- four keys
        # the old table used for six operations.  They are carried under their own names
        # so no consumer loses them. Their historical migration segmentation stays
        # intact; authored text is accepted independently of its length.
        value[key] = list(extra) if isinstance(extra, tuple) else extra
    if declaration.turn_bound:
        value["turn_bound"] = {"required": True,
                               "enforced_at": cited(declaration.turn_door)}
    if declaration.header:
        value["header"] = {"required": declaration.header,
                           "enforced_at": cited(declaration.header_door)}
    if declaration.protocol:
        value["execution_protocol"] = protocol(operation)
    if operation == "help":
        from laplace.projects.writing_sources import response_wire_contract
        value["response_wire"] = response_wire_contract()
    if operation == "repository":
        from laplace.projects.writing_sources import CODE_MODE_IMAGE_GUIDANCE, CODE_MODE_IMAGE_RECIPE, operation_contract
        deployed = operation_contract()
        value["action_units"] = {name: row["units"]
                                 for name, row in deployed["operations"].items()}
        value["dependency_identity"] = deployed["dependency_identity"]
        value["image_delivery"] = CODE_MODE_IMAGE_GUIDANCE
        value["code_mode_image_recipe"] = CODE_MODE_IMAGE_RECIPE
    published = owner_examples(operation)
    if published:
        value["examples"] = published
    template = owner_template(operation, compact=True)
    if template:
        value["template"] = template
    value["example"] = generated_example(operation, project=project, root=root,
                                         variant=variant, payload=payload)
    if with_tokens:
        value["native"] = writing_verbs.native_example(
            operation, value["example"], project=project, root=root)
    # The per-operation digest is NOT repeated here: the operating brief already carries
    # `exact_action_digests[operation]` (src/laplace/writing/operating.py) and the help
    # response carries the tool contract's own `digest`. Serving it a third time cost
    # 6,935 characters across the 73 for a value no caller compares inside a help reply.
    if operation in {"logical_plan", "logical_plan_change"} and project and root is not None:
        # truthful availability for this project (campaign bounded source reading, 2026-10-14);
        # `permitted` above is the role's permission and is unchanged
        from laplace.research import concepts as concepts_surface
        known = concepts_surface.logical_plan_availability(project, Path(root))
        if known and not known["available"]:
            value["project_availability"] = {key: known[key] for key in ("status", "reason", "logical_plan_owner", "manuscript", "supported_reads", "creates_a_plan")}
    return value


def exact_action_digests(operations=None) -> dict[str, str]:
    """{operation: digest of its declaration}, under the name the system already uses.

    `writing_operating.tool_contract` has published `exact_action_digests` and
    `exact_actions_digest` since before this packet (base commit
    src/laplace/writing_operating.py:259-260).  A `declaration_digest` beside them would
    be a third and a fourth name for one value --- exactly the defect this lane exists to
    end --- and the holder census named both as new identity fields, which is how they
    were caught.
    """
    names = sorted(operations if operations is not None else DECLARATIONS)
    return {name: _one_digest(name) for name in names}


def _one_digest(operation: str) -> str:
    declaration = DECLARATIONS[operation]
    return digest({"operation": operation, "verb": declaration.verb,
                   "concept": declaration.concept, "homes": list(declaration.homes),
                   "payload": owner_input_schema(operation), "effects": list(declaration.effects),
                   "rules": [rule.rendered() for rule in declaration.rules],
                   "outputs": list(declaration.outputs),
                   "recoverable_errors": list(declaration.recoverable),
                   "errors": list(declaration.errors),
                   "extras": {key: list(value) if isinstance(value, tuple) else value
                              for key, value in (declaration.extras or {}).items()},
                   "owner_examples": sorted(owner_examples(operation)),
                   **({"caller_expected": False} if not declaration.caller_expected else {}),
                   "turn_bound": declaration.turn_bound, "header": declaration.header,
                   "handler": declaration.handler, "does": declaration.does,
                   **({"contract_derived":resolved_derived(declaration,contract=True)} if declaration.contract_derived else {})})


def native_read_homes(project: str = "", concept: str = "") -> list[dict[str, Any]]:
    return native_homes(project,concept,verbs=('read',))


def native_homes(project: str = "", concept: str = "", *, verbs=('read','record','create')) -> list[dict[str, Any]]:
    """Only existing HTTP contracts the semantic dispatcher actually proves reachable.

    These are homes, not additional legacy operations. Child identities and exact
    current actions come from the collection owner's returned handles.
    """
    from laplace.native import verbs as writing_verbs
    import copy
    rows=[]
    for name,routes in sorted(writing_verbs.BY_OPERATION.items()):
        declaration=HTTP_DECLARATIONS.get(name)
        if declaration is None:continue
        if not any(route.door=="http" and route.verb in verbs
                   and (not concept or route.concept==concept) for route in routes):continue
        seed={} if all(route.verb=='read' for route in routes) else _example_from(declaration.payload,{},declaration)
        proof=writing_verbs.native_example(name,seed,project=project or "<project>")
        if not proof.get("available"):continue
        request=proof["native_request"]
        schema=copy.deepcopy(declaration.payload)
        if name in {'authoring/proposals','authoring/proposal-preview'}:
            from laplace.manuscript import proposal_navigation
            schema=proposal_navigation.contract()
        else:
            schema.get("properties",{}).pop("project",None)
            if "required" in schema:schema["required"]=[key for key in schema["required"] if key!="project"]
        rows.append({"verb":request["verb"],"concept":request["concept"],
                     "native_request":request,"payload":schema,"basis":declaration.does,
                     "owner_read":{"method":"GET" if request["verb"]=="read" else "POST","route":declaration.route,"operation":name},
                     **({"permission":copy.deepcopy(declaration.extras["generic_permission"])} if (declaration.extras or {}).get("generic_permission") else {})})
    return rows


# ---- THE HELP OWNER'S AREAS, JOURNEYS AND CONTROLS (G8, plan §7) -----------------------------
#
# One declaration set, three readers: the native `help` operation (`help {concept: areas |
# journeys | controls}`), the HTTP `/authoring/help?project=&view=areas` read, and the
# workspace help layer / task guide. The guide used to carry a hand-authored copy of the
# welcome tour (`GUIDE_STEPS` in workspace-guide.mjs) — a second statement of the same
# tutorial truth that drifted from the controls it named; it is retired, and the guide now
# renders the `welcome` journey from this owner.
#
# AN AREA is one view of the workspace: what it is for at a glance, its state chips, its
# shortcuts and the journeys that start there. A JOURNEY is an ordered task of steps; a
# step names the CONTROL it points at and the observation FACT that proves it done, in a
# closed predicate language (`equals`, `not_equals`, `truthy`, `all`) over the facts the
# shell observes (`workspace-guide.observeWorkspace`): the guide never clicks and never
# fakes a state. A CONTROL is a declared control family rendered with `data-control="<id>"`;
# `rendered` says whether the shell renders that attribute today — the per-view coverage
# test that fails on drift is the whole-M5 requirement (D2), this registry is its source.
#
# BOUNDS AND INVALIDATION. The declarations are code: `help_areas()` renders them in O(size)
# with no file read, the payload is bounded by the declaration (the workspace
# aggregate-content ceiling is 32 KiB), and `version` is the digest of the three tables, so a consumer that
# cached the payload for its session compares that one string to know whether to re-read.
HELP_AREAS_SCHEMA = "laplace.help-areas/1"
HELP_OWNER_CONCEPTS = ("areas", "journeys", "controls", "diagrams", "checklist", "guides")
from laplace.native.help_guides import GUIDE_DECLARATIONS
OBSERVATION_FACTS = ("view", "outline", "returnVisible", "historyOpen", "workSelected",
                     "sessionOpen", "inspectorOpen", "templateOpen", "researchFocus",
                     "researchRepresentation", "researchFocal", "researchReading", "researchInputs", "reviewPanel")

CONTROL_DECLARATIONS: dict[str, dict[str, Any]] = {
    "nav:skip": {"label": "Skip to content", "view": "shell", "kind": "navigation", "rendered": True,
                 "renders_in": "project shell and global application entry; tests/human_workspace_shell.test.mjs"},
    "task:trail": {"label": "What led here", "view": "work", "kind": "navigation", "rendered": True,
                   "renders_in": "selected Task header or dialog with an issued provenance_read; tests/task_trail.test.mjs"},
    "writing:sources": {"label": "Sources beside writing", "view": "manuscript", "kind": "toggle", "rendered": True,
                        "renders_in": "ready native Writing host toolbar; tests/human_workspace_shell.test.mjs"},
    "help:read-guide": {"label": "Read a guide", "view": "shell", "kind": "navigation", "rendered": True, "renders_in": "workspace-help.mjs guide selection"},
    "tasks:add-open": {"label": "Add task", "view": "work", "kind": "disclosure", "rendered": True, "renders_in": "workspace-work-view.mjs existing task creator"},
    "tasks:add": {"label": "Add task", "view": "work", "kind": "form", "rendered": True, "renders_in": "workspace-work-view.mjs existing task form"},
    **{f"workflow:{key}": {"label": label, "view": "workflows", "kind": "disclosure", "rendered": True, "renders_in": "workspace-workflow-editor.mjs"} for key, label in (("purpose", "Workflow purpose"), ("saved-read", "Read this saved version"), ("saved-close", "Close saved version"))},
    **{f"workflow:{key}": {"label": label, "view": "workflows", "kind": "navigation", "rendered": True, "renders_in": "workspace-workflow-editor.mjs, exact issued offers; tests/workflow_history_frontend.test.mjs"} for key, label in (("history", "Browse saved versions"), ("history-next", "Older saved versions"), ("saved-next", "Read next saved-body part"), ("saved-workspace", "Open this saved version in Workspace"))},
    **{f"workflow:{key}": {"label": label, "view": "workflows", "kind": "navigation", "rendered": True, "renders_in": "workspace-workflow-editor.mjs native progression; tests/workflow_operation_frontend.test.mjs"} for key,label in (("design","Design"),("runs","Runs"),("guide","Guide"))},
    "workflow:discard": {"label": "Discard unsaved edits", "view": "workflows", "kind": "action", "rendered": True, "renders_in": "workspace-workflow-editor.mjs Design local draft only; tests/workflow_operation_frontend.test.mjs"},
    "workflow:adapt": {"label": "Use as new draft…", "view": "workflows", "kind": "action", "rendered": True, "renders_in": "workspace-workflow-editor.mjs Design, verified saved selection through the existing ownership choice; tests/workflow_operation_frontend.test.mjs"},
    "workflow:lineage-prepare": {"label": "Prepare complete lineage export", "view": "workflows", "kind": "disclosure", "rendered": True, "renders_in": "workspace-workflow-editor.mjs actual permitted lineage descriptor; tests/workflow_history_frontend.test.mjs"},
    **{f"workflow:{key}": {"label": label, "view": "workflows", "kind": kind, "rendered": True, "renders_in": "workspace-workflow-operation.mjs from exact issued owner offers; tests/workflow_operation_frontend.test.mjs"} for key, label, kind in (
        ("preview", "Check execution", "action"), ("context-read", "Inspect declared context", "disclosure"), ("uses", "Read recorded uses", "disclosure"), ("river", "Read observed flow", "disclosure"),
        ("uses-more", "Read more", "navigation"), ("river-more", "Read more", "navigation"), ("river-read", "Read a recorded response, proposal, return or run", "navigation"), ("run-detail", "Open run detail", "disclosure"),
        ("app-run-uses", "Read recorded uses", "navigation"), ("app-run-river", "Read observed flow", "navigation"), ("app-run-reply", "Read step response", "navigation"))},
    # Wave 11 (run-view): an opened run is its drawing with each stage's marks, then the river of observed flow; every
    # control in that view, existing and new, carries one of these ids. "does" is the guide sentence for each.
    **{f"workflow:{key}": {"label": label, "view": "workflows", "kind": kind, "rendered": True, "does": does,
        "renders_in": "workspace-workflow-editor.mjs paintAppRuns (an opened run) and workspace-workflow-river.mjs; tests/workflow_river.test.mjs"} for key, label, kind, does in (
        ("run-return", "Return to workflow", "navigation", "Leaves the runs and returns to this workflow's design; nothing is stopped or changed."),
        ("run-refresh", "Refresh status", "action", "Reads the selected run again from the workflow owner; it changes nothing."),
        ("runs-back", "Back to runs", "navigation", "Returns to the list of this saved version's agent runs."),
        ("run-step", "A step of this run", "navigation", "Opens this step's one card in the river: its state, times, provider and model, and its recorded result, conversation and exact data; nothing is sent."),
        ("run-session", "Open its session", "navigation", "Opens the project page with this stage's session, where you can read it, write to it or stop its turn."),
        ("run-explain", "What is a step?", "disclosure", "Shows or hides two sentences explaining a step."),
        ("run-guide", "More in Guide", "navigation", "Opens this workflow's Guide view."),
        ("run-view", "Graph view or List view", "navigation", "Shows the run's stages as a free graph or as a list."),
        ("run-fit", "Fit workflow", "action", "Scales the run graph to fit its box."),
        ("run-center", "Center selected", "action", "Centres the run graph on the chosen stage."),
        ("run-start", "Prepare start message", "action", "Composes the owner's start message for this prepared run in its original conversation; you send it there."),
        ("run-parent", "Open original conversation", "navigation", "Opens the conversation in which this run was prepared."),
        ("run-preparation", "Preparation and launch", "disclosure", "Shows or hides which session and turn prepared and launched this run."),
        ("run-exact", "Show exact recorded data", "disclosure", "Shows or hides the exact recorded owner data this part of the run view was painted from."),
        ("run-step-result", "Read full public result and actions", "navigation", "Opens this step's saved public result and its actions in the saved-turn reader."),
        ("run-step-conversation", "Open step conversation", "navigation", "Opens this step's conversation, where you can send it a message or stop it."),
        ("run-continue", "Prepare review continuation message", "action", "Composes the owner's continuation message for a failed review; you send it in the conversation."),
        ("run-attempts", "Earlier attempts", "disclosure", "Shows or hides this step's earlier attempts."),
        ("run-earlier-result", "Read earlier public result", "navigation", "Opens an earlier attempt's saved public result."),
        ("run-typed-return", "Open exact typed return", "navigation", "Opens this step's typed return as the owner saved it."),
        ("run-retained-output", "Retained worker output", "navigation", "Opens a retained worker output this step reused."),
        ("river-mark", "A mark of the observed flow", "navigation", "Opens one card for this turn, tool call, reply or dependency, with the owner's reads for it; nothing is read until you choose one."),
        ("river-step", "A step's lane", "navigation", "Opens one card for this step: its state in words, provider and model, its times, and its recorded result, conversation and exact data."),
        ("river-follow", "Follow", "navigation", "Returns the river to now and keeps it there as new marks arrive; it shows how many arrived while you looked back."),
        ("river-waiting", "Waiting for you", "navigation", "Opens the first step where an owner field says the next act is yours."),
        ("river-identity", "Identity", "disclosure", "Shows or hides the exact session, turn and event ids and the raw owner state behind this card."),
        ("river-list", "List every mark", "disclosure", "Shows or hides every mark of the river as a line of text, in time order."),
        ("river-conversation", "Open conversation", "navigation", "Opens the project page with this step's session."),
        ("river-card-close", "Close", "navigation", "Closes the card; the river keeps its place."),
        ("river-reply-more", "Read more of it", "navigation", "Reads the next page of the opened reply through the owner's continuation."),
        ("runs-open", "Open agent run", "navigation", "Opens this run: its drawing with each stage's marks and the river of observed flow under it."))},
    # Wave 12 (design-view): screen 1, "Set up: draw the steps and routes". Every control the Design view paints carries
    # one of these ids (a repeated one names its step, setting, edge or part as data-control-owner); "does" is the guide
    # sentence for each, and for a route pattern it says exactly what the pattern inserts.
    **{f"workflow:{key}": {"label": label, "view": "workflows", "kind": kind, "rendered": True, "does": does,
        "renders_in": "workspace-workflow-editor.mjs Design (paintStageTools, paintPatterns, the selected step's column, paintPolicy) and an opened run's compact line; tests/workflow_design_patterns.test.mjs"} for key, label, kind, does in (
        ("overview", "All workflows", "navigation", "Returns to the list of saved workflows and templates; an unsaved draft stays in this tab."),
        ("topology", "The drawing", "region", "Shows the workflow's steps and the routes between them; in an opened run, each step with its marks."),
        ("explain", "What is a step, a role, a hand-over or a review loop?", "disclosure", "Shows or hides two sentences explaining this part of a workflow."),
        ("explain-guide", "More in Guide", "navigation", "Opens this workflow's Guide view."),
        ("save", "Save definition", "action", "Sends this draft to the workflow owner as a new saved version; saving starts no work."),
        ("stage", "A step on the drawing", "selection", "Chooses this step; the column beside the drawing then shows its role, its settings with where each value comes from, what it reads and its instructions."),
        ("stage-add", "Add step", "action", "Adds a builder step with no arrows to this draft and chooses it."),
        ("stage-insert", "Add a step after this one", "action", "Adds a builder step straight after the chosen one: what the chosen step passed forward now leaves from the new step, and the chosen step passes forward to it."),
        ("stage-earlier", "Move earlier", "action", "Swaps the chosen step with the one before it; every arrow keeps its place."),
        ("stage-later", "Move later", "action", "Swaps the chosen step with the one after it; every arrow keeps its place."),
        ("stage-remove", "Remove this step", "action", "Removes the chosen step from this draft; a step that passed forward to it now passes forward to the step after it. A route pattern is removed the same way, step by step."),
        ("pattern-review", "Add a review of this step", "action", "Inserts one reviewer step (role adversary, titled Review of the chosen step) straight after the chosen step, with a solid arrow from the chosen step to it and a dashed findings-back arrow from it to the chosen step; the reviewer sets no provider or model of its own. Offered only where the owner's execution check, asked about the draft it makes (its instructions still to be written), runs it; otherwise it is greyed with the owner's sentence beside it and pressing applies nothing. Reads Check first when that check cannot be read."),
        ("pattern-reciprocal", "Make these two review each other", "action", "Inserts a reviewer after each of two builder steps, the chosen one and the one paired with it (or a new copy of the chosen step), each with a solid arrow from its builder and a dashed findings-back arrow to it: four steps and four arrows in all. The reviewer of each builder takes the other builder's provider, model and effort. Offered only where the owner's execution check, asked about the draft it makes (its instructions still to be written), runs it; otherwise it is greyed with the owner's sentence beside it and pressing applies nothing. Reads Check first when that check cannot be read."),
        ("pattern-partner", "Paired with", "choice", "Chooses the step the reciprocal review pairs with the chosen one, or a new copy of the chosen step; the owner's execution check says whether the pair runs."),
        ("pattern-reads", "The synthesis reads", "choice", "Chooses a step whose result the synthesis reads; the choice is kept only on the screen until the synthesis is added."),
        ("pattern-synthesis", "Add a synthesis that reads these", "action", "Inserts one step titled Synthesis with the owner's synthesis role (written in the original conversation) and a dotted data-input arrow from each chosen step; it adds no other arrow. Offered only where the owner's execution check, asked about the draft it makes (its instructions still to be written), runs it; otherwise it is greyed with the owner's sentence beside it and pressing applies nothing. Reads Check first when that check cannot be read."),
        ("policy-edit", "Change these limits", "navigation", "Opens Workflow details and defaults, where this workflow's review rounds, time limit and advance setting are edited."),
        ("policy-advance", "When the next step starts", "choice", "Sets the workflow's one advance setting: review starts by itself after each response, or the next step waits for your decision."),
        ("compare", "Compare draft with current", "action", "Reads the current saved version beside this draft; nothing is saved."),
        ("reinspect", "Reinspect current", "action", "Reads the selected saved workflow again from its owner; the draft is kept."),
        ("prepare-external", "Prepare external run…", "disclosure", "Opens or closes the form that prepares the saved version for an external run; preparing starts nothing."),
        ("prepare-agent", "Prepare agent run…", "disclosure", "Opens or closes the form that prepares the saved version as an agent run in a project conversation."),
        ("agent-runs", "Agent runs", "navigation", "Shows the recorded agent runs of this saved version."),
        ("inspector-part", "Step, Settings, Connections or Instructions", "navigation", "Jumps to that part of the chosen step in the column."),
        ("stage-nest", "Nest inside", "choice", "Puts the chosen step inside a group step, or at the top level; a group passes on only declared settings."),
        ("stage-position", "Canvas position", "disclosure", "Shows or hides the buttons that nudge the step on the free graph."),
        ("stage-nudge", "Move left, up, down or right", "action", "Moves the chosen step 24 pixels on the free graph."),
        ("setting-step", "Set for this step", "choice", "Writes this step's own provider, model, effort or input policy; Inherit removes its value here, so a containing group or the workflow defaults decide."),
        ("setting-workflow", "Set for the whole workflow", "choice", "Writes the workflow defaults for provider, model, effort or input policy, read by every step that sets no value of its own."),
        ("setting-identity", "Identity", "disclosure", "Shows or hides the exact origin, lineage and boundary the settings owner returned for each of this step's settings."),
        ("relation-add", "Add relation", "form", "Adds an arrow of the chosen kind from the chosen step to the step named here."),
        ("design-view", "Graph view or List view", "navigation", "Shows the same steps as a free graph or as a list with their relations."),
        ("graph-mode", "Select / move, Connect or Nest", "choice", "Sets what a click or a drag on the free graph does."),
        ("graph-fit", "Fit workflow", "action", "Scales the free graph to fit its box."),
        ("graph-center", "Center selected", "action", "Centres the free graph on the chosen step."),
        ("graph-step", "A step on the free graph", "selection", "Chooses this step, or with Connect or Nest joins the chosen step to it."),
        ("list-step", "A step in the list", "selection", "Chooses this step."),
        ("step-list", "Step list", "disclosure", "Shows or hides the list of steps under the free graph."),
        ("relations", "Relations", "disclosure", "Shows or hides every arrow of this draft as a line with its Remove button."),
        ("relation-remove", "Remove relation", "action", "Removes this one arrow from the draft."),
        ("back", "Back to prior workflow", "navigation", "Returns to the workflow opened before this one."),
        ("purpose-edit", "Edit workflow purpose", "disclosure", "Shows or hides the field for this workflow's purpose."),
        ("purpose-full", "Full workflow purpose", "disclosure", "Shows or hides the whole purpose when it is longer than its first paragraph."),
        ("details", "Workflow details and defaults", "disclosure", "Shows or hides this workflow's review loop limits and human boundary."),
        ("lineage", "Share complete saved lineage", "disclosure", "Shows or hides how many saved versions this workflow has and the owner's export of them."),
        ("saved-history", "Saved history", "disclosure", "Shows or hides the recent saved versions of this workflow."),
        ("technical", "Technical details", "disclosure", "Shows or hides the exact owner scope, permissions, providers, version and draft record."),
        ("recover", "Reinspect exact request", "action", "Asks the owner what became of the original Save or Prepare request; nothing is resent."),
        ("acknowledge", "Acknowledge inspected attempt", "action", "Clears the answered Save or Prepare result from this view; the recorded effect stays."),
        ("prepare-submit", "Prepare selected steps", "action", "Prepares the chosen steps of the saved version for an external run; it starts nothing."),
        ("agent-prepare-submit", "Prepare in conversation", "action", "Composes the owner's preparation message for an agent run in the project conversation; you send it there."),
        ("inspect-manuscript", "Inspect selected manuscript", "navigation", "Opens the manuscript chosen as the run's target in the reader."),
        ("adopt-guard", "Keep draft and adopt compared guard", "action", "Keeps this draft and takes the compared current version as the version it will be saved over."),
        ("context-choice", "Also deliver", "choice", "Adds or removes one context choice the owner declares for this step, such as the result of a connected earlier step; it grants no permission."),
        ("handoff-target", "Hand the result to", "choice", "Names a later connected step that receives this step's result."),
        ("prepare-step", "A saved step to prepare", "choice", "Includes or leaves out this saved step in the preparation."),
        ("prepare-input", "A selected evidence input", "choice", "Includes or leaves out this inspected input in the agent run's preparation."),
        ("prepare-target", "Manuscript to revise", "choice", "Chooses the document or section the agent run is prepared to revise."))},
    # Wave 13 (lane-checks): screen 3's Lane and Checks, the Development section of the open session on the Sessions page.
    # Every control sends the request the development owner's status read offers (development_source.status offers).
    **{f"development:{key}": {"label": label, "view": "shell", "kind": kind, "rendered": True, "does": does,
        "renders_in": "workspace-development.mjs mountDevelopment, mounted by workspace-sessions.mjs paintDevelopment in the open session's pane; tests/workspace_development.test.mjs"} for key, label, kind, does in (
        ("read", "Read again", "action", "Reads the Work's development status again from the development owner; nothing changes."),
        ("cut-lane", "Cut a lane", "action", "Sends the owner's lane offer: a lean copy of the app source (src, tests, scripts, profiles) is cut at the serving checkout's commit, and this session is granted to read, write and check in it, never in the live tree."),
        ("discard-lane", "Discard the lane", "action", "First press asks again; Discard now sends the owner's discard offer: the lane grant is revoked and the lane folder, with anything in it that was not adopted, is removed."),
        ("keep-lane", "Keep the lane", "action", "Withdraws the pending Discard; nothing is sent."),
        ("run-check", "Run a check profile", "action", "Sends the owner's offer to run this fixed check profile in the lane's isolated sandbox, with the file names typed beside it when the profile takes them; the result lists the failing test names read from the runner's output."),
        ("check-targets", "Files for a check", "form", "The test or source files this check runs, separated by spaces; the owner refuses a name outside the profile's globs. Kept in this browser until it is cleared."),
        ("more-checks", "Show older checks", "navigation", "Reads the next page of checks through the owner's next_read."),
        ("failing-all", "Show all listed names", "disclosure", "Shows or hides every failing test name the owner listed for this check; the first eight are always shown."))},
    # Wave 13 (adopt): screen 3's cards Preview and Adopt beside the lane and checks. Preview is the adoption owner's read
    # (development_adoption.preview); Adopt sends exactly the request the preview's adopt offer carries.
    **{f"development:{key}": {"label": label, "view": "shell", "kind": kind, "rendered": True, "does": does,
        "renders_in": "workspace-development.mjs mountDevelopment paintPreview and paintAdopt, mounted by workspace-sessions.mjs paintDevelopment in the open session's pane; tests/workspace_development.test.mjs"} for key, label, kind, does in (
        ("adopt-preview", "Preview Adopt", "action", "Reads what Adopt would change in the live tree: the files (tool and profile files flagged), the checks and any newly failing tests against the live commit, the reviews that would no longer be current and the publication inputs the close re-reads; nothing changes."),
        ("adopt", "Adopt", "action", "First press asks again; Adopt now sends the preview's adopt offer: the lane diff is applied to the live tree and committed locally with a Work-Id trailer, the lane grant is revoked and the lane folder removed. Nothing is pushed. Refused, with the owner's sentence beside it, while a close or another development action holds its lock, the live tree moved or a check is newly failing."),
        ("adopt-cancel", "Not now", "action", "Withdraws the pending Adopt; nothing is sent."))},
    "workflow:withdraw": {"label": "Withdraw original request", "view": "workflows", "kind": "action", "rendered": True, "renders_in": "workspace-workflow-editor.mjs owner withdrawal offer of an uncertain original request; tests/workflow_operation_frontend.test.mjs"},
    **{f"workflow:{key}": {"label": label, "view": "workflows", "kind": "action", "rendered": True, "renders_in": "workspace-workflow-operation.mjs shared Stop, mounted by Runs Open run detail and research-workbench-run.mjs Plan & run; tests/workflow_operation_frontend.test.mjs"} for key, label in (("stop-run", "Stop this run"), ("stop-check", "Check original Stop request"), ("stop-resend", "Resend original Stop unchanged"))},
    **{f"review-evidence:{name}": {"label": label, "view": "review-evidence", "kind": "navigation", "rendered": True,
        "renders_in": "workspace-review-evidence.mjs openReviewEvidence and owner-issued deliberate read controls"}
       for name,label in (("read","Inspect review evidence"),("list","List obligations"),("inspect","Inspect evidence routes"),("phase","Read exact phase"))},
    "source:inspect": {"label":"Source inspector","view":"source-inspector","kind":"disclosure","rendered":True,"renders_in":"workspace-source-inspector.mjs openSourceInspector"},
    "backlog:historical": {"label":"Historical engine obligations","view":"historical-obligations","kind":"disclosure","rendered":True,"renders_in":"workspace-source-inspector.mjs openHistoricalObligations"},
    **{f"backlog:{name}": {"label":label,"view":"backlog","kind":kind,"rendered":True,"renders_in":"workspace-backlog.mjs"} for name,label,kind in (("catalogue","Whole Work catalogue","navigation"),("filters","Filter whole backlog","form"),("inspect","Inspect exact Work","selection"),("planning","Save Work planning","form"),("check","Check original planning save","action"))},
    **{f"research:{key}": {"label": label, "view": "research-workbench", "kind": kind, "rendered": True,
                           "renders_in": ("research-workbench-view.mjs " if key in ("object", "action") else "research-workbench.mjs ") + "owner-backed native workbench " + label}
       for key, label, kind in (("object", "Research object", "selection"), ("lens", "Project context (optional)", "selection"),
                                ("tab", "Object views", "navigation"), ("input", "Include inspected input", "action"),
                                ("action", "Available object action", "action"), ("back", "Back to previous object", "navigation"),
                                ("refresh", "Refresh workspace", "action"), ("help", "Help", "disclosure"))},
    **{f"research:{key}": {"label": label, "view": "research-workbench", "kind": "navigation", "rendered": True,
                           "renders_in": "research-geometry.mjs coordinated native working surface"}
       for key, label in (("representation", "Working surface"), ("timeline", "Recorded timeline"), ("inspect", "Open focused object"))},
    **{f"nav:{view}": {"label": label, "view": "shell", "kind": "navigation", "rendered": True,
                       "renders_in": "workspace.mjs nav button data-view=" + view}
       # the Dependencies view and the Conversations nav entry are retired (M5 C2): view=dependencies
       # opens Material at its shared bindings and view=turns opens the conversation library
       for view, label in (("backlog", "All tasks"), ("overview", "Home"), ("work", "Tasks"), ("material", "Sources"),
                           ("history", "Activity"), ("settings", "Settings"),
                           ("argument", "Argument & evidence"), ("reader-plan", "Reader plan"),
                           ("research", "Research"), ("manuscript", "Writing"),
                           ("review", "Review & notes"), ("presentation", "Figures & output"))},
    "nav:menu": {"label": "Menu", "view": "shell", "kind": "toggle", "rendered": True,
                 "renders_in": "workspace.mjs header [data-nav]; shown in the compact and drawer navigation layouts"},
    "workspace:menu": {"label": "Workspace", "view": "shell", "kind": "disclosure", "rendered": True,
                       "renders_in": "workspace.mjs header [data-workspace-menu]: Projects, Workspace activity, Workspace dependencies, System owners, App settings"},
    "manuscript:outline": {"label": "Document outline", "view": "manuscript", "kind": "disclosure", "rendered": True,
                           "renders_in": "workspace.mjs nav outline control"},
    "manuscript:focus": {"label": "Focus manuscript", "view": "manuscript", "kind": "toggle", "rendered": True,
                         "renders_in": "workspace.mjs header [data-focus]"},
    "context:return": {"label": "Back to place", "view": "shell", "kind": "navigation", "rendered": True,
                       "renders_in": "workspace.mjs header context group [data-return-reader]"},
    "context:work": {"label": "Selected Work chip", "view": "shell", "kind": "navigation", "rendered": True,
                     "renders_in": "workspace.mjs header context group [data-work-scope]"},
    "context:clear": {"label": "Clear selected Work", "view": "shell", "kind": "action", "rendered": True,
                      "renders_in": "workspace.mjs header context group [data-clear-task]"},
    "conversation:toggle": {"label": "Conversation", "view": "shell", "kind": "toggle", "rendered": True,
                            "renders_in": "workspace.mjs header [data-talk]"},
    "help:guide": {"label": "Help", "view": "shell", "kind": "toggle", "rendered": True,
                   "renders_in": "workspace.mjs header [data-guide]"},
    # C4-C6 (M5, 2026-10-14): the Work, Activity and Reader-plan controls render their
    # data-control today; `renders_in` names the module whose source the coverage test reads
    "reader-plan:open-in-manuscript": {"label": "Open in manuscript", "view": "reader-plan", "kind": "action", "rendered": True,
                                       "renders_in": "workspace-spine.mjs objectHeader primary action"},
    "reader-plan:item": {"label": "Reader-plan item", "view": "reader-plan", "kind": "selection", "rendered": True,
                         "renders_in": "workspace-spine.mjs ordered plan row (orderedPlan control)"},
    "reader-plan:relation-map": {"label": "Relation map", "view": "reader-plan", "kind": "disclosure", "rendered": True,
                                 "renders_in": "workspace-spine.mjs lazy relation map (workspace-topology)"},
    "reader-plan:paragraph-action": {"label": "Paragraph plan action", "view": "reader-plan", "kind": "action", "rendered": True,
                                     "renders_in": "reader-state.mjs paragraph card actions (edit, move, remove) opened on a bounded subject read"},
    "reader-plan:guard": {"label": "Reader-plan guard subject", "view": "reader-plan", "kind": "disclosure", "rendered": True,
                          "renders_in": "reader-state.mjs read-only inspector of one saved/nested projection:guard subject (writing-artifact routes it; no reader-plan remount, no extra read)"},
    "history:entry": {"label": "Activity entry", "view": "history", "kind": "disclosure", "rendered": True,
                      "renders_in": "workspace-history.mjs timeline row"},
    "history:category": {"label": "Activity category", "view": "history", "kind": "selection", "rendered": True,
                         "renders_in": "workspace-history.mjs category select bound to the owner category filter (manuscript by default)"},
    "history:tab": {"label": "Changes or Graphs", "view": "history", "kind": "navigation", "rendered": True,
                    "renders_in": "workspace-history.mjs tab strip; Changes is the default, Graphs opens the analytics projections"},
    "history:open-target": {"label": "Open affected object", "view": "history", "kind": "action", "rendered": True,
                            "renders_in": "workspace-history.mjs record links (repo_file match or the record's saved text)"},
    "work:item": {"label": "Task item", "view": "work", "kind": "selection", "rendered": True,
                  "renders_in": "workspace-work-navigator.mjs Inspect control of a navigator row and workspace-work.mjs flat catalogue row; instances carry data-control-owner"},
    "work:next-step": {"label": "Next step", "view": "work", "kind": "action", "rendered": True,
                       "renders_in": "workspace-work.mjs blocker card primary action"},
    "work:prerequisites": {"label": "Prerequisites", "view": "work", "kind": "disclosure", "rendered": True,
                           "renders_in": "workspace-work-relations.mjs Needs panel: every authored dependency with its owner standing"},
    "work:neighbourhood": {"label": "Related tasks", "view": "work", "kind": "disclosure", "rendered": True,
                           "renders_in": "workspace-work.mjs lazy section; one paged graph read, drawn and listed by workspace-topology"},
    "work:disposition": {"label": "Record disposition", "view": "work", "kind": "disclosure", "rendered": True,
                         "renders_in": "workspace-work.mjs guarded disposition form"},
    "work:review": {"label": "Review lifecycle", "view": "work", "kind": "disclosure", "rendered": True,
                    "renders_in": "workspace-work-review.mjs review facet and its allowed phase recorder"},
    "work:review-setup": {"label": "Set up reviews", "view": "work", "kind": "action", "rendered": True,
                          "renders_in": "workspace-work-review.mjs Work review setup entry; also offered from passage comment Reviewers and limits"},
    # Eigen continuity (C actual mounted controls, ART-557c2c15): instances carry data-control-owner=project::workId; no passive heading carries one
    "work:continuity-continue": {"label": "Continue to the approved review", "view": "work", "kind": "action", "rendered": True,
                                 "renders_in": "selected Task continuity next action; only the owner-issued HTTP Continue at READY with its exact basis and current Task cut"},
    "work:continuity-proof": {"label": "Attach arrived proof", "view": "work", "kind": "action", "rendered": True,
                              "renders_in": "selected Task continuity next action; the owner-issued fillable proof template with its HTTP route and current Task cut"},
    "work:continuity-check": {"label": "Check the original outcome", "view": "work", "kind": "action", "rendered": True,
                              "renders_in": "selected Task continuity; a retained uncertain original wire, checked by the pure issued summary GET (not a POST or retry)"},
    "work:continuity-resend": {"label": "Resend the original request unchanged", "view": "work", "kind": "action", "rendered": True,
                               "renders_in": "selected Task continuity; the exact retained original wire after the owner check reads NONE (visible label names the request kind; never automatic)"},
    "work:continuity-review": {"label": "Open review form", "view": "work", "kind": "action", "rendered": True,
                               "renders_in": "selected Task continuity; opens the existing permitted review recorder for the owner-named phase"},
    "work:continuity-retry": {"label": "Read progress again", "view": "work", "kind": "action", "rendered": True,
                              "renders_in": "selected Task continuity; retries the failed progress summary GET"},
    "review:responses": {"label": "Request reviews / Review responses", "view": "review", "kind": "action", "rendered": True,
                         "renders_in": "workspace-review.mjs saved passage comment routing/results entry"},
    "topology:view": {"label": "Typed relationships", "view": "shared", "kind": "disclosure", "rendered": True,
                      "renders_in": "workspace-topology.mjs region; Work neighbourhood and reader-plan relation map instances"},
    "argument:record": {"label": "Argument object header", "view": "argument", "kind": "disclosure", "rendered": True,
                        "renders_in": "concept-reader.mjs object header (kind eyebrow, title, proof and formal chips)"},
    "conversation:context": {"label": "Inspect context", "view": "conversation", "kind": "disclosure", "rendered": True,
                             "renders_in": "workspace-session.mjs context door [data-context-open] (C10)"},
    "manuscript:document-setup": {"label": "Document setup", "view": "manuscript", "kind": "disclosure", "rendered": True,
                                  "renders_in": "manuscript-editor.mjs Document setup panel (object header, files as relation rows, Exact build basis)"},
    # C7-C9 (M5, 2026-10-14): manuscript band, template proof, output cards, conversation rows,
    # settings families, profile candidates, material rows, research rows render their control
    "manuscript:undo": {"label": "Undo", "view": "manuscript", "kind": "action", "rendered": True,
                        "renders_in": "manuscript-editor.mjs editor band (Write mode; walk undoEdit)"},
    "manuscript:redo": {"label": "Redo", "view": "manuscript", "kind": "action", "rendered": True,
                        "renders_in": "manuscript-editor.mjs editor band (Write mode; walk redoEdit)"},
    "manuscript:template-layout": {"label": "Template & layout", "view": "manuscript", "kind": "action", "rendered": True,
                                   "renders_in": "manuscript-editor.mjs Document setup primary action when the owner offers a template"},
    "template:proof": {"label": "Reviewed proof", "view": "manuscript", "kind": "disclosure", "rendered": True,
                       "renders_in": "document-template.mjs reviewed-proof row naming the build receipt and PDF that Apply binds"},
    "template:apply": {"label": "Apply reviewed preview", "view": "manuscript", "kind": "action", "rendered": True,
                       "renders_in": "document-template.mjs apply button, enabled only for the reviewed proof"},
    "output:document": {"label": "Manuscript PDF", "view": "presentation", "kind": "disclosure", "rendered": True,
                        "renders_in": "workspace-output.mjs Manuscript PDF card (object header, document chips, Build primary)"},
    "output:derived": {"label": "Derived output", "view": "presentation", "kind": "disclosure", "rendered": True,
                       "renders_in": "derived-output.mjs derived output card (object header with status chip)"},
    "conversation:turn": {"label": "Turn facets", "view": "conversation", "kind": "disclosure", "rendered": True,
                          "renders_in": "workspace-session.mjs thread row chips (saved changes, failed attempts, reply standing)"},
    "conversation:artifact": {"label": "Saved artifacts", "view": "conversation", "kind": "disclosure", "rendered": True,
                              "renders_in": "workspace-session.mjs relation rows of a turn's saved artifacts"},
    "conversation:target": {"label": "Message target", "view": "conversation", "kind": "disclosure", "rendered": True,
                            "renders_in": "workspace-session.mjs target chip row (target, attached reading, intent)"},
    "settings:family": {"label": "Settings family", "view": "settings", "kind": "disclosure", "rendered": True,
                        "renders_in": "workspace-app.mjs family head (scope chip and one sentence of effect)"},
    "settings:stage": {"label": "Writing stage", "view": "settings", "kind": "selection", "rendered": True,
                       "renders_in": "workspace-project.mjs ordered plan of writing stages (in-place guidance)"},
    "profile:candidate": {"label": "Preference suggestion", "view": "settings", "kind": "selection", "rendered": True,
                          "renders_in": "profile-preferences.mjs relation rows of saved suggestions (Compare before Apply)"},
    "material:add-document": {"label": "Add local document", "view": "material", "kind": "action", "rendered": True,
                              "renders_in": "workspace-material.mjs Add local document entry; opens the form without selecting or uploading a file"},
    "material:add-literature": {"label": "Add to Literature", "view": "material", "kind": "action", "rendered": True,
                                "renders_in": "workspace-material.mjs retained-original entry; also on intake and exact-source readers; opens explicit metadata form"},
    "conversation:next-message": {"label": "Model & settings", "view": "conversation", "kind": "disclosure", "rendered": True,
                                    "renders_in": "workspace-session.mjs selected-conversation next-message inspector; staged preferences and exact original request recovery"},
    "conversation:add-document": {"label": "Add local document", "view": "conversation", "kind": "action", "rendered": True,
                                  "renders_in": "workspace-session.mjs conversation Context toolbar; shares the Material document form"},
    "material:reader": {"label": "Project reader", "view": "material", "kind": "selection", "rendered": True,
                        "renders_in": "workspace-material.mjs relation rows of the project readers"},
    "material:file": {"label": "Recorded file", "view": "material", "kind": "region", "rendered": True,
                      "renders_in": "workspace-material.mjs recorded file card (availability chip, Read primary); a region, not a control: selecting a card has no owner meaning, its Read, Add to Literature and More are the controls"},
    "material:binding": {"label": "Shared material binding", "view": "material", "kind": "selection", "rendered": True,
                         "renders_in": "workspace-material.mjs shared material card (currentness chip)"},
    "research:result": {"label": "Research result", "view": "research", "kind": "selection", "rendered": True,
                        "renders_in": "writing-evidence.mjs result index row (currentness chip)"},
    # C10-C11 (M5, 2026-10-14): the help layer, the task cue, the topology fold and the paragraph expansion
    "help:layer": {"label": "Help for this view", "view": "shell", "kind": "disclosure", "rendered": True,
                   "renders_in": "workspace-help.mjs non-modal layer at the right edge of main (glance, tasks, how it works, states, shortcuts)"},
    "help:close": {"label": "Close help", "view": "shell", "kind": "action", "rendered": True,
                   "renders_in": "workspace-help.mjs layer head; Esc closes to the Help door"},
    "help:task": {"label": "Start a task tutorial", "view": "shell", "kind": "action", "rendered": True,
                  "renders_in": "workspace-help.mjs journey rows (the person's progress from laplace:learning)"},
    "help:diagram": {"label": "How it works", "view": "shell", "kind": "disclosure", "rendered": True,
                     "renders_in": "workspace-help.mjs lazy diagram (help concept diagrams, drawn and listed by workspace-topology)"},
    "help:cue": {"label": "Task cue", "view": "shell", "kind": "disclosure", "rendered": True,
                 "renders_in": "workspace-guide.mjs anchored cue card beside the step's control (Back, Next or Skip, Stop)"},
    "topology:fold": {"label": "Wide level fold", "view": "shared", "kind": "toggle", "rendered": True,
                      "renders_in": "workspace-topology.mjs fold card (exact count) and the toolbar Unfold all / Fold wide levels"},
    "reader-plan:paragraph-expand": {"label": "Read whole paragraph plan", "view": "reader-plan", "kind": "action", "rendered": True,
                                     "renders_in": "reader-state.mjs display row door (shortened or omitted fields); one owner row_read with that paragraph_id, read only"},
    "reader-plan:transition-expand": {"label": "Read full reader transition", "view": "reader-plan", "kind": "action", "rendered": True,
                                      "renders_in": "reader-state.mjs reader-transition door when the display shortened its text; one owner values_read, read only"},
    "reader-plan:unit-select": {"label": "Planned unit", "view": "reader-plan", "kind": "toggle", "rendered": True,
                                "renders_in": "reader-state.mjs unit row; opens one unit"},
    "reader-plan:acknowledge-inputs": {"label": "Record inspected inputs", "view": "reader-plan", "kind": "action", "rendered": True,
                                       "renders_in": "reader-state.mjs Inputs and open points; one guard read, then a metadata-only observation (not review)"},
    # WAVE 11 CENSUS REPAIRS (2026-11-06): the controls this packet changed that carried no declared id
    "conversation:send": {"label": "Send", "view": "conversation", "kind": "action", "rendered": True,
                          "renders_in": "workspace-session.mjs composer Send; with nothing typed it says 'Write a message first.' beside Send and sends nothing (workspace-sessions.mjs refuseEmptySend)"},
    "sessions:send": {"label": "Send", "view": "shell", "kind": "action", "rendered": True,
                      "renders_in": "workspace-sessions.mjs open-session pane on the Sessions page (app=activity); the same empty-message behaviour as the conversation panel; tests/workspace_sessions.test.mjs"},
    "research:conversation": {"label": "Object conversation", "view": "research-workbench", "kind": "disclosure", "rendered": True,
                              "renders_in": "research-geometry.mjs Explore toolbar: shows the dock section where an opened object's conversation appears after Discuss"},
    "research:save-view": {"label": "Save presentation view", "view": "research-workbench", "kind": "action", "rendered": True,
                           "renders_in": "research-geometry.mjs Saved presentation views; says beside it why nothing was saved"},
    "research:open-view": {"label": "Open saved view", "view": "research-workbench", "kind": "action", "rendered": True,
                           "renders_in": "research-geometry.mjs Saved presentation views; says beside it why nothing was opened"},
    "work:step-waits-on": {"label": "Read what this step waits on", "view": "work", "kind": "navigation", "rendered": True,
                           "renders_in": "workspace-work-review.mjs continuity Next; the task's own issued detail read, its blockers said beside it with the time"},
    "work:containment-save": {"label": "Save containing work", "view": "work", "kind": "action", "rendered": True,
                              "renders_in": "workspace-work.mjs Change containing work; unchanged it says 'Nothing changed' beside Save and sends nothing; after a recorded save the redrawn card says when, and which task now contains this one, from the owner's detail read"},
    "work:attempt": {"label": "Last save attempt", "view": "work", "kind": "region", "rendered": True,
                     "renders_in": "workspace-work.mjs Edit authored work; the work port's last save attempt for this task (its status, attribution and the revision it was written against), not a control"},
    "work:compare": {"label": "Draft and current work", "view": "work", "kind": "region", "rendered": True,
                     "renders_in": "workspace-work.mjs Edit authored work after Compare with the current work; the port's comparison of the draft with the current owner read, with Use the displayed current work as my basis"},
    "work:result": {"label": "Open the result", "view": "work", "kind": "action", "rendered": True,
                    "renders_in": "workspace-work.mjs Next of a completed task with one recorded comment route; checks the route, build and document with their owners, then opens the PDF"},
    "settings:save-defaults": {"label": "Save future defaults", "view": "settings", "kind": "action", "rendered": True,
                               "renders_in": "workspace-project.mjs Settings, New conversation defaults, after Change future defaults is opened; issues POST /work/session-preferences with the chosen provider, model and effort; after a recorded save it says the values the owner recorded (or that they were already saved), after NOT_ADMITTED that the save was not recorded and the choices are kept, and with no known outcome it says so and reads the saved defaults again"},
    # ---- wave 13 id sweep: declarations (begin) ----
    **{key: {"label": label, "view": "shell", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-frame.mjs the top bar; tests/workspace_frame.test.mjs (every page, with or without a project)"} for key, label, kind, does in (
        ("frame:menu", "Menu", "navigation", "Opens the workspace places as a list on a narrow window; inside a project it shows or hides the project's own navigation. Nothing is changed."),
        ("frame:switch", "Switch project", "disclosure", "Opens the project switcher: the projects you opened most recently first, with a search. Nothing is changed until you choose one."),
        ("frame:more", "More", "disclosure", "Lists the four rarer workspace pages: Explore across projects, Workspace dependencies, System owners and App settings."),)},
    **{key: {"label": label, "view": "shell", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-frame.mjs the top bar; tests/workspace_frame.test.mjs place links (Now, Sessions, All tasks, Workflows, Projects)"} for key, label, kind, does in (
        ("frame:place", "Workspace place", "navigation", "Goes to that workspace page: Now, Sessions, All tasks, Workflows or Projects. The place's name is the link's text; nothing is changed."),)},
    **{key: {"label": label, "view": "shell", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-frame.mjs the top bar; tests/workspace_frame.test.mjs the narrow menu's place links and Help (listed in the project navigation inside a project)"} for key, label, kind, does in (
        ("frame:menu-place", "Workspace place (menu)", "navigation", "Goes to that workspace page from the narrow menu: a place, or one of More's four pages."),)},
    **{key: {"label": label, "view": "shell", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-frame.mjs the top bar; tests/workspace_frame.test.mjs the narrow menu's Help (listed in the project navigation inside a project)"} for key, label, kind, does in (
        ("frame:menu-help", "Help (menu)", "action", "Opens help for the page you are on, from the narrow menu."),)},
    **{key: {"label": label, "view": "shell", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-frame.mjs the top bar; tests/workspace_frame.test.mjs More's list, opened"} for key, label, kind, does in (
        ("frame:more-page", "More page", "navigation", "Goes to one of More's pages: Explore across projects, Workspace dependencies, System owners or App settings."),)},
    **{key: {"label": label, "view": "shell", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-frame.mjs the top bar; tests/workspace_frame.test.mjs the project switcher panel, opened"} for key, label, kind, does in (
        ("frame:switch-all", "All projects", "navigation", "Goes to the Projects page, the full list of your projects and writing."),
        ("frame:switch-create", "Create a project", "navigation", "Goes to the Projects page with the create form open; nothing is created until you save there."),)},
    **{key: {"label": label, "view": "shell", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-frame.mjs the top bar; tests/workspace_frame.test.mjs the project switcher panel, opened and read"} for key, label, kind, does in (
        ("frame:switch-row", "Switch to this project", "navigation", "Opens that project on the same kind of page you are on (Writing only where it has a manuscript). Nothing is changed."),)},
    **{key: {"label": label, "view": "shell", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-frame.mjs the top bar; tests/workspace_frame.test.mjs Return to project (a workspace page opened from a project)"} for key, label, kind, does in (
        ("frame:return", "Return to project", "navigation", "Goes back to the project page this workspace page was opened from."),)},
    **{key: {"label": label, "view": "shell", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-chrome.mjs project navigation; tests/human_workspace_shell.test.mjs"} for key, label, kind, does in (
        ("nav:more-tools", "More project tools", "disclosure", "Shows the project's rarer pages: Review & notes, Activity, Settings, Argument & evidence, Reader plan and Figures & output."),)},
    **{key: {"label": label, "view": "now", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-now.mjs Now page; tests/workspace_control_coverage.test.mjs 'now/page'"} for key, label, kind, does in (
        ("now:all-sessions", "All sessions", "navigation", "Goes to the Sessions page, every session across the workspace."),
        ("now:all-tasks", "All tasks", "navigation", "Goes to the All tasks page, the Work catalogue across every project."),
        ("now:all-projects", "All projects", "navigation", "Goes to the Projects page."),
        ("now:open-all-tasks", "Open All tasks", "navigation", "Goes to the All tasks page for the completed tasks that were not listed here."),
        ("now:create-project", "Create a project", "navigation", "Goes to the Projects page with the create form open; nothing is created until you save there."),
        ("now:bring-manuscript", "Bring an existing manuscript", "navigation", "Goes to the Projects page with the existing-manuscript form open; nothing is read or copied until you choose a file there."),)},
    **{key: {"label": label, "view": "now", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-now.mjs Now page rows from the engine's live work, the Work catalogue and the projects library"} for key, label, kind, does in (
        ("now:open-running", "Open the running work", "navigation", "Opens the conversation, research page or project the engine reports this live work for; nothing is changed."),
        ("now:open-task", "Open task", "navigation", "Opens that task in its project, read-only until you change something there."),
        ("now:open-suggested-task", "Open the suggested task", "navigation", "Opens the task the Work catalogue suggests next to inspect."),
        ("now:project-writing", "Continue writing", "navigation", "Opens that project's Writing page."),
        ("now:project-tasks", "Project tasks", "navigation", "Opens that project's Tasks page."),
        ("now:project-open", "Open project", "navigation", "Opens that project's Home page."),)},
    **{key: {"label": label, "view": "history", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-history.mjs and history-telemetry.mjs Activity"} for key, label, kind, does in (
        ("history:actor", "Activity actor", "selection", "Narrows the timeline to the actor you choose; the timeline is read again with that filter."),)},
    **{key: {"label": label, "view": "work", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-work.mjs Tasks and the open task; tests/workspace_control_coverage.test.mjs 'work/catalogue' and 'work/panels-open'"} for key, label, kind, does in (
        ("work:close", "Close task", "navigation", "Closes the open task and returns to the task list; nothing is changed."),
        ("work:edit-open", "Edit title and completion condition", "action", "Opens the authored-work editor for this task's title and completion condition; nothing is saved until you save."),
        ("work:status-open", "Update task status", "action", "Opens the task-status form for this task; nothing is changed until you save there."),
        ("work:use-for-message", "Use for next message", "action", "Puts this task in your next conversation message as its subject; nothing is sent."),
        ("work:related-turns", "View related turns", "navigation", "Opens the recorded conversation turns that name this task; it only reads."),
        ("work:authored-open", "Edit authored work", "disclosure", "Shows the editor for the task's authored title and completion condition."),
        ("work:containment-open", "Change containing work", "disclosure", "Shows the form that moves this task under another task."),
        ("work:disposition-open", "Update task status", "disclosure", "Shows the form that records a new status for this task."),
        ("work:evidence-paths", "Advanced: exact evidence paths", "disclosure", "Shows the exact evidence paths the owner records for this task."),
        ("work:save-authored", "Save authored work", "action", "Records the title and completion condition you edited, against the revision you started from; if it changed meanwhile it is refused."),
        ("work:save-status", "Save task status", "action", "Records the task status you chose, with the reason, through the owner's own request."),)},
    **{key: {"label": label, "view": "work", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-work.mjs Tasks and the open task; tests/workspace_control_coverage.test.mjs 'work/catalogue' and 'work/panels-open'"} for key, label, kind, does in (
        ("work:nav-filter", "Task filter", "selection", "Narrows the task list to one group (needs attention, in progress, ready, awaiting review, waiting, closed) the owner counts."),)},
    **{key: {"label": label, "view": "research-workbench", "kind": kind, "rendered": True, "does": does, "renders_in": "research-workbench.mjs and research-geometry.mjs Explore across projects; tests/workspace_control_coverage.test.mjs 'research-workbench/workspace'"} for key, label, kind, does in (
        ("research:saved-view-choice", "Saved presentation view", "selection", "Chooses which saved presentation view Open saved view will restore."),
        ("research:overview", "Workspace overview", "navigation", "Returns the page to the whole workspace instead of the selected object; nothing is changed."),
        ("research:browse", "Browse workspace objects", "disclosure", "Shows the workspace's objects, filtered by the kinds the owner offers."),
        ("research:selected-inputs", "Selected inputs", "disclosure", "Shows the objects and source windows you included as inputs for the next question."),
        ("research:outline-toggle", "Show or hide the outline", "disclosure", "Shows or hides the relation outline beside the page; it changes only the layout."),
        ("research:inspector-toggle", "Show or hide the inspector", "disclosure", "Shows or hides the inspector beside the page; it changes only the layout."),
        ("research:orientation", "Orientation", "action", "Opens the help guide for this page so you can start a task tutorial."),
        ("research:saved-views", "Saved presentation views", "disclosure", "Shows the presentation views you saved and the name field for a new one."),
        ("research:panel-sizes", "Panel sizes", "disclosure", "Shows the width fields for the outline and the inspector."),)},
    **{key: {"label": label, "view": "backlog", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-backlog.mjs the All tasks page; tests/workspace_control_coverage.test.mjs 'wave 13: All tasks'"} for key, label, kind, does in (
        ("backlog:add-task-open", "Add task in a project", "disclosure", "Shows one link per registered project; each opens that project's Tasks page at its Add task form. Nothing is created here."),
        ("backlog:guide", "How task planning works", "disclosure", "Explains in a few lines what the catalogue shows, how search and filters read, and that planning changes no execution."),
        ("backlog:queue-active", "Unfinished tasks, not deferred", "navigation", "Reads the owner's unfinished-and-not-deferred queue and adopts its filters."),
        ("backlog:queue-all", "All tasks and closed records", "navigation", "Reads every recorded task, closed ones included, and adopts the owner's filters for it."),
        ("backlog:source-contracts", "Inspect Source contracts", "navigation", "Opens the Source inspector for the contracts the catalogue read lists; it only reads."),
        ("backlog:historical-open", "Historical engine records (separate from current tasks)", "disclosure", "Lists the engine's historical work orders and promises, kept apart from current tasks."),
        ("backlog:filter-options", "Status and planning filters", "disclosure", "Shows the owner's further filters: status, planning and the rest the catalogue read offers."),
        ("backlog:refresh", "Refresh catalogue", "action", "Reads the Work catalogue again with the filters now set; it changes nothing."),
        ("backlog:row-details", "Status, planning and owner details", "disclosure", "Shows the exact status, planning and owner fields the catalogue recorded for this task."),)},
    **{key: {"label": label, "view": "backlog", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-backlog.mjs the All tasks page; tests/workspace_control_coverage.test.mjs 'wave 13: All tasks'"} for key, label, kind, does in (
        ("backlog:suggested", "Suggested next to inspect", "navigation", "Opens the task the catalogue read suggests next, for inspection only."),)},
    **{key: {"label": label, "view": "backlog", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-backlog.mjs the All tasks page; tests/workspace_control_coverage.test.mjs 'wave 13: All tasks'"} for key, label, kind, does in (
        ("backlog:filter", "Catalogue filter", "selection", "Sets one of the owner's catalogue filters (search, namespace, lifecycle and the rest); Find Work then applies them."),)},
    **{key: {"label": label, "view": "backlog", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-backlog.mjs the All tasks page; tests/workspace_control_coverage.test.mjs 'wave 13: All tasks'"} for key, label, kind, does in (
        ("backlog:plan", "Plan this Work", "action", "Opens the planning form for this task from its owner-issued planning read; nothing is saved until you save there."),)},
    **{key: {"label": label, "view": "backlog", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-backlog.mjs the All tasks page; tests/workspace_control_coverage.test.mjs 'wave 13: All tasks'"} for key, label, kind, does in (
        ("backlog:more", "More Work", "navigation", "Reads the next page of the catalogue by the owner's own continuation handle."),)},
    **{key: {"label": label, "view": "backlog", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-backlog.mjs the All tasks page; tests/workspace_control_coverage.test.mjs 'wave 13: All tasks'"} for key, label, kind, does in (
        ("backlog:historical-records", "Historical engine records", "navigation", "Opens one of the engine's historical record lists beside the catalogue; it only reads."),)},
    **{key: {"label": label, "view": "backlog", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-backlog.mjs the All tasks page; tests/workspace_control_coverage.test.mjs 'wave 13: All tasks'"} for key, label, kind, does in (
        ("backlog:add-task-in", "Add a task in this project", "navigation", "Opens that project's Tasks page at its Add task form."),)},
    **{key: {"label": label, "view": "backlog", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-backlog.mjs the All tasks page; tests/workspace_control_coverage.test.mjs 'wave 13: All tasks'"} for key, label, kind, does in (
        ("backlog:add-task-create", "Create or open a project", "navigation", "Goes to the Projects page when no registered project exists to add a task in."),)},
    **{key: {"label": label, "view": "projects", "kind": kind, "rendered": True, "does": does, "renders_in": "project-work.mjs the Projects page; tests/workspace_control_coverage.test.mjs 'projects/page'"} for key, label, kind, does in (
        ("projects:task-write", "Start writing", "selection", "Chooses 'start writing': the list below then opens each project at its Writing page."),
        ("projects:task-source", "Read a source", "selection", "Chooses 'read a source': the list below then opens each project at its Sources page."),
        ("projects:task-tasks", "Organise tasks", "selection", "Chooses 'organise tasks': the list below then opens each project at its Tasks page."),
        ("projects:task-open", "Open existing project", "selection", "Chooses 'open an existing project': the list below then opens each project at its Home page."),
        ("projects:create-toggle", "Create a project", "disclosure", "Shows the form that creates a project; nothing is created until you press Create project."),
        ("projects:create", "Create project", "action", "Creates the project from the title, category, purpose and audience you typed, then opens it."),
        ("projects:find-existing", "Find existing manuscripts", "action", "Asks the project owner to list manuscripts it can register from this computer; it only reads."),
        ("projects:category", "Project category", "selection", "Chooses the kind of project to create: general, article, book, software, company, transcript or campaign."),)},
    **{key: {"label": label, "view": "owners", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-owners.mjs the System owners page; tests/workspace_control_coverage.test.mjs 'owners/page'"} for key, label, kind, does in (
        ("owners:find", "Find owners", "action", "Reads the owners that match the name or path you typed; it changes nothing."),)},
    **{key: {"label": label, "view": "owners", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-owners.mjs the System owners page; tests/workspace_control_coverage.test.mjs 'owners/page'"} for key, label, kind, does in (
        ("owners:read", "Read an owner page", "navigation", "Reads the owner page, explanation, input file or Work list that the owner itself offers here; the address it reads is the owner's own."),)},
    **{key: {"label": label, "view": "dependencies", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-app.mjs Workspace dependencies page; tests/workspace_control_coverage.test.mjs 'dependencies/page'"} for key, label, kind, does in (
        ("dependencies:filter", "Filter dependencies", "action", "Reads the recorded shared-material links again for the consumer project and search text you chose; it changes nothing."),
        ("dependencies:coverage", "Coverage and relation owners", "disclosure", "Shows which owners list these links and any project whose links could not be listed."),
        ("dependencies:refresh", "Refresh dependency index", "action", "Reads the recorded links again from the first page; it changes nothing."),
        ("dependencies:more", "More dependencies", "navigation", "Reads the next page of recorded links at the same registry revision."),
        ("dependencies:open-material", "Open project material and shared bindings", "navigation", "Opens the chosen consumer project's Sources page."),
        ("dependencies:consumer", "Consumer project", "selection", "Chooses which project's shared-material links are listed; Filter dependencies then reads them."),)},
    **{key: {"label": label, "view": "dependencies", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-app.mjs Workspace dependencies page; tests/workspace_control_coverage.test.mjs 'dependencies/page'"} for key, label, kind, does in (
        ("dependencies:inspect", "Inspect binding", "action", "Reads the exact stored owner of this binding and shows what it says now; it changes nothing."),
        ("dependencies:open-binding", "Open binding in project", "navigation", "Opens this binding on its consumer project's Sources page."),)},
    **{key: {"label": label, "view": "settings", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-app.mjs App settings page; tests/workspace_control_coverage.test.mjs 'settings/families'"} for key, label, kind, does in (
        ("settings:category-models", "Models & providers", "selection", "Shows the providers and models the catalogue reports, and the model policy they follow."),
        ("settings:category-voice", "Writing & voice", "selection", "Shows the shared writing voice profile and lets you edit it."),
        ("settings:category-architecture", "Structural preferences", "selection", "Shows saved structural-preference suggestions to compare."),
        ("settings:category-runtime", "Runtime", "selection", "Shows the runtime the app observed and the one it declares."),
        ("settings:category-storage", "Storage & recovery", "selection", "Shows what is stored and how it is recovered."),
        ("settings:refresh-providers", "Refresh provider availability", "action", "Asks each configured provider whether it is available now, then shows what they report."),
        ("settings:model-policy-source", "Model policy source", "disclosure", "Shows where the model policy is declared."),)},
    **{key: {"label": label, "view": "settings", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-app.mjs App settings page; tests/workspace_control_coverage.test.mjs 'settings/families'"} for key, label, kind, does in (
        ("settings:provider-models", "Reported models and exact state", "disclosure", "Shows the models this provider reports and its exact authentication state, as the catalogue gives them."),)},
    **{key: {"label": label, "view": "overview", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-home.mjs project Home; tests/workspace_control_coverage.test.mjs 'overview/ready'"} for key, label, kind, does in (
        ("home:continue-writing", "Continue writing", "navigation", "Opens the project's Writing page."),)},
    **{key: {"label": label, "view": "overview", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-home.mjs project Home; tests/workspace_control_coverage.test.mjs 'overview/ready'"} for key, label, kind, does in (
        ("home:writing-file-details", "Writing file details", "disclosure", "Shows the path of the writing file this project's manuscript is read from."),
        ("home:edit-argument", "Edit working argument", "disclosure", "Shows the working argument as editable text; nothing is saved until you press Save argument."),
        ("home:work-argument", "Work through the argument", "action", "Opens the conversation panel to work through this argument; nothing is sent."),
        ("home:argument-open", "Working argument", "disclosure", "Shows the working argument, whether read-only or to develop, with its editor."),
        ("home:edit-brief", "Edit purpose, reader and form", "disclosure", "Shows the purpose, audience and form as editable fields; nothing is saved until you press Save framing."),
        ("home:save-framing", "Save framing", "action", "Records the purpose, audience and form you edited as the project's framing."),
        ("home:save-argument", "Save argument", "action", "Records the working argument you edited, against the revision you started from; if it changed meanwhile, it is refused."),
        ("home:form", "Form", "selection", "Chooses the form of the work: book, article, report, briefing or custom; Save framing records it."),)},
    **{key: {"label": label, "view": "overview", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-home.mjs project Home; tests/workspace_control_coverage.test.mjs 'overview/ready'"} for key, label, kind, does in (
        ("home:open-tasks", "Open tasks", "navigation", "Opens the project's Tasks page."),
        ("home:open-questions", "Open questions", "navigation", "Opens the project's open questions in the argument structure."),
        ("home:all-activity", "All activity", "navigation", "Opens the project's Activity page with every recorded event."),
        ("home:open-conversation", "Open conversation", "action", "Opens the conversation panel for this project; nothing is sent."),
        ("home:guided-tour", "Take the guided tour", "action", "Opens the help guide for this page so you can start a task tutorial."),
        ("home:brief", "The brief", "disclosure", "Shows the project's central question, reader and form as recorded."),
        ("home:document-setup", "Manuscript selection and setup", "disclosure", "Shows which manuscript file the project reads and how its document is set up."),
        ("home:edit-title", "Edit project title", "action", "Shows the title field so you can rename the project; nothing is saved until you save there."),)},
    **{key: {"label": label, "view": "overview", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-home.mjs project Home; tests/workspace_control_coverage.test.mjs 'overview/ready'"} for key, label, kind, does in (
        ("home:read-event-record", "Read event record", "action", "Opens the exact recorded event in the inspector; it changes nothing."),)},
    **{key: {"label": label, "view": "overview", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-home.mjs project Home; tests/workspace_control_coverage.test.mjs 'overview/ready'"} for key, label, kind, does in (
        ("home:recent-open", "Open a recorded destination", "navigation", "Opens the file, section or conversation a recent event names; it changes nothing."),)},
    **{key: {"label": label, "view": "overview", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-home.mjs project Home; tests/workspace_control_coverage.test.mjs 'overview/ready'"} for key, label, kind, does in (
        ("home:event-details", "Event details", "disclosure", "Shows the recorded summary of this event."),)},
    **{key: {"label": label, "view": "settings", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-project.mjs project Settings; tests/workspace_control_coverage.test.mjs 'settings/project'"} for key, label, kind, does in (
        ("settings:refresh", "Refresh settings", "action", "Reads the project's settings and writing stages again; it changes nothing."),
        ("settings:edit-writing", "Edit writing settings", "action", "Opens the writing-style editor for this project; nothing is saved until you save there."),
        ("settings:future-defaults", "Change future defaults", "disclosure", "Shows the provider, model and effort new conversations start with, and lets you change them."),
        ("settings:identities", "Engine and profile identities", "disclosure", "Shows the exact engine and profile identities this project's tools run under."),)},
    **{key: {"label": label, "view": "settings", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-project.mjs project Settings; tests/workspace_control_coverage.test.mjs 'settings/project'"} for key, label, kind, does in (
        ("settings:inspect-history", "Inspect project history", "action", "Opens the project's history in the inspector; it only reads."),
        ("settings:stage-use", "Use in conversation", "action", "Prepares a request in the conversation panel from this writing stage's guidance; nothing is sent."),
        ("settings:stage-refresh", "Refresh stage", "action", "Reads this writing stage's guidance again; it changes nothing."),
        ("settings:profile-identities", "Exact profile identities and tool route", "disclosure", "Shows the exact profile identities and the tool route this stage uses."),)},
    **{key: {"label": label, "view": "settings", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-project.mjs project Settings; tests/workspace_control_coverage.test.mjs 'settings/project'"} for key, label, kind, does in (
        ("settings:default-select", "Default provider, model or effort", "selection", "Chooses the provider, model or effort new conversations start with; Save future defaults records them."),)},
    **{key: {"label": label, "view": "settings", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-material.mjs the storage panel of project Settings; tests/workspace_control_coverage.test.mjs 'settings/project'"} for key, label, kind, does in (
        ("settings:storage", "Storage and cleanup", "disclosure", "Shows how much space the project uses and which empty session folders could be removed."),)},
    **{key: {"label": label, "view": "settings", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-material.mjs the storage panel of project Settings; tests/workspace_control_coverage.test.mjs 'settings/project'"} for key, label, kind, does in (
        ("settings:storage-measure", "Re-measure storage", "action", "Measures the project's stored files again; it changes nothing."),)},
    **{key: {"label": label, "view": "material", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-material.mjs project Sources; tests/workspace_control_coverage.test.mjs 'material/files'"} for key, label, kind, does in (
        ("material:refresh-sources", "Refresh sources", "action", "Reads the project's recorded source files again; it changes nothing."),
        ("material:refresh-shared", "Refresh shared material", "action", "Reads the project's shared material links again; it changes nothing."),
        ("material:file-manage", "Manage", "disclosure", "Shows what you can do with this recorded file: inspect it, adopt a newer revision or remove its reference."),
        ("material:owner", "Material owner", "selection", "Chooses which source repository or project artifact owner the material you link comes from."),
        ("material:owner-type", "Material owner type", "selection", "Chooses whether the material you link is a source-repository file or a project artifact."),)},
    **{key: {"label": label, "view": "material", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-material.mjs project Sources; tests/workspace_control_coverage.test.mjs 'material/files'"} for key, label, kind, does in (
        ("material:file-more", "More", "disclosure", "Shows more actions and the exact identity of this recorded file."),
        ("material:link-options", "Link another source", "disclosure", "Shows the form that links another repository file or project artifact to this project."),
        ("material:readers", "Other project reading views", "disclosure", "Lists the other pages that read this project's material: Writing, Research, Review and Figures."),)},
    **{key: {"label": label, "view": "material", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-material.mjs project Sources; tests/workspace_control_coverage.test.mjs 'material/files'"} for key, label, kind, does in (
        ("material:prepare-reader", "Prepare text-only reader", "action", "Prepares a text-only reader for this source from its inspected revision; nothing is changed in the source."),)},
    **{key: {"label": label, "view": "material", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-material.mjs project Sources; tests/workspace_control_coverage.test.mjs 'material/files'"} for key, label, kind, does in (
        ("material:adopt", "Adopt inspected revision", "action", "Records this binding against the revision you just inspected, through the material owner's own request."),)},
    **{key: {"label": label, "view": "material", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-material.mjs project Sources; tests/workspace_control_coverage.test.mjs 'material/files'"} for key, label, kind, does in (
        ("material:remove-reference", "Remove reference", "action", "Removes this project's reference to the source; the source itself is not touched."),
        ("material:discuss", "Prepare a question about this file", "action", "Prepares a message about this file in the conversation panel; nothing is sent."),
        ("material:file-history", "Related file history", "action", "Opens the recorded history that names this file; it only reads."),)},
    **{key: {"label": label, "view": "material", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-material.mjs project Sources; tests/workspace_control_coverage.test.mjs 'material/files'"} for key, label, kind, does in (
        ("material:inspect", "Inspect material", "action", "Reads the material you described and shows what its owner says now; nothing is linked yet."),)},
    **{key: {"label": label, "view": "material", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-material.mjs project Sources; tests/workspace_control_coverage.test.mjs 'material/files'"} for key, label, kind, does in (
        ("material:link", "Link inspected revision", "action", "Links the inspected revision to this project through the material owner's request."),)},
    **{key: {"label": label, "view": "material", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-material.mjs project Sources; tests/workspace_control_coverage.test.mjs 'material/files'"} for key, label, kind, does in (
        ("material:read", "Read a recorded file", "action", "Opens this recorded file in the reader; it changes nothing."),)},
    **{key: {"label": label, "view": "material", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-material.mjs project Sources; tests/workspace_control_coverage.test.mjs 'material/files'"} for key, label, kind, does in (
        ("material:inspect-binding", "Inspect a shared binding", "action", "Reads the exact stored owner of this shared binding and shows what it says now; it changes nothing."),)},
    **{key: {"label": label, "view": "review", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-review.mjs Review and notes; tests/workspace_control_coverage.test.mjs 'review/pending'"} for key, label, kind, does in (
        ("review:refresh", "Refresh review", "action", "Reads the proposals and notes again; it changes nothing."),
        ("review:commission", "Commission a review", "action", "Prepares a message in the conversation panel asking for an independent review of the manuscript; nothing is sent."),)},
    **{key: {"label": label, "view": "review", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-review.mjs Review and notes; tests/workspace_control_coverage.test.mjs 'review/pending'"} for key, label, kind, does in (
        ("review:filter", "Review list", "selection", "Switches the list to comments, notes, global notes, other notes, closed items, proposals or proposal versions; it reads the owner's list for that choice."),)},
    **{key: {"label": label, "view": "research", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-research.mjs Research; tests/workspace_control_coverage.test.mjs 'research/results'"} for key, label, kind, does in (
        ("research:tab", "Research reader", "selection", "Switches Research to Numerics and results, Formal proof or Literature; nothing is changed."),)},
    **{key: {"label": label, "view": "research", "kind": kind, "rendered": True, "does": does, "renders_in": "writing-evidence.mjs Research evidence; tests/workspace_control_coverage.test.mjs 'research/results'"} for key, label, kind, does in (
        ("research:experiment-open", "Run or develop an experiment", "disclosure", "Shows the producers that can be run and the button that asks for a new experiment."),)},
    **{key: {"label": label, "view": "research", "kind": kind, "rendered": True, "does": does, "renders_in": "writing-evidence.mjs Research evidence; tests/workspace_control_coverage.test.mjs 'research/results'"} for key, label, kind, does in (
        ("research:develop-experiment", "Develop an experiment", "action", "Prepares a message in the conversation panel asking Eigen to help develop the numerics the argument needs; nothing is sent."),
        ("research:develop-visual", "Develop visual with Eigen", "action", "Prepares a message in the conversation panel asking Eigen to develop a figure for the manuscript; nothing is sent."),)},
    **{key: {"label": label, "view": "research", "kind": kind, "rendered": True, "does": does, "renders_in": "writing-evidence.mjs Research evidence; tests/workspace_control_coverage.test.mjs 'research/results'"} for key, label, kind, does in (
        ("research:figures-open", "Figures and diagrams", "disclosure", "Shows the figures and diagrams recorded for this project, to render, inspect or place one."),)},
    **{key: {"label": label, "view": "history", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-history.mjs Activity; tests/workspace_control_coverage.test.mjs 'history/timeline'"} for key, label, kind, does in (
        ("history:tab-changes", "Changes", "selection", "Shows the timeline of recorded changes; it is the page's current tab."),)},
    **{key: {"label": label, "view": "history", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-history.mjs Activity; tests/workspace_control_coverage.test.mjs 'history/timeline'"} for key, label, kind, does in (
        ("history:tab-graphs", "Graphs", "selection", "Replaces the timeline with the session analytics graphs for this project."),
        ("history:coverage", "What this history contains", "disclosure", "Lists which records this history draws on and what it cannot establish."),)},
    **{key: {"label": label, "view": "history", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-history.mjs Activity; tests/workspace_control_coverage.test.mjs 'history/timeline'"} for key, label, kind, does in (
        ("history:refresh", "Refresh history", "action", "Reads the project's recorded activity again from the first page; it changes nothing."),
        ("history:overview", "Show activity overview", "disclosure", "Shows the activity overview: who acted, when, and what was recorded."),)},
    **{key: {"label": label, "view": "presentation", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-output.mjs Figures and output; tests/workspace_control_coverage.test.mjs 'presentation/not-built'"} for key, label, kind, does in (
        ("output:build", "Build manuscript PDF", "action", "Builds the manuscript PDF from the document the owner describes; the owner's own build request is sent."),
        ("output:develop-figure", "Develop a figure", "action", "Prepares a message in the conversation panel asking Eigen to develop a figure for the argument; nothing is sent."),
        ("output:document-setup", "Open document setup", "navigation", "Opens Writing with Document setup, where the document's template and preamble are set."),)},
    **{key: {"label": label, "view": "presentation", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-output.mjs Figures and output; tests/workspace_control_coverage.test.mjs 'presentation/not-built'"} for key, label, kind, does in (
        ("output:build-details", "Build details", "disclosure", "Shows the build's reason, error and the last lines of its log."),)},
    **{key: {"label": label, "view": "presentation", "kind": kind, "rendered": True, "does": does, "renders_in": "derived-output.mjs derived output; tests/workspace_control_coverage.test.mjs 'presentation/not-built'"} for key, label, kind, does in (
        ("output:refresh-derived", "Refresh derived output", "action", "Reads the derived output's status again from its owner; it changes nothing."),)},
    **{key: {"label": label, "view": "reader-plan", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-spine.mjs Reader plan; tests/workspace_control_coverage.test.mjs 'reader-plan/selected'"} for key, label, kind, does in (
        ("reader-plan:refresh", "Refresh reader plan", "action", "Reads the reader plan again from its owner; it changes nothing."),)},
    **{key: {"label": label, "view": "reader-plan", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-spine.mjs Reader plan; tests/workspace_control_coverage.test.mjs 'reader-plan/selected'"} for key, label, kind, does in (
        ("reader-plan:create-item", "Create reader-plan item", "action", "Starts a new reader-plan item for the selected scope; nothing is recorded until you save."),)},
    **{key: {"label": label, "view": "work", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-work.mjs Tasks and the open task; tests/workspace_control_coverage.test.mjs 'work/catalogue' and 'work/panels-open'"} for key, label, kind, does in (
        ("work:flat-catalogue", "All task records and advanced namespace views", "disclosure", "Shows every recorded task of this project as one flat list, with the owner's advanced namespace views."),)},
    **{key: {"label": label, "view": "work", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-work.mjs Tasks and the open task; tests/workspace_control_coverage.test.mjs 'work/catalogue' and 'work/panels-open'"} for key, label, kind, does in (
        ("work:namespaces", "Existing work namespaces", "disclosure", "Lists the work namespaces that already exist, each with the read that opens it."),
        ("work:dev-workflows", "Recorded development workflows", "disclosure", "Lists the development workflows already recorded, each with the read that opens it."),)},
    **{key: {"label": label, "view": "work", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-work.mjs Tasks and the open task; tests/workspace_control_coverage.test.mjs 'work/catalogue' and 'work/panels-open'"} for key, label, kind, does in (
        ("work:progress-open", "Progress and next action", "action", "Scrolls to this task's progress and next action, as the owner reports them."),
        ("work:reinspect", "Reinspect this work", "action", "Reads this task again from its owner; it changes nothing."),
        ("work:completion-basis", "Completion basis", "disclosure", "Shows what the owner counts as this task's completion basis."),)},
    **{key: {"label": label, "view": "work", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-work.mjs Tasks and the open task; tests/workspace_control_coverage.test.mjs 'work/catalogue' and 'work/panels-open'"} for key, label, kind, does in (
        ("work:status-details", "Status details", "disclosure", "Shows the exact recorded lifecycle and current acceptance of this task."),)},
    **{key: {"label": label, "view": "work", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-work.mjs Tasks and the open task; tests/workspace_control_coverage.test.mjs 'work/catalogue' and 'work/panels-open'"} for key, label, kind, does in (
        ("work:open-parent", "Part of the containing task", "navigation", "Opens the task that contains this one."),)},
    **{key: {"label": label, "view": "work", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-work.mjs Tasks and the open task; tests/workspace_control_coverage.test.mjs 'work/catalogue' and 'work/panels-open'"} for key, label, kind, does in (
        ("work:status-choice", "Task status", "selection", "Chooses the status to record for this task; Save task status records it."),)},
    **{key: {"label": label, "view": "work", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-work-view.mjs the task creator; tests/workspace_control_coverage.test.mjs 'work/catalogue'"} for key, label, kind, does in (
        ("tasks:add-summary", "Add task", "disclosure", "Shows the form that adds a task to this project; nothing is added until you press Add task."),)},
    **{key: {"label": label, "view": "work", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-work-view.mjs the task creator; tests/workspace_control_coverage.test.mjs 'work/catalogue'"} for key, label, kind, does in (
        ("tasks:add-more", "Type, containing work and prerequisites", "disclosure", "Shows the task's type, the task that contains it and the tasks it waits on."),
        ("tasks:add-submit", "Add task", "action", "Adds the task you described to this project through the owner's request."),
        ("tasks:add-exact", "Add by exact id", "action", "Chooses the task whose exact id you typed as the containing or prerequisite task."),
        ("tasks:add-type", "Task type", "selection", "Chooses the new task's type: research, writing and the other kinds the owner offers."),
        ("tasks:add-prerequisites", "Prerequisites", "selection", "Chooses the tasks the new task waits on."),
        ("tasks:add-parent", "Containing work", "selection", "Chooses the task that will contain the new one, or the project root."),)},
    **{key: {"label": label, "view": "work", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-work-relations.mjs the relations panel of the open task; tests/workspace_control_coverage.test.mjs 'work/panels-open'"} for key, label, kind, does in (
        ("work:relation-open", "Open a related task", "navigation", "Opens that related task beside this one."),)},
    **{key: {"label": label, "view": "work", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-work-relations.mjs the relations panel of the open task; tests/workspace_control_coverage.test.mjs 'work/panels-open'"} for key, label, kind, does in (
        ("work:relation-tab", "Relations tab", "selection", "Shows the tasks this task needs, the tasks that need it or the tasks it contains; nothing is changed."),)},
    **{key: {"label": label, "view": "shared", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-topology.mjs the typed topology; tests/workspace_control_coverage.test.mjs 'shared/topology-plain'"} for key, label, kind, does in (
        ("topology:zoom-out", "Zoom out", "action", "Zooms the drawing out; it changes only the view."),
        ("topology:zoom-in", "Zoom in", "action", "Zooms the drawing in; it changes only the view."),
        ("topology:fit", "Fit to pane", "action", "Fits the whole drawing into the pane; it changes only the view."),)},
    **{key: {"label": label, "view": "shared", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-topology.mjs the typed topology; tests/workspace_control_coverage.test.mjs 'shared/topology-plain'"} for key, label, kind, does in (
        ("topology:node", "Select a node", "selection", "Selects that object in the drawing and opens it where the page shows the selection."),)},
    **{key: {"label": label, "view": "argument", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-argument.mjs and concept-explorer.mjs Argument and evidence; tests/workspace_control_coverage.test.mjs 'argument/panels-open'"} for key, label, kind, does in (
        ("argument:overview", "Overview", "navigation", "Shows the project's overview record: its purpose, reader and the argument's top objects."),
        ("argument:map", "Map project relationships", "action", "Draws the objects of the argument and what each requires, supports or is placed in; it changes nothing."),
        ("argument:reader-plan", "Reader plan", "navigation", "Opens the project's Reader plan page."),
        ("argument:add-object", "Add argument object", "action", "Opens the form that adds an argument object; nothing is recorded until you save there."),)},
    **{key: {"label": label, "view": "manuscript", "kind": kind, "rendered": True, "does": does, "renders_in": "manuscript-editor.mjs the Writing editor band; tests/workspace_control_coverage.test.mjs 'manuscript/write'"} for key, label, kind, does in (
        ("writing:mode-write", "Write", "selection", "Shows the manuscript for writing in the editor."),
        ("writing:mode-tex", "TeX", "selection", "Shows the manuscript's TeX source."),
        ("writing:tools", "Document tools", "disclosure", "Shows the secondary writing tools: setup, build details and file history."),)},
    **{key: {"label": label, "view": "manuscript", "kind": kind, "rendered": True, "does": does, "renders_in": "manuscript-editor.mjs the Writing editor band; tests/workspace_control_coverage.test.mjs 'manuscript/write'"} for key, label, kind, does in (
        ("writing:mode-pdf", "PDF", "selection", "Shows the built manuscript PDF."),)},
    **{key: {"label": label, "view": "manuscript", "kind": kind, "rendered": True, "does": does, "renders_in": "manuscript-editor.mjs the Writing editor band; tests/workspace_control_coverage.test.mjs 'manuscript/write'"} for key, label, kind, does in (
        ("writing:build", "Build PDF", "action", "Builds the manuscript PDF through the document owner's build request."),
        ("writing:build-details", "Build details", "action", "Opens Document setup at the last build's reason, error and log."),
        ("writing:file-history", "File history", "navigation", "Opens the recorded history of the manuscript's file."),
        ("writing:setup", "Document setup", "disclosure", "Shows the document's template, root file and preamble, and whether a template change is offered."),
        ("writing:build-log", "Build details", "disclosure", "Shows the build's reason, error and the last lines of its log, as the document owner reports them."),
        ("writing:build-basis", "Exact build basis", "disclosure", "Shows the exact root file and PDF state the build is made from."),
        ("writing:open-root", "Open root and preamble", "navigation", "Opens the manuscript's root file at its preamble in the TeX view."),)},
    **{key: {"label": label, "view": "history", "kind": kind, "rendered": True, "does": does, "renders_in": "history-telemetry.mjs Activity overview and tool telemetry; tests/workspace_control_coverage.test.mjs 'history/panels-open'"} for key, label, kind, does in (
        ("history:telemetry-limits", "Call-count coverage", "disclosure", "Shows what the recorded call counts cover and what they leave out."),
        ("history:overview-details", "Project activity, actors and recorded evidence", "disclosure", "Shows the activity by actor and by record kind for this project."),
        ("history:measurement-limits", "What these measurements cover", "disclosure", "Shows what these activity measurements cover and what they leave out."),)},
    **{key: {"label": label, "view": "history", "kind": kind, "rendered": True, "does": does, "renders_in": "history-telemetry.mjs Activity overview and tool telemetry; tests/workspace_control_coverage.test.mjs 'history/panels-open'"} for key, label, kind, does in (
        ("history:telemetry-filter", "Telemetry filter", "selection", "Narrows the activity to the bar, cell or time bucket you pressed, by the filter the owner issued for it."),)},
    **{key: {"label": label, "view": "history", "kind": kind, "rendered": True, "does": does, "renders_in": "history-telemetry.mjs Activity overview and tool telemetry; tests/workspace_control_coverage.test.mjs 'history/panels-open'"} for key, label, kind, does in (
        ("history:telemetry-select", "Telemetry scope", "selection", "Chooses the provider or other scope the call telemetry is shown for."),)},
    **{key: {"label": label, "view": "history", "kind": kind, "rendered": True, "does": does, "renders_in": "history-telemetry.mjs Activity overview and tool telemetry; tests/workspace_control_coverage.test.mjs 'history/panels-open'"} for key, label, kind, does in (
        ("history:tool-view", "Tool frequency view", "selection", "Chooses how tool frequency is drawn: histogram or rank on linear or logarithmic axes."),)},
    **{key: {"label": label, "view": "argument", "kind": kind, "rendered": True, "does": does, "renders_in": "concept-explorer.mjs Argument and evidence; tests/workspace_control_coverage.test.mjs 'argument/panels-open'"} for key, label, kind, does in (
        ("argument:find", "Find an object", "disclosure", "Shows a search box for a claim or concept by name."),
        ("argument:search", "Search", "action", "Searches the project's argument objects for the words you typed; it only reads."),
        ("argument:inventory", "Argument object inventory", "disclosure", "Lists every argument object of this project by kind."),
        ("argument:containment-all", "All objects & containment", "disclosure", "Lists every object with the place that contains it."),
        ("argument:containment-basis", "Containment basis", "disclosure", "Shows how the owner graded this object's containment."),
        ("argument:organise", "Organise parts", "disclosure", "Shows the controls that move or regroup this object's parts."),
        ("argument:uncontained", "Objects without a containing location", "disclosure", "Lists the objects the owner has not placed in any containing location."),
        ("argument:changes", "Changes and affected concepts", "disclosure", "Shows the recorded changes to this object and the concepts they affect."),
        ("argument:history-basis", "What this history can establish", "disclosure", "Shows what the change history can and cannot establish."),
        ("argument:add-part", "Add part", "action", "Opens the form that adds a part inside the open object; nothing is recorded until you save there."),
        ("argument:group", "Group parts", "action", "Opens the form that groups existing parts under a new object; nothing is recorded until you save there."),)},
    **{key: {"label": label, "view": "argument", "kind": kind, "rendered": True, "does": does, "renders_in": "concept-explorer.mjs Argument and evidence; tests/workspace_control_coverage.test.mjs 'argument/panels-open'"} for key, label, kind, does in (
        ("argument:move-part", "Move a part", "action", "Opens the chooser for this part's new containing location; nothing is moved until you confirm."),)},
    **{key: {"label": label, "view": "argument", "kind": kind, "rendered": True, "does": does, "renders_in": "concept-explorer.mjs Argument and evidence; tests/workspace_control_coverage.test.mjs 'argument/panels-open'"} for key, label, kind, does in (
        ("argument:object", "Open an argument object", "navigation", "Opens that object and the objects it contains."),)},
    # ---- second pass: controls that render only over richer owner answers, mounted from captured answers ----
    **{key: {"label": label, "view": "overview", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-home.mjs the Home next-task card, when the Work owner names a next ready task; tests/workspace_control_coverage.test.mjs 'overview/seeded'"} for key, label, kind, does in (
        ("home:open-next-task", "Open next task", "action", "Opens the task the Work owner names as the next ready one; nothing is changed."),)},
    **{key: {"label": label, "view": "work", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-work-navigator.mjs and workspace-work.mjs Tasks, the owner's task rows and pages; tests/workspace_control_coverage.test.mjs 'work/seeded'"} for key, label, kind, does in (
        ("work:subtasks", "View subtasks", "navigation", "Opens the subtasks of this task in place, read from the owner's page for it; nothing is changed."),
        ("work:more-tasks", "More tasks", "navigation", "Reads the next page of tasks from the owner's own continuation and adds the rows not already shown; nothing is changed."),
        ("work:more-work", "More work", "navigation", "Reads the next page of the whole task list from the owner's own continuation; nothing is changed."),
        ("work:namespace-read", "Read this exact work namespace", "navigation", "Reads one recorded work namespace or workflow exactly as the owner holds it and shows it; nothing is changed."),
        ("work:choose-evidence", "Choose saved evidence", "action", "Lists the saved evidence the owner offers for this task so some can be added to the status draft; nothing is saved until Save."),
        ("work:action-inspect", "Inspect an allowed action", "navigation", "Reads what the owner would do for one allowed action of this task and shows it; nothing is done."),
        ("work:action-template", "Owner-issued action template", "disclosure", "Shows the request template the owner issued for one action; it is shown and never sent from here."),
        ("work:history-read", "Show recorded history", "disclosure", "Reads the recorded history of this task from the owner and shows it; nothing is changed."),
        ("work:action-context", "Actions and context", "disclosure", "Shows the operations the owner lists for this task and whether each is permitted here, with how many tasks it needs, affects and contains; nothing is changed."),
        ("work:location-open", "Containing task", "navigation", "Opens a task that contains this one, from its place in the owner's containment path; nothing is changed."),
        ("work:location-deeper", "Open the deeper levels", "navigation", "Opens the levels of containment between the shown root and this task in the task list; nothing is changed."),
        ("work:progress-basis", "Exact progress basis and reads", "disclosure", "Shows the revisions and cuts the progress summary was built on, and the reads behind it; nothing is changed."),
        ("work:progress-read", "Read the progress records", "navigation", "Reads the review records or the task details behind the progress summary, as the owner issued them; nothing is changed."),)},
    **{key: {"label": label, "view": "argument", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-argument.mjs the working argument on Argument and evidence, when the project's framing carries an authored argument; tests/workspace_control_coverage.test.mjs 'argument/seeded'"} for key, label, kind, does in (
        ("argument:read-authored", "Read the authored argument", "disclosure", "Shows the argument as it was authored in the project's framing; nothing is changed."),)},
    **{key: {"label": label, "view": "settings", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-material.mjs Storage and cleanup in project Settings; tests/workspace_control_coverage.test.mjs 'settings/seeded'"} for key, label, kind, does in (
        ("settings:unverified-processes", "Unverified process observations", "disclosure", "Lists the process ids the owner saw but could not verify as belonging to this project; nothing is changed."),
        ("settings:cleanup-remove", "Remove empty unused session folders", "action", "Removes only the session folders the owner verified as empty and unused, after the confirmation box is ticked; it is off while the owner reports none or the cleanup unavailable."),)},
    **{key: {"label": label, "view": "research-workbench", "kind": kind, "rendered": True, "does": does, "renders_in": "research-workbench.mjs and research-geometry.mjs Explore, the workspace catalogue and its working surface; tests/workspace_control_coverage.test.mjs 'research-workbench/catalogue'"} for key, label, kind, does in (
        ("research:compare-selection", "Compare selection", "disclosure", "Shows the objects picked for comparison, which is a presentation choice only and changes no object; nothing is changed."),
        ("research:object-kind", "Object kind", "selection", "Narrows the catalogue to one kind of object through the owner's own read for that kind; nothing is changed."),
        ("research:more-objects", "More objects", "navigation", "Reads the next page of the catalogue from the owner's own continuation and adds it below; nothing is changed."),
        ("research:availability-reason", "Exact availability reason", "disclosure", "Shows the owner's exact reason an action is not available for the shown object; nothing is changed."),)},
    **{key: {"label": label, "view": "manuscript", "kind": kind, "rendered": True, "does": does, "renders_in": "manuscript-editor.mjs Document setup, the files the build uses as relation rows; tests/workspace_control_coverage.test.mjs 'manuscript/setup-open'"} for key, label, kind, does in (
        ("writing:setup-file", "Document file", "navigation", "Opens that file of the document in the Writing editor; nothing is changed."),)},
    **{key: {"label": label, "view": "presentation", "kind": kind, "rendered": True, "does": does, "renders_in": "derived-output.mjs the derived output card when the owner reports no reader-plan output; tests/workspace_control_coverage.test.mjs 'presentation/seeded'"} for key, label, kind, does in (
        ("output:reader-plan-absence", "Reader-plan output is not configured", "disclosure", "Says why the project has no reader-plan output, in the owner's words, or that it is not prepared yet; nothing is changed."),)},
    **{key: {"label": label, "view": "shell", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-chrome.mjs the project navigation, Running now, while the conversation owner observes a turn running; tests/workspace_control_coverage.test.mjs 'shell/running-now'"} for key, label, kind, does in (
        ("nav:live-task", "Current task", "navigation", "Opens the task the running turn is working on, named by the Work owner; nothing is changed."),
        ("nav:live-conversation", "Active conversation", "navigation", "Opens the conversation the owner observes running, so its turn can be followed; nothing is changed."),)},
    **{key: {"label": label, "view": "shared", "kind": kind, "rendered": True, "does": does, "renders_in": "workspace-topology.mjs the typed-relationship list under the drawing (Related tasks, the reader-plan relation map); tests/workspace_control_coverage.test.mjs 'shared/topology-plain'"} for key, label, kind, does in (
        ("topology:relation", "Related object", "selection", "Selects the object at the other end of one typed relationship, or reads it from its owner when it lies outside the page; nothing is changed."),
        ("topology:relation-source", "Relationship source", "navigation", "Reads the object at the near end of a relationship that comes in from outside the page, from its owner; nothing is changed."),)},
    **{key: {"label": label, "view": view, "kind": "navigation", "rendered": True, "does": does, "renders_in": where} for key, label, view, does, where in (
        ("now:project-title", "Project title", "now", "Opens this project at its Home page; nothing is changed.", "workspace-now.mjs Now, Continue: the project's title link; tests/workspace_control_coverage.test.mjs 'now/page'"),
        ("projects:project", "Project", "projects", "Opens this project in the way chosen above the list: writing, a source, tasks or its Home; nothing is changed.", "project-work.mjs the project list of Projects; tests/workspace_control_coverage.test.mjs 'projects/page'"),
        ("home:task-title", "Task title", "overview", "Opens that task from the Home page; nothing is changed.", "workspace-home.mjs the task rows of Home; tests/workspace_control_coverage.test.mjs 'overview/seeded'"),
        ("material:open-owner", "Open material owner", "material", "Opens the page of the owner of this material, or its read record when a repository owns it; nothing is changed.", "workspace-material.mjs the Manage panel of a shared material binding; tests/workspace_control_coverage.test.mjs 'material/panels-open'"),
        ("history:download-state", "Download full saved state", "history", "Downloads the project's whole saved authoring state as a file, read from the owner; nothing is changed.", "workspace-history.mjs Activity; tests/workspace_control_coverage.test.mjs 'history/timeline'"),
        ("dependencies:open-record", "Open exact binding record", "dependencies", "Opens the owner's exact record of this binding in a new tab; nothing is changed.", "workspace-app.mjs Workspace dependencies, each binding; tests/workspace_control_coverage.test.mjs 'dependencies/page'"),)},
    # ---- wave 13 id sweep: declarations (end) ----
}

JOURNEY_DECLARATIONS: dict[str, dict[str, Any]] = {
    "orient-research-surface": {"title": "Find your way around the working surface", "area": "research-workbench", "steps": [
        {"id": "outline", "title": "Orient in the relation outline", "control": "research:representation",
         "say": "Choose Relation outline. It shows the same objects as the map; changing representation edits nothing.",
         "done": {"fact": "researchRepresentation", "equals": "outline"}},
        {"id": "focus", "title": "Inspect an object without leaving your task", "control": "research:object",
         "say": "Select an object. Open focused object reads it; the current editor stays available. Comparison is visual.",
         "done": {"fact": "researchFocus", "truthy": True}},
        {"id": "read", "title": "Open the full reading or editor", "control": "research:inspect",
         "say": "Open focused object. Inspect before including a source window. Back returns here; cues record navigation only.",
         "done": {"all": [{"fact": "researchRepresentation", "equals": "focus"}, {"fact": "researchFocal", "truthy": True}]}},
    ]},
    "welcome": {
        "title": "Find your way around",
        "area": "overview",
        "steps": [
            {"id": "manuscript", "title": "Open the manuscript", "control": "nav:manuscript",
             "say": "Choose Writing or Continue writing on Home. The status distinguishes saved text from its PDF.",
             "done": {"fact": "view", "equals": "manuscript"}},
            {"id": "outline", "title": "See where you are", "control": "manuscript:outline",
             "say": "Open Document outline under Writing. Choose a heading to move there.",
             "done": {"all": [{"fact": "view", "equals": "manuscript"}, {"fact": "outline", "truthy": True}]}},
            {"id": "reader-plan", "title": "Read the plan for the reader", "control": "nav:reader-plan",
             "say": "Under More, open Reader plan. Its source mark shows whether a section is linked.",
             "done": {"fact": "view", "equals": "reader-plan"}},
            {"id": "open-in-manuscript", "title": "Go to a section in the manuscript", "control": "reader-plan:open-in-manuscript",
             "say": "Select a section and Open in manuscript. Use Back to Reader plan to return.",
             "done": {"all": [{"fact": "view", "equals": "manuscript"}, {"fact": "returnVisible", "truthy": True}]}},
            {"id": "return", "title": "Return where you were", "control": "context:return",
             "say": "Use Back to Reader plan. Your place and any unsaved draft are kept.",
             "done": {"fact": "view", "equals": "reader-plan"}},
            {"id": "history", "title": "Inspect one change", "control": "history:entry",
             "say": "Under More, choose Activity. Open an entry to inspect its changes and saved text.",
             "done": {"all": [{"fact": "view", "equals": "history"}, {"fact": "historyOpen", "truthy": True}]}},
            {"id": "work", "title": "Find what is blocking work", "control": "work:item",
             "say": "Choose Tasks and open a blocked task. Read its blocker and next action.",
             "done": {"all": [{"fact": "view", "equals": "work"}, {"fact": "workSelected", "truthy": True}]}},
            {"id": "context-chip", "title": "Keep the selected Work in view", "control": "context:work",
             "say": "Leave Tasks. The task chip returns to this task; Clear removes that context.",
             "done": {"all": [{"fact": "view", "not_equals": "work"}, {"fact": "workSelected", "truthy": True}]}},
            {"id": "conversation", "title": "See what a message will carry", "control": "conversation:context",
             "say": "Open Conversation, then Options and Context. Check the retained target and reading; Next message sets future preferences.",
             "done": {"all": [{"fact": "sessionOpen", "truthy": True}, {"fact": "inspectorOpen", "truthy": True}]}},
            {"id": "template", "title": "Preview a template without saving", "control": "manuscript:document-setup",
             "say": "In Writing, open Document setup and Template & layout. Preview is separate from Apply this reviewed preview.",
             "done": {"fact": "templateOpen", "truthy": True}},
        ],
    },
    # C10 (2026-10-14): one task per area where the shell observes a state that proves each step;
    # every step names a rendered control; no step starts a write, a model or a run
    "why-waiting": {
        "title": "Find why work is waiting",
        "area": "work",
        "steps": [
            {"id": "open", "title": "Open Work", "control": "nav:work",
             "say": "Choose Tasks to read their standing.",
             "done": {"fact": "view", "equals": "work"}},
            {"id": "select", "title": "Select a waiting item", "control": "work:item",
             "say": "Open a blocked task to read its blocker and next action.",
             "done": {"all": [{"fact": "view", "equals": "work"}, {"fact": "workSelected", "truthy": True}]}},
            {"id": "keep", "title": "Keep it in view", "control": "context:work",
             "say": "Open another view. The task chip returns to the selected task.",
             "done": {"all": [{"fact": "view", "not_equals": "work"}, {"fact": "workSelected", "truthy": True}]}},
        ],
    },
    "plan-to-source": {
        "title": "From the reader plan to the source and back",
        "area": "reader-plan",
        "steps": [
            {"id": "open", "title": "Open the reader plan", "control": "nav:reader-plan",
             "say": "Under More, open Reader plan and choose a source-linked section.",
             "done": {"fact": "view", "equals": "reader-plan"}},
            {"id": "source", "title": "Go to the section's source", "control": "reader-plan:open-in-manuscript",
             "say": "Select a bound section, then Open in manuscript. A Back control appears at the top for the return.",
             "done": {"all": [{"fact": "view", "equals": "manuscript"}, {"fact": "returnVisible", "truthy": True}]}},
            {"id": "back", "title": "Return to the plan", "control": "context:return",
             "say": "Use Back to Reader plan. The selected section and any unsaved draft are kept.",
             "done": {"fact": "view", "equals": "reader-plan"}},
        ],
    },
    "orient-manuscript": {
        "title": "Find your place in the manuscript",
        "area": "manuscript",
        "steps": [
            {"id": "open", "title": "Open the manuscript", "control": "nav:manuscript",
             "say": "Choose Writing. The status distinguishes saved text from the PDF.",
             "done": {"fact": "view", "equals": "manuscript"}},
            {"id": "outline", "title": "Use the outline", "control": "manuscript:outline",
             "say": "Open Document outline under Writing. Choose a heading to move there.",
             "done": {"all": [{"fact": "view", "equals": "manuscript"}, {"fact": "outline", "truthy": True}]}},
            {"id": "setup", "title": "See the document setup", "control": "manuscript:document-setup",
             "say": "Open Document setup, then Template & layout. Preview makes a candidate; nothing changes until Apply this reviewed preview.",
             "done": {"fact": "templateOpen", "truthy": True}},
        ],
    },
    "inspect-change": {
        "title": "Inspect one recorded change",
        "area": "history",
        "steps": [
            {"id": "open", "title": "Open Activity", "control": "nav:history",
             "say": "Choose Activity. Changes are grouped by day; the category selector is the owner's filter.",
             "done": {"fact": "view", "equals": "history"}},
            {"id": "entry", "title": "Open an entry", "control": "history:entry",
             "say": "Open an entry. Its hunks come first; whole saved text stays behind Show saved text; Open goes to the affected object.",
             "done": {"all": [{"fact": "view", "equals": "history"}, {"fact": "historyOpen", "truthy": True}]}},
        ],
    },
    # Orientation only: existing facts prove navigation/context, not an upload, Save or claim link.
    "document-reference-actions": {
        "title": "Find document and reference actions", "area": "material",
        "steps": [
            {"id": "material", "title": "Open your document list", "control": "nav:material",
             "say": "Choose Sources. Add local document accepts PDF or text. Check its destination, then inspect the offered reading.",
             "done": {"fact": "view", "equals": "material"}},
            {"id": "conversation", "title": "Find the conversation", "control": "conversation:toggle",
             "say": "After inspecting document text, Use in conversation selects that reading and keeps your question. Send is separate.",
             "done": {"fact": "sessionOpen", "truthy": True}},
            {"id": "context", "title": "Check the reading for your question", "control": "conversation:context",
             "say": "Inspect Next message context. PDF text does not show figure or equation layout; inspect the original page when needed.",
             "done": {"all": [{"fact": "sessionOpen", "truthy": True}, {"fact": "inspectorOpen", "truthy": True}]}},
            {"id": "research", "title": "Open Research for references", "control": "nav:research",
             "say": "Under More, open Research and Literature. Add to Literature records provenance; Link to claim needs a passage and rationale.",
             "done": {"fact": "view", "equals": "research"}},
        ],
    },
    "what-a-message-carries": {
        "title": "See what a message will carry",
        "area": "conversation",
        "steps": [
            {"id": "open", "title": "Open the conversation", "control": "conversation:toggle",
             "say": "Open Conversation. Its composer names the message target.",
             "done": {"fact": "sessionOpen", "truthy": True}},
            {"id": "context", "title": "Inspect the context", "control": "conversation:context",
             "say": "Open Next message context to inspect the reading, target and AI settings.",
             "done": {"all": [{"fact": "sessionOpen", "truthy": True}, {"fact": "inspectorOpen", "truthy": True}]}},
        ],
    },
}

AREA_DECLARATIONS: dict[str, dict[str, Any]] = {
    "review-evidence":{"title":'Review evidence',"view":"review-evidence","glance":'Read review counts, then selected evidence.',"states":[],"shortcuts":[],"journeys":[]},
    "source-inspector":{"title":"Source inspector","view":"source-inspector","glance":'Read developer declarations and retained facts.',"states":[],"shortcuts":[],"journeys":[]},
    "historical-obligations":{"title":"Historical engine obligations","view":"historical-obligations","glance":'Read selected engine history; this is separate from Tasks.',"states":[],"shortcuts":[],"journeys":[]},
    "backlog":{"title":'All tasks',"view":"backlog","glance":'Find tasks across projects.',"states":[],"shortcuts":[],"journeys":[]},
    "research-workbench": {"title": "Explore across projects", "view": "research-workbench",
        "glance": 'Explore selected objects and their relationships. Reading, message context, execution and scientific judgement are separate; check an uncertain original request.',
        "states": [], "shortcuts": [{"key": "?", "does": "Open help"}, {"key": "Esc", "does": "Close help or the current inspector"}], "journeys": ["orient-research-surface"]},
    "overview": {"title": 'Home', "view": "overview", "glance": 'Continue this project.',
                 "states": [{"label": "PDF matches saved document", "tone": "ok"}, {"label": "Build out of date", "tone": "attention"}],
                 "shortcuts": [{"key": "?", "does": "Open help for this view"}, {"key": "Esc", "does": "Close help, a cue or the inspector"}], "journeys": ["welcome"]},
    "work": {"title": 'Tasks', "view": "work", "glance": 'Read purpose, blockers and the next action.',
             "states": [{"label": "Waiting", "tone": "neutral"}, {"label": "Ready", "tone": "ok"}, {"label": "Observed running", "tone": "running"}, {"label": "Done; current review separate", "tone": "neutral"}],
             "shortcuts": [], "journeys": ["why-waiting"]},
    "material": {"title": 'Sources', "view": "material", "glance": 'Read and organise research sources.',
                 "states": [{"label": "Not yet inspected", "tone": "attention"}, {"label": "Bound", "tone": "ok"}], "shortcuts": [], "journeys": ["document-reference-actions"]},
    "history": {"title": 'Activity', "view": "history", "glance": 'Inspect saved changes.',
                "states": [{"label": "Bytes match the saved record", "tone": "ok"}, {"label": "Recorded source differs", "tone": "attention"}], "shortcuts": [], "journeys": ["inspect-change"]},
    "settings": {"title": 'Project settings', "view": "settings", "glance": 'Set writing guidance and future defaults.',
                 "states": [], "shortcuts": [], "journeys": []},
    "argument": {"title": 'Argument & evidence', "view": "argument", "glance": 'Organise claims and evidence.',
                 "states": [{"label": "Current", "tone": "ok"}, {"label": "Stale", "tone": "attention"}], "shortcuts": [], "journeys": []},
    "reader-plan": {"title": 'Reader plan', "view": "reader-plan", "glance": 'Plan the reader’s route through the text.',
                    "states": [{"label": "Bound to source heading", "tone": "ok"}, {"label": "Source inferred", "tone": "attention"}, {"label": "No source link", "tone": "neutral"}],
                    "shortcuts": [], "journeys": ["plan-to-source"]},
    "research": {"title": 'Research', "view": "research", "glance": 'Inspect literature, calculations and results.',
                 "states": [{"label": "Current", "tone": "ok"}, {"label": "Stale", "tone": "attention"}, {"label": "Untracked", "tone": "attention"}], "shortcuts": [], "journeys": ["document-reference-actions"]},
    "manuscript": {"title": 'Writing', "view": "manuscript", "glance": 'Write locally; wait for Saved.',
                   "states": [{"label": "Saved", "tone": "ok"}, {"label": "Unsaved edits", "tone": "attention"}, {"label": "Needs review", "tone": "attention"}],
                   "shortcuts": [{"key": "F", "does": "Focus manuscript / Restore panels"}, {"key": "Ctrl-S", "does": "Save every standing edit"}, {"key": "Esc", "does": "Revert the paragraph under the caret"}],
                   "journeys": ["orient-manuscript"]},
    "review": {"title": 'Review & notes', "view": "review", "glance": 'Read proposed changes, comments and notes.',
               "states": [{"label": "Pending", "tone": "attention"}, {"label": "Applied", "tone": "ok"}], "shortcuts": [], "journeys": []},
    "presentation": {"title": 'Figures & output', "view": "presentation", "glance": 'Read a verified PDF or develop figures.',
                     "states": [{"label": "Build running", "tone": "running"}, {"label": "Preview only", "tone": "neutral"}], "shortcuts": [], "journeys": []},
    "conversation": {"title": 'Conversation', "view": "conversation", "glance": 'Ask about an explicit reading or target.',
                     "states": [{"label": "Reply saved", "tone": "ok"}, {"label": "Work acceptance separate", "tone": "neutral"}, {"label": "Read-only", "tone": "historical"}],
                     "shortcuts": [], "journeys": ["what-a-message-carries"]},
}


# Task guidance is content of this Help owner, not a second progress store. Only
# an observed journey records progress; following a recipe never claims success.
_AREA_GUIDANCE = {
    "overview": ('Choose Writing, Sources or a task.', 'Opening a view starts nothing.', "open-or-create-a-project"),
    "work": ('Open a task and What led here.', 'Completion, review and running differ.', "find-what-happened"),
    "material": ('Add a document or open a file.', 'Only Send asks an AI.', "read-a-source-and-ask-a-question"),
    "history": ('Open a dated outcome and its destination.', 'Recorded history is not current execution.', "find-what-happened"),
    "settings": ('Inspect the relevant settings.', 'Admitted messages stay unchanged.', "find-help-and-recover"),
    "argument": ('Open a claim or its relationships.', 'A link does not prove a claim.', "write-save-and-reopen"),
    "reader-plan": ('Open a plan item or the outline.', 'Planning does not edit writing.', "write-save-and-reopen"),
    "research": ('Choose the relevant research view.', 'Output is not scientific acceptance.', "read-a-source-and-ask-a-question"),
    "manuscript": ('Click a paragraph to write.', 'Saved draft text is not a PDF build.', "write-save-and-reopen"),
    "review": ('Open the relevant review item.', 'A response does not apply an edit.', "organise-tasks-and-reviews"),
    "presentation": ('Inspect the output or build details.', 'Build is an explicit action.', "write-save-and-reopen"),
    "conversation": ('Inspect context beside the destination; check the reading before Send.', 'Looking elsewhere does not Send.', "read-a-source-and-ask-a-question"),
    "backlog": ('Inspect a task, then Plan this task.', 'Planning does not start or cancel work.', "organise-tasks-and-reviews"),
    "review-evidence": ('Choose a question list.', 'Counts do not mean bodies were read.', "organise-tasks-and-reviews"),
}
for _area_id, (_next, _effects, _section) in _AREA_GUIDANCE.items():
    AREA_DECLARATIONS[_area_id].update(next_action=_next, effects=_effects,
        guide={"id": "tasks", "section": _section, "label": "Task recipe"})

# NOW (wave 11 census repair R3): the page the app opens on gets its own help; one sentence per group it draws
# (src/laplace/web/static_shared/workspace-now.mjs), instead of borrowing the Projects help.
AREA_DECLARATIONS["now"] = {"title": "Now", "view": "now", "glance": 'What is running, what waits for you, and where to continue.',
    "next_action": 'Open a running conversation, a waiting task or a recent project.', "effects": 'Opening a row starts nothing.',
    "parts": [{"name": "Running now", "says": 'Work the engine reports running in any project, read every 5 seconds while this page is open, with the time of the read.'},
              {"name": "Waiting for you", "says": 'Completed tasks in any project whose evidence needs a current review, and the task the Work catalogue suggests inspecting next.'},
              {"name": "Continue", "says": 'Up to six projects you opened most recently in this app, each with Open, its Tasks and, when it has a manuscript, Continue writing.'},
              {"name": "Start", "says": 'Create a new project, or bring an existing manuscript in as a project.'}],
    "states": [], "shortcuts": [], "journeys": []}

for _id, _title, _purpose, _next, _effects, _guide in (
    ("projects", "Projects", 'Open or create a writing project.', 'Choose a title or Create a project.', 'Creation sends no message.', "open-or-create-a-project"),
    ("workflows", "Workflows", 'Optional reusable work steps.', 'Choose a workflow and read its purpose.', 'Save, prepare and start are separate.', "use-a-workflow"),
    ("workspace-activity", "Workspace activity", 'Find what happened and where it went.', 'Open the offered conversation or result.', 'Recorded is not necessarily running.', "find-what-happened"),
    ("dependencies", "Shared-source links", 'Inspect shared sources between projects.', 'Open a source link.', 'Listed does not mean inspected.', "read-a-source-and-ask-a-question"),
    ("owners", "System owners", 'Advanced application reference.', 'Inspect an owner when needed.', 'Reading grants no source effects.', "find-help-and-recover"),
    ("app-settings", "App settings", 'Set up optional AI and app preferences.', 'Read account setup for AI assistance.', 'Refresh may launch discovery; Send is separate.', "find-help-and-recover"),
    ("document-intake", "Add a document", 'Retain a PDF or text original.', 'Choose a file and check its destination.', 'Adding and linking are separate.', "read-a-source-and-ask-a-question"),
    ("source-reading", "Read a source", 'Read the offered source window.', 'Check coverage before using it.', 'Unseen text is not inspected.', "read-a-source-and-ask-a-question"),
    ("review-setup", "Set up reviews", 'Define review questions.', 'Save review questions first.', 'Reviewer approvals are optional.', "organise-tasks-and-reviews"),
    ("saved-workflow-reading", "Saved workflow version", 'Read saved text separately.', 'Close saved version to return.', 'Reading does not change the draft guard.', "use-a-workflow"),
):
    AREA_DECLARATIONS[_id] = {"title": _title, "view": _id, "glance": _purpose,
        "next_action": _next, "effects": _effects, "states": [], "shortcuts": [], "journeys": [],
        "guide": {"id": "tasks", "section": _guide, "label": "Task recipe"}}

# THE INTERNAL DIAGRAMS (C10, plan §7): one per area, authored here, served by the help owner's
# `diagrams` concept and drawn by workspace-topology from these nodes, edges and layout hints
# (rank, groups). They explain the implemented mechanism of each area: every node is an object
# or a step the owner really has; every edge is a typed relation the owner really publishes.
# Nothing here is inferred from a project; nothing is scientific.
def _flow(ids, kind="then"):
    return [{"kind": kind, "source": a, "target": b} for a, b in zip(ids, ids[1:])]


DIAGRAM_DECLARATIONS: dict[str, dict[str, Any]] = {
    "backlog":{"title":"Work and planning","description":"Recorded Work remains canonical; planning changes no execution authority.","nodes":[{"id":"catalogue","title":"Whole Work catalogue"},{"id":"inspect","title":"Inspect exact Work"},{"id":"plan","title":"Explicit planning"}],"edges":[{"kind":"then","source":"catalogue","target":"inspect"},{"kind":"then","source":"inspect","target":"plan"}],"layout":{"rank":{"catalogue":0,"inspect":1,"plan":2},"groups":[]}},
    "research-workbench": {"title": "Objects, exact readings and recorded work",
        "description": "An object is read through its owner. Explicit input choices supply a Work evidence packet; recorded responses and human manuscript application remain separate decisions.",
        "nodes": [{"id": "object", "title": "Owner-qualified object"}, {"id": "reading", "title": "Inspected reading"}, {"id": "packet", "title": "Selected evidence packet"}, {"id": "work", "title": "Recorded Work and responses"}],
        "edges": [{"kind": "reads", "source": "object", "target": "reading"}, {"kind": "explicit-selection", "source": "reading", "target": "packet"}, {"kind": "consumed-by", "source": "packet", "target": "work"}],
        "layout": {"rank": {"object": 0, "reading": 1, "packet": 2, "work": 3}, "groups": []}},
    "overview": {"title": "The four loops of a project",
                 "description": "A project is read and edited through its manuscript, cleared through its work, grounded in its material and discussed in its conversations; every loop records what it changes in Activity.",
                 "nodes": [{"id": "project", "title": "Project"}, {"id": "manuscript", "title": "Manuscript"}, {"id": "work", "title": "Work"},
                           {"id": "material", "title": "Material"}, {"id": "conversation", "title": "Conversations"}, {"id": "activity", "title": "Activity"}],
                 "edges": [{"kind": "contains", "source": "project", "target": t} for t in ("manuscript", "work", "material", "conversation")]
                          + [{"kind": "tracked-by", "source": t, "target": "activity"} for t in ("manuscript", "work", "material", "conversation")],
                 "layout": {"rank": {"project": 0, "manuscript": 1, "work": 1, "material": 1, "conversation": 1, "activity": 2}, "groups": [{"id": "loops", "title": "The loops", "nodes": ["manuscript", "work", "material", "conversation"]}]}},
    "work": {"title": "Work: facets and the dispatch tree",
             "description": "A work item carries four separate facets. A dispatched item waits on its children, whose returns are synthesised back into it.",
             "nodes": [{"id": "item", "title": "Work item"}, {"id": "lifecycle", "title": "Recorded lifecycle"}, {"id": "readiness", "title": "Prerequisite readiness"},
                       {"id": "acceptance", "title": "Current acceptance"}, {"id": "execution", "title": "Execution standing"},
                       {"id": "parent", "title": "Parent work"}, {"id": "child", "title": "Child work"}, {"id": "return", "title": "Return"}, {"id": "synthesis", "title": "Synthesis"}],
             "edges": [{"kind": "contains", "source": "item", "target": f} for f in ("lifecycle", "readiness", "acceptance", "execution")]
                      + [{"kind": "contains", "source": "parent", "target": "child"}, {"kind": "then", "source": "child", "target": "return"},
                         {"kind": "then", "source": "return", "target": "synthesis"}, {"kind": "requires", "source": "parent", "target": "synthesis"}],
             "layout": {"rank": {"item": 0, "lifecycle": 1, "readiness": 1, "acceptance": 1, "execution": 1, "parent": 0, "child": 1, "return": 2, "synthesis": 3},
                        "groups": [{"id": "facets", "title": "Facets of one item", "nodes": ["lifecycle", "readiness", "acceptance", "execution"]},
                                   {"id": "dispatch", "title": "Dispatch tree", "nodes": ["parent", "child", "return", "synthesis"]}]}},
    "manuscript": {"title": "Manuscript: from source to saved version",
                   "description": "Source files are projected into the reader; an edit returns a receipt, a saved version and an Activity record; the PDF is built from the saved document.",
                   "nodes": [{"id": "source", "title": "Source files"}, {"id": "projection", "title": "Projection"}, {"id": "edit", "title": "Edit"}, {"id": "receipt", "title": "Receipt"},
                             {"id": "version", "title": "Saved version"}, {"id": "history", "title": "Activity record"}, {"id": "pdf", "title": "PDF build"}],
                   "edges": _flow(["source", "projection", "edit", "receipt", "version", "history"]) + [{"kind": "reads", "source": "pdf", "target": "version"}],
                   "layout": {"rank": {"source": 0, "projection": 1, "edit": 2, "receipt": 3, "version": 4, "history": 5, "pdf": 5}, "groups": []}},
    "reader-plan": {"title": "Reader plan: sections, sources, argument and passages",
                    "description": "A section is bound to one source heading, argues its planned objects, which are supported by evidence; its paragraph plan maps to passages of the source.",
                    "nodes": [{"id": "section", "title": "Plan section"}, {"id": "heading", "title": "Source heading"}, {"id": "node", "title": "Argument object"},
                              {"id": "evidence", "title": "Evidence"}, {"id": "paragraph", "title": "Paragraph plan"}, {"id": "passage", "title": "Source passage"}],
                    "edges": [{"kind": "bound-to", "source": "section", "target": "heading"}, {"kind": "argues", "source": "section", "target": "node"},
                              {"kind": "supported-by", "source": "node", "target": "evidence"}, {"kind": "contains", "source": "section", "target": "paragraph"},
                              {"kind": "placed-in", "source": "paragraph", "target": "passage"}, {"kind": "contains", "source": "heading", "target": "passage"}],
                    "layout": {"rank": {"heading": 0, "section": 1, "node": 2, "paragraph": 2, "evidence": 3, "passage": 3}, "groups": []}},
    "history": {"title": "Activity: from the journal to one record",
                "description": "The journal and the saved versions are folded into an index; a page of that index opens one record with its hunks and byte identities.",
                "nodes": [{"id": "journal", "title": "Journal"}, {"id": "versions", "title": "Saved versions"}, {"id": "fold", "title": "Indexed fold"},
                          {"id": "page", "title": "Page"}, {"id": "record", "title": "Record"}, {"id": "hunks", "title": "Hunks"}, {"id": "identity", "title": "Byte identities"}],
                "edges": [{"kind": "then", "source": "journal", "target": "fold"}, {"kind": "then", "source": "versions", "target": "fold"}] + _flow(["fold", "page", "record"])
                         + [{"kind": "contains", "source": "record", "target": "hunks"}, {"kind": "contains", "source": "record", "target": "identity"}],
                "layout": {"rank": {"journal": 0, "versions": 0, "fold": 1, "page": 2, "record": 3, "hunks": 4, "identity": 4}, "groups": []}},
    "review": {"title": "Review: from a turn to its effect",
               "description": "A proposal arrives on a turn as versions of the text; its hunks are decided one by one; an accepted decision is applied and its effect recorded.",
               "nodes": [{"id": "turn", "title": "Turn"}, {"id": "versions", "title": "Versions"}, {"id": "hunks", "title": "Hunks"}, {"id": "decision", "title": "Decision"},
                         {"id": "application", "title": "Application"}, {"id": "effect", "title": "Effect"}],
               "edges": _flow(["turn", "versions", "hunks", "decision", "application", "effect"]),
               "layout": {"rank": {"turn": 0, "versions": 1, "hunks": 2, "decision": 3, "application": 4, "effect": 5}, "groups": []}},
    "research": {"title": "Research: result, binding, claim",
                 "description": "A recorded result is bound to an argument object; the claim the object makes cites that binding. Currentness is recomputed only when read.",
                 "nodes": [{"id": "result", "title": "Result"}, {"id": "binding", "title": "Binding"}, {"id": "claim", "title": "Claim"}],
                 "edges": _flow(["result", "binding", "claim"]), "layout": {"rank": {"result": 0, "binding": 1, "claim": 2}, "groups": []}},
    "presentation": {"title": "Figures and output: spec, render, placement",
                     "description": "A figure spec renders to a file that is placed in the manuscript; the PDF is built from the saved document and never from a preview.",
                     "nodes": [{"id": "spec", "title": "Figure spec"}, {"id": "render", "title": "Render"}, {"id": "placement", "title": "Placement"}, {"id": "document", "title": "Saved document"}, {"id": "pdf", "title": "PDF"}],
                     "edges": _flow(["spec", "render", "placement"]) + [{"kind": "placed-in", "source": "placement", "target": "document"}, {"kind": "then", "source": "document", "target": "pdf"}],
                     "layout": {"rank": {"spec": 0, "render": 1, "placement": 2, "document": 3, "pdf": 4}, "groups": []}},
    "conversation": {"title": "Conversation: what a message carries",
                     "description": "A message names its target; the admitted turn records its actions and receipts and the reply. A parent turn waits on its children and synthesises their returns.",
                     "nodes": [{"id": "target", "title": "Target"}, {"id": "turn", "title": "Admitted turn"}, {"id": "actions", "title": "Actions and receipts"}, {"id": "reply", "title": "Reply"},
                               {"id": "parent", "title": "Parent turn"}, {"id": "children", "title": "Child turns"}, {"id": "returns", "title": "Returns"}, {"id": "synthesis", "title": "Synthesis"}],
                     "edges": _flow(["target", "turn", "actions", "reply"]) + [{"kind": "contains", "source": "parent", "target": "children"}] + _flow(["children", "returns", "synthesis"])
                              + [{"kind": "requires", "source": "parent", "target": "synthesis"}],
                     "layout": {"rank": {"target": 0, "turn": 1, "actions": 2, "reply": 3, "parent": 0, "children": 1, "returns": 2, "synthesis": 3},
                                "groups": [{"id": "one", "title": "One message", "nodes": ["target", "turn", "actions", "reply"]}, {"id": "wait", "title": "Parent wait", "nodes": ["parent", "children", "returns", "synthesis"]}]}},
    "settings": {"title": "Settings: how scopes layer",
                 "description": "Engine declarations give the defaults; a project overrides them; a conversation prefers within the project; the admitted turn records exactly what applied.",
                 "nodes": [{"id": "engine", "title": "Engine declarations"}, {"id": "project", "title": "Project defaults"}, {"id": "conversation", "title": "Conversation preferences"}, {"id": "turn", "title": "Admitted turn"}],
                 "edges": _flow(["engine", "project", "conversation", "turn"], kind="overrides"),
                 "layout": {"rank": {"engine": 0, "project": 1, "conversation": 2, "turn": 3}, "groups": []}},
    "material": {"title": "Material: readers, files and shared bindings",
                 "description": "A project reads its recorded files through readers; a shared binding points at workspace material and carries its own currentness.",
                 "nodes": [{"id": "project", "title": "Project"}, {"id": "reader", "title": "Reader"}, {"id": "file", "title": "Recorded file"}, {"id": "binding", "title": "Shared binding"}, {"id": "shared", "title": "Workspace material"}],
                 "edges": [{"kind": "contains", "source": "project", "target": "reader"}, {"kind": "reads", "source": "reader", "target": "file"},
                           {"kind": "contains", "source": "project", "target": "binding"}, {"kind": "bound-to", "source": "binding", "target": "shared"}],
                 "layout": {"rank": {"project": 0, "reader": 1, "binding": 1, "file": 2, "shared": 2}, "groups": []}},
    "argument": {"title": "Argument and evidence",
                 "description": "An argument object may require other objects; evidence supports it; a reader-plan section places it. A requirement is a stated relation, not a verification.",
                 "nodes": [{"id": "object", "title": "Argument object"}, {"id": "premise", "title": "Required object"}, {"id": "evidence", "title": "Evidence"}, {"id": "section", "title": "Plan section"}],
                 "edges": [{"kind": "requires", "source": "object", "target": "premise"}, {"kind": "supported-by", "source": "object", "target": "evidence"}, {"kind": "placed-in", "source": "object", "target": "section"}],
                 "layout": {"rank": {"premise": 0, "object": 1, "evidence": 2, "section": 2}, "groups": []}},
}


# THE STATES (C10 D2, repair H6): a finite list of states per view, declared once; a control
# declares the states it renders in (`states`) and whether its instances are dynamic (`dynamic`:
# they carry data-control-owner with the qualified owner id). STATE_COVERAGE says for every
# view/state whether the source render coverage test (tests/workspace_control_coverage.test.mjs)
# mounts that state through an existing harness ("source") or whether only the root's actual
# browser matrix (C12) can reach it ("actual", with the reason). A control present in a mounted
# state must render there; a control declared for other states of that view only must be absent
# or disabled there; no undeclared data-control value may appear.
VIEW_STATES: dict[str, dict[str, str]] = {
    "workflows": {"empty": "native workflow library with no selected design or invented run", "runs": "Runs for the selected saved version, following only its offered uses read", "river-run": "one opened run: its drawing with each stage's marks and the river of observed flow under it", "guide": "Guide in the same retained workflow workspace", "draft-design": "Design with local unsaved edits and an enabled local discard", "selected": "authoring a selected workflow in Design", "saved-reading": "a separate exact saved-version reading",
                  "history-offered": "library/details with actual history_read offered and the library disclosure explicitly open",
                  "history-open": "a current metadata history page with explicit saved-row reads",
                  "history-next-offered": "a current history page with an issued older-page continuation",
                  "saved-body-partial": "an exact incomplete saved-body reading with issued next_body_read",
                  "saved-body-complete": "a complete verified saved body offering its exact object_read",
                  "lineage-prepare-offered": "selected saved endpoint with Share complete saved lineage open and a permitted owner handover_action",
                  "check-offered": "Design with an owner-issued execution_preview offer (conditional controls)",
                  "check-result": "an execution check result with an issued role context read",
                  "withdraw-offered": "an uncertain original Save or Prepare with an owner withdrawal offer",
                  "observation-offered": "Runs with owner-issued uses or river reads, nothing read yet",
                  "observation-next-offered": "a read observation page with an issued next_read",
                  "river-reads-offered": "read river rows whose owner-issued reads have a supplied reader",
                  "run-detail-offered": "a read compact river run with an issued detail_read",
                  "stop-offered": "an opened research run view (Open run detail or Plan & run) with a permitted Stop and no held original",
                  "stop-pending": "a retained original Stop request held with its owner-issued request_read",
                  "stop-resend-offered": "the retained original checked RECORDED or NONE for its exact attempt"},
    "review-evidence":{"aggregate":"owner obligation counts without support expansion","list":"one bounded obligation enumeration","support":"selected evidence inspection routes","changed":"held observation changed; fresh summary requires explicit read"},
    "source-inspector":{"reading":"an explicitly addressed read-only Source inspector"},
    "historical-obligations":{"reading":"one explicit selected historical engine source or record"},
    "backlog":{"catalogue":"whole Work catalogue and qualified filters","selected":"exact Work selected","planning":"local authored planning fields","pending":"original planning request retained"},
    "research-workbench": {"workspace": "workspace object list inspected with Browse workspace objects explicitly opened", "source-selected": "selected exact source window with retained previous object and Browse workspace objects explicitly opened", "focus-inspection-offered": "relationship focus Inspector has an actual owner-issued detail_read"},
    "shell": {"global-entry": "workspace navigation with its global Help door; tests/first_use_shell.test.mjs",
              "cold-entry": "a cold entry: conversation closed, no selected Work, no return place, Focus hidden",
              "work-selected": "entered with a selected Work (work=): the Work chip and Clear are shown in the context strip",
              "return-place": "the Work chip opened Work from another view: Back to place is shown",
              "manuscript-view": "the Manuscript view is current: Focus manuscript is shown",
              "help-open": "the help layer is open inside main", "cue-running": "a task cue is mounted beside its control",
              "manuscript-unavailable": "a project without a manuscript: Manuscript, Document outline and Figures & output are unavailable",
              "compact-layout": "a compact project shell using its existing Menu button",
              "project-tools-open": "More project tools opened explicitly; advanced navigation is usable",
              "switcher-open": "the frame's project switcher opened (its search, its two links and one row per project read from the library)",
              "more-open": "the frame's More list opened (the four rarer workspace pages)"},
    "now": {"page": "the Now page: running work, waiting tasks, recent projects and the two ways to start"},
    "projects": {"page": "the Projects page: the task choice, the project list and the create and existing-manuscript forms"},
    "dependencies": {"page": "the Workspace dependencies page: the recorded shared-material links across projects"},
    "owners": {"page": "the System owners page: the owner search and the reads each owner offers"},
    "overview": {"ready": "Home of a project with a manuscript", "no-manuscript": "Home of a project without a manuscript"},
    "work": {"catalogue": "no item selected: the catalogue only", "selected": "an item selected with its blockers, prerequisites, map and forms",
             "list-open": "Choose another task opened explicitly while a Task is selected",
             "next-action-offered": "selected Task with an actual permitted blocker action offered visibly",
             "trail-offered": "selected Task with an actual owner-issued provenance read; focused Task trail evaluator",
             "continuity-continue-offered": "selected Task whose continuity issues an HTTP Continue at READY with the exact basis and current cut, no unresolved original and not read-only",
             "continuity-proof-offered": "selected Task whose continuity issues a fillable proof template with its HTTP route and current cut, no unresolved original and not read-only",
             "continuity-unresolved": "selected Task with a retained uncertain or checked original continuity request; Check is a pure issued GET",
             "continuity-resend-offered": "the owner check read NONE for the retained original and the exact old wire is kept; not read-only, never automatic",
             "continuity-review-offered": "selected Task whose owner names a review phase with an existing permitted recorder",
             "continuity-read-failed": "the selected Task continuity summary GET failed and Read progress again is mounted",
             "read-only": "a namespace observer: no authored-work or disposition forms",
             # WAVE 11 CENSUS REPAIRS: the two states the newly declared work:compare and work:result appear in
             "draft-compared": "selected Task whose authored-work draft basis changed, after Compare with the current work",
             "result-offered": "a completed Task with exactly one recorded comment route offers Open the result"},
    "material": {"files": "recorded files; optional project reading views remain closed", "readers-open": "Other project reading views explicitly opened alongside recorded files", "bindings": "shared material bindings present",
                 "retained-source": "recorded immutable original with Add to Literature available"},
    "history": {"timeline": "the activity timeline", "record-open": "one record opened from the timeline",
                "graphs": "the Graphs tab: the session analytics surface replaces the timeline (its own view strip; the Changes/Graphs strip is absent)"},
    "settings": {"families": "the app settings families", "project": "project settings with the writing stages",
                 "preferences": "Structural preferences with saved suggestions to compare"},
    "argument": {"record": "one argument object record"},
    "reader-plan": {"empty": "no reader plan yet", "selected": "one section selected (its display page)", "read-only": "a read-only reader plan"},
    "research": {"results": "recorded results listed", "empty": "no results"},
    "manuscript": {"opening": "the editor band before the reader is ready; secondary controls remain in Document tools",
                   "source-host": "ready native Writing host with adjacent Sources reading; focused host evaluator",
                   "write": "Write mode with a ready reader; Document tools remains closed",
                   "tools-open": "Document tools opened explicitly; secondary writing controls are usable",
                   "setup-open": "Document setup open with a template offered", "template-open": "a template candidate without a reviewed proof",
                   "template-reviewed": "a template candidate with its reviewed proof: Apply available"},
    "review": {"pending": "proposals awaiting a decision", "empty": "nothing pending", "comments": "saved passage comments with review routing"},
    "presentation": {"not-built": "the manuscript PDF not built; no derived output prepared", "build-failed": "the last manuscript build failed; its details are offered"},
    "conversation": {"open": "thread rows of saved turns", "composer": "the conversation open: retained reading, target and future message intent beside the composer",
                     "options-open": "infrequent Conversation Options opened explicitly; message decisions stay beside the composer",
                     "context-open": "the Context inspector open"},
    "shared": {"topology-plain": "a typed topology without a wide level", "topology-folded": "a typed topology with a folded wide level",
               "guard-inspector": "a read-only guard subject inspector"},
}
_SHELL = ['cold-entry', 'work-selected', 'return-place', 'manuscript-view', 'help-open', 'cue-running', 'manuscript-unavailable', 'compact-layout', 'project-tools-open', 'switcher-open', 'more-open']
_SHELL_WITH_MANUSCRIPT = ['cold-entry', 'work-selected', 'return-place', 'manuscript-view', 'help-open', 'cue-running', 'compact-layout', 'project-tools-open', 'switcher-open', 'more-open']
CONTROL_STATES: dict[str, dict[str, Any]] = {
    "nav:skip": {"states": [*_SHELL, "global-entry"]},
    "task:trail": {"states": ["trail-offered"]},
    "writing:sources": {"states": ["source-host", "opening", "tools-open", "setup-open"]},
    "help:read-guide": {"states": ["help-open"]},
    "tasks:add-open": {"states": ["catalogue", "selected"]},
    "tasks:add": {"states": ["catalogue", "selected"]},
    **{f"workflow:{key}": {"states": ["empty", "selected", "draft-design", "runs", "guide"]} for key in ("design", "runs", "guide")},
    "workflow:discard": {"states": ["draft-design"], "dynamic": True, "hidden_until": "Design contains local unsaved edits; saved effects are not undone"},
    "workflow:adapt": {"states": ["selected"], "dynamic": True, "hidden_until": "the verified current saved selection has no local edits and the owner issues creation choices"},
    "workflow:purpose": {"states": ["selected", "draft-design"]},
    "workflow:saved-read": {"states": ["selected", "draft-design", "history-open"]},
    "workflow:saved-close": {"states": ["saved-reading", "saved-body-partial", "saved-body-complete"]},
    "workflow:history": {"states": ["history-offered"], "dynamic": True, "hidden_until": "the selected library/detail row issues history_read"},
    "workflow:history-next": {"states": ["history-next-offered"], "dynamic": True, "hidden_until": "the admitted current history page issues next_read"},
    "workflow:saved-next": {"states": ["saved-body-partial"], "dynamic": True, "hidden_until": "the exact saved body remains partial and issues next_body_read"},
    "workflow:saved-workspace": {"states": ["saved-body-complete"], "dynamic": True, "hidden_until": "the complete verified saved body supplies object_read"},
    "workflow:lineage-prepare": {"states": ["lineage-prepare-offered"], "dynamic": True, "hidden_until": "the explicitly read lineage descriptor permits the exact preparation action"},
    "workflow:preview": {"states": ["check-offered", "check-result"], "dynamic": True, "hidden_until": "the owner listing issues an execution_preview offer"},
    "workflow:context-read": {"states": ["check-result"], "dynamic": True, "hidden_until": "a checked role carries an issued context_read"},
    "workflow:withdraw": {"states": ["withdraw-offered"], "dynamic": True, "hidden_until": "an uncertain original Save or Prepare carries an owner withdrawal offer"},
    "workflow:uses": {"states": ["observation-offered", "observation-next-offered"], "dynamic": True, "hidden_until": "the selected saved version issues a uses read"},
    "workflow:river": {"states": ["observation-offered", "observation-next-offered", "river-reads-offered", "run-detail-offered", "stop-offered", "stop-pending", "stop-resend-offered"], "dynamic": True, "hidden_until": "a listed run issues a river read requiring only work_id"},
    **{f"workflow:{key}-more": {"states": ["observation-next-offered"], "dynamic": True, "hidden_until": "the read page issues next_read"} for key in ("uses", "river")},
    "workflow:river-read": {"states": ["river-reads-offered", "river-run"], "dynamic": True, "hidden_until": "a consumer supplies a reader for a row's owner-issued reads; the opened run's river card supplies one for its row's reply, proposal and typed return"},
    # Wave 11: the opened run (drawing and river). Dynamic ids carry the step, mark or turn they act on as data-control-owner.
    **{f"workflow:{key}": {"states": ["river-run"], "dynamic": True, "hidden_until": hidden} for key, hidden in (
        ("run-return", "a run of a saved version is opened"), ("run-refresh", "a run of a saved version is opened"), ("runs-back", "a run of a saved version is opened"),
        ("run-step", "the opened run's consumed definition is drawn"), ("run-session", "a drawn stage has an observed attempt whose conversation the owner issues"),
        ("run-explain", "the opened run's consumed definition is drawn"), ("run-guide", "a run explanation is opened"), ("run-view", "the opened run's consumed definition is drawn"),
        ("run-fit", "the run is shown as a graph"), ("run-center", "the run is shown as a graph"), ("run-start", "the owner permits use_in_conversation for the opened run"),
        ("run-parent", "the opened run names its original conversation"), ("run-preparation", "a run of a saved version is opened"), ("run-exact", "a run of a saved version is opened"),
        ("run-step-result", "the chosen step has a conversation"), ("run-step-conversation", "the chosen step has a conversation"),
        ("run-continue", "the chosen review step's continue_action is available and permitted"), ("run-attempts", "the chosen step has earlier attempts"),
        ("run-earlier-result", "an earlier attempt is listed"), ("run-typed-return", "the chosen step's typed return read carries http"), ("run-retained-output", "the chosen step reused a retained output with a read"),
        ("river-mark", "the opened run's observed-flow read returned a timed mark"), ("river-step", "the opened run's observed-flow read returned"),
        ("river-follow", "the river was scrolled back or a mark was opened"), ("river-waiting", "an app-run step's continue_action is permitted"),
        ("river-identity", "a river card is open"), ("river-list", "the opened run's observed-flow read returned"), ("river-conversation", "a river card's row issues a conversation"),
        ("river-card-close", "a river card is open"), ("river-reply-more", "an opened reply page issues next_read"))},
    "workflow:runs-open": {"states": ["runs"], "dynamic": True, "hidden_until": "the selected saved version's runs read lists a run"},
    # Wave 12 (design-view): the Design view's controls render in Design (saved or with local edits); conditional ones are dynamic.
    "workflow:overview": {"states": ["selected", "draft-design", "runs", "river-run", "guide"]},
    "workflow:topology": {"states": ["selected", "draft-design", "river-run"]},
    **{f"workflow:{key}": {"states": ["selected", "draft-design"]} for key in ("save", "stage-add", "compare", "reinspect", "prepare-external", "design-view", "details", "technical", "purpose-edit", "setting-workflow")},
    **{f"workflow:{key}": {"states": ["selected", "draft-design"], "dynamic": True, "hidden_until": hidden} for key, hidden in (
        ("explain", "a section with an explanation is drawn"), ("explain-guide", "an explanation is opened"), ("stage", "the draft has a step to draw"),
        ("stage-insert", "a step is chosen on the drawing"), ("stage-earlier", "a step is chosen on the drawing"), ("stage-later", "a step is chosen on the drawing"), ("stage-remove", "a step is chosen on the drawing"),
        ("pattern-review", "a step is chosen on the drawing"), ("pattern-reciprocal", "a step is chosen on the drawing"), ("pattern-partner", "a step is chosen on the drawing"),
        ("pattern-reads", "a step is chosen on the drawing"), ("pattern-synthesis", "a step is chosen on the drawing"), ("policy-edit", "the workflow carries a review policy"),
        ("policy-advance", "the workflow carries a review policy"), ("prepare-agent", "the owner offers use_in_conversation for the saved version"), ("agent-runs", "the saved version issues app_runs_read with app_prepare available"),
        ("inspector-part", "a step is chosen on the drawing"), ("stage-nest", "a step is chosen on the drawing"), ("stage-position", "a step is chosen on the drawing"), ("stage-nudge", "Canvas position is opened"),
        ("setting-step", "a step is chosen on the drawing"), ("setting-identity", "a step is chosen on the drawing"), ("relation-add", "a step is chosen on the drawing"),
        ("graph-mode", "the free graph is shown"), ("graph-fit", "the free graph is shown"), ("graph-center", "the free graph is shown"), ("graph-step", "the free graph is shown"),
        ("list-step", "the list of steps is shown"), ("step-list", "the free graph is shown"), ("relations", "the list of steps is shown"), ("relation-remove", "Relations is opened and the draft has an arrow"),
        ("back", "a workflow was opened from another workflow"), ("purpose-full", "the purpose is longer than its first paragraph"), ("lineage", "the saved version issues lineage_read"),
        ("saved-history", "the saved version lists recent saved versions"), ("recover", "a Save or Prepare outcome is uncertain"), ("acknowledge", "the owner answered a Save or Prepare request"),
        ("prepare-submit", "Prepare external run is opened"), ("agent-prepare-submit", "Prepare agent run is opened"), ("inspect-manuscript", "Prepare agent run is opened with manuscript choices"),
        ("adopt-guard", "Compare draft with current returned the current version"), ("context-choice", "Check execution returned the owner's context choices for the chosen step"),
        ("handoff-target", "Check execution returned the owner's hand-over fields and the chosen step passes forward"), ("prepare-step", "a preparation form is opened"),
        ("prepare-input", "Prepare agent run is opened with inspected inputs"), ("prepare-target", "Prepare agent run is opened with manuscript choices"))},
    # Wave 13 (lane-checks): the Development section renders only in an open session whose saved turns name a Work.
    **{f"development:{key}": {"states": ["global-entry"], "dynamic": True, "hidden_until": hidden} for key, hidden in (
        ("read", "a session whose saved turns name a Work is open beside the Sessions list"),
        ("cut-lane", "the development status read offers lane for the open session's Work"),
        ("discard-lane", "the development status read offers discard for the Work's ACTIVE lane"),
        ("keep-lane", "Discard the lane was pressed once"),
        ("run-check", "the development status read offers a check for a grant the open session holds"),
        ("check-targets", "an offered check profile declares targets"),
        ("more-checks", "the development status checks page issues next_read"),
        ("failing-all", "a check lists more than eight failing names"))},
    # Wave 13 (adopt): Preview and Adopt render beside an ACTIVE lane; Adopt only after a preview.
    **{f"development:{key}": {"states": ["global-entry"], "dynamic": True, "hidden_until": hidden} for key, hidden in (
        ("adopt-preview", "the development status read states an ACTIVE lane for the open session's Work"),
        ("adopt", "Preview Adopt returned the adoption owner's adopt offer (disabled with its refusals when the offer has no request)"),
        ("adopt-cancel", "Adopt was pressed once"))},
    "workflow:run-detail": {"states": ["run-detail-offered", "stop-offered", "stop-pending", "stop-resend-offered"], "dynamic": True, "hidden_until": "the compact river run issues row_projection.detail_read"},
    # C1: the app-run summary painted when Open run detail reads an owner app-dispatch run; each step reply carries its
    # child turn as data-control-owner, so the (control, owner) return coordinate is unique per step.
    **{f"workflow:{key}": {"states": ["run-detail-offered"], "dynamic": True, "hidden_until": hidden} for key, hidden in (
        ("app-run-uses", "the opened app-dispatch run summary issues its recorded-uses read"),
        ("app-run-river", "the opened app-dispatch run summary issues its observed-flow read"),
        ("app-run-reply", "a step of the opened app-dispatch run carries its exact public reply and a reader is supplied; one per step, owned by its child turn"))},
    "workflow:stop-run": {"states": ["stop-offered"], "dynamic": True, "hidden_until": "the opened research run view issues a permitted stop-run with no held original, or a newly issued request identity"},
    "workflow:stop-check": {"states": ["stop-pending", "stop-resend-offered"], "dynamic": True, "hidden_until": "a retained original Stop request carries its owner-issued request_read"},
    "workflow:stop-resend": {"states": ["stop-resend-offered"], "dynamic": True, "hidden_until": "Check read RECORDED or NONE for the exact retained attempt with its original body"},
    **{f"review-evidence:{name}":{"states":states} for name,states in (("read",["aggregate","list","support","changed"]),("list",["aggregate","list"]),("inspect",["list"]),("phase",["support"]))},
    "source:inspect":{"states":["reading"]},
    "backlog:historical":{"states":["reading"]},
    **{f"backlog:{name}":{"states":states} for name,states in (("catalogue",["catalogue","selected","planning","pending"]),("filters",["catalogue","selected","planning","pending"]),("inspect",["catalogue","selected"]),("planning",["planning"]),("check",["pending"]))},
    **{f"research:{key}": {"states": ["workspace", "source-selected"]} for key in ("representation", "timeline")},
    "research:inspect": {"states": ["focus-inspection-offered"]},
    **{f"research:{key}": {"states": states} for key, states in (("object", ["workspace", "source-selected"]), ("lens", ["workspace", "source-selected"]), ("refresh", ["workspace", "source-selected"]), ("help", ["workspace", "source-selected"]), ("action", ["workspace", "source-selected"]), ("tab", ["source-selected"]), ("input", ["source-selected"]), ("back", ["source-selected"]))},
    **{f"nav:{view}": {"states": list(_SHELL)} for view in ("overview", "work", "material", "research")},
    **{f"nav:{view}": {"states": ["project-tools-open"]} for view in ("backlog", "history", "settings", "argument", "reader-plan", "review", "presentation")},
    "nav:manuscript": {"states": list(_SHELL_WITH_MANUSCRIPT)},
    "nav:menu": {"states": ["compact-layout"]}, "workspace:menu": {"states": list(_SHELL)},
    "manuscript:outline": {"states": ["project-tools-open"], "view": "shell"},
    "manuscript:focus": {"states": ["manuscript-view"], "view": "shell", "hidden_until": "the Manuscript view"},
    "context:return": {"states": ["return-place"]}, "context:work": {"states": ["work-selected", "return-place"]}, "context:clear": {"states": ["work-selected", "return-place"]},
    "conversation:toggle": {"states": list(_SHELL)}, "help:guide": {"states": [*_SHELL, "global-entry"]},
    "reader-plan:open-in-manuscript": {"states": ["selected", "read-only"]}, "reader-plan:item": {"states": ["selected", "read-only"], "dynamic": True},
    "reader-plan:relation-map": {"states": ["selected", "read-only"]}, "reader-plan:paragraph-action": {"states": ["selected"]},
    "reader-plan:paragraph-expand": {"states": ["selected", "read-only"]}, "reader-plan:transition-expand": {"states": ["selected", "read-only"]},
    "reader-plan:acknowledge-inputs": {"states": ["selected"]}, "reader-plan:unit-select": {"states": ["selected", "read-only"], "dynamic": True}, "reader-plan:guard": {"states": ["guard-inspector"], "view": "shared"},
    "history:entry": {"states": ["timeline", "record-open"]}, "history:category": {"states": ["timeline", "record-open"]},
    "history:tab": {"states": ["timeline", "record-open"]}, "history:open-target": {"states": ["record-open"]},
    "work:item": {"states": ["catalogue", "list-open", "read-only"], "dynamic": True}, "work:next-step": {"states": ["next-action-offered"]},
    "work:prerequisites": {"states": ["selected", "read-only"]}, "work:neighbourhood": {"states": ["selected", "read-only"]}, "work:disposition": {"states": ["selected"]},
    "work:review": {"states": ["selected", "read-only"]},
    "topology:view": {"states": ["topology-plain", "topology-folded"]}, "topology:fold": {"states": ["topology-folded"]},
    "argument:record": {"states": ["record"]},
    "conversation:context": {"states": ["composer", "context-open", "options-open"]}, "conversation:turn": {"states": ["open"]},
    "conversation:artifact": {"states": ["open"]}, "conversation:target": {"states": ["composer", "context-open"]},
    "manuscript:document-setup": {"states": ["tools-open", "setup-open"]}, "manuscript:undo": {"states": ["tools-open"]},
    "manuscript:redo": {"states": ["tools-open"]}, "manuscript:template-layout": {"states": ["setup-open"]},
    "template:proof": {"states": ["template-reviewed"]}, "template:apply": {"states": ["template-reviewed"]},
    "output:document": {"states": ["not-built", "build-failed"]}, "output:derived": {"states": ["not-built", "build-failed"]},
    "settings:family": {"states": ["families"]}, "settings:stage": {"states": ["project"]}, "profile:candidate": {"states": ["preferences"]},
    "work:review-setup": {"states": ["selected"]},
    "work:continuity-continue": {"states": ["continuity-continue-offered"], "dynamic": True, "hidden_until": "the owner issues an HTTP Continue at READY with the exact basis and current Task cut, no unresolved original, not read-only"},
    "work:continuity-proof": {"states": ["continuity-proof-offered"], "dynamic": True, "hidden_until": "the owner issues a fillable proof template with its HTTP route and current Task cut, no unresolved original, not read-only"},
    "work:continuity-check": {"states": ["continuity-unresolved"], "dynamic": True, "hidden_until": "a retained uncertain or checked original continuity request exists"},
    "work:continuity-resend": {"states": ["continuity-resend-offered"], "dynamic": True, "hidden_until": "the owner check read NONE and the exact original wire is retained, not read-only"},
    "work:continuity-review": {"states": ["continuity-review-offered"], "dynamic": True, "hidden_until": "the owner names a review phase and an existing recorder is permitted"},
    "work:continuity-retry": {"states": ["continuity-read-failed"], "dynamic": True, "hidden_until": "the continuity summary GET failed"},
    "review:responses": {"states": ["comments", "note-draft", "comments-closed", "comments-paged", "comments-focus"], "dynamic": True, "hidden_until": "a saved comment has an exact origin for review routing"},
    "material:add-document": {"states": ["files", "readers-open", "bindings", "retained-source"]},
    "material:add-literature": {"states": ["retained-source"], "dynamic": True, "hidden_until": "a retained same-project original offers Add to Literature"},
    "conversation:add-document": {"states": ["composer", "context-open", "options-open"]},
    "conversation:next-message": {"states": ["composer", "context-open", "options-open"]},
    "material:reader": {"states": ["readers-open"]}, "material:file": {"states": ["files", "readers-open", "bindings", "retained-source"], "dynamic": True}, "material:binding": {"states": ["bindings", "retained-source"], "dynamic": True},
    "research:result": {"states": ["results"]},
    "help:layer": {"states": ["help-open"]}, "help:close": {"states": ["help-open"]}, "help:task": {"states": ["help-open"]}, "help:diagram": {"states": ["help-open"]},
    "help:cue": {"states": ["cue-running"]},
    # WAVE 11 CENSUS REPAIRS
    "conversation:send": {"states": ["composer", "context-open", "options-open"]},
    "sessions:send": {"states": ["global-entry"], "dynamic": True, "hidden_until": "a session is open beside the Sessions list"},
    "research:conversation": {"states": ["workspace", "source-selected"]},
    "research:save-view": {"states": ["workspace", "source-selected"]}, "research:open-view": {"states": ["workspace", "source-selected"]},
    "work:step-waits-on": {"states": ["continuity-continue-offered", "continuity-proof-offered", "continuity-review-offered"], "dynamic": True, "hidden_until": "the selected task's continuity Next issues its own detail read"},
    "work:containment-save": {"states": ["selected"]}, "work:attempt": {"states": ["selected"]},
    "work:compare": {"states": ["draft-compared"], "dynamic": True, "hidden_until": "an authored-work draft's basis changed and Compare with the current work was pressed"},
    "work:result": {"states": ["result-offered"], "dynamic": True, "hidden_until": "a completed task has exactly one recorded comment route with its read and origin"},
    "settings:save-defaults": {"states": ["project"], "hidden_until": "Change future defaults is opened and the providers read has answered"},
    # ---- wave 13 id sweep: states (begin) ----
    **{key: {'states': ['cold-entry', 'work-selected', 'return-place', 'manuscript-view', 'help-open', 'cue-running', 'manuscript-unavailable', 'compact-layout', 'project-tools-open', 'switcher-open', 'more-open', 'global-entry']} for key in ("frame:menu", "frame:switch", "frame:more",)},
    **{key: {'states': ['cold-entry', 'work-selected', 'return-place', 'manuscript-view', 'help-open', 'cue-running', 'manuscript-unavailable', 'compact-layout', 'project-tools-open', 'switcher-open', 'more-open', 'global-entry'], 'dynamic': True, 'hidden_until': "the place's own page is not the one open, and for All tasks a project is open (outside a project All tasks is nav:backlog)"} for key in ("frame:place",)},
    **{key: {'states': ['cold-entry', 'work-selected', 'return-place', 'manuscript-view', 'help-open', 'cue-running', 'manuscript-unavailable', 'compact-layout', 'project-tools-open', 'switcher-open', 'more-open'], 'dynamic': True, 'hidden_until': "the narrow menu lists the places (a workspace page's Menu panel, or the project navigation's top block)"} for key in ("frame:menu-place",)},
    **{key: {'states': ['cold-entry', 'work-selected', 'return-place', 'manuscript-view', 'help-open', 'cue-running', 'manuscript-unavailable', 'compact-layout', 'project-tools-open', 'switcher-open', 'more-open']} for key in ("frame:menu-help",)},
    **{key: {'states': ['more-open'], 'dynamic': True, 'hidden_until': 'More is opened'} for key in ("frame:more-page",)},
    **{key: {'states': ['switcher-open']} for key in ("frame:switch-all", "frame:switch-create",)},
    **{key: {'states': ['switcher-open'], 'dynamic': True, 'hidden_until': 'the switcher is opened and /projects/library has answered'} for key in ("frame:switch-row",)},
    **{key: {'states': ['global-entry'], 'dynamic': True, 'hidden_until': 'the page address carries the project to return to'} for key in ("frame:return",)},
    **{key: {'states': ['cold-entry', 'work-selected', 'return-place', 'manuscript-view', 'help-open', 'cue-running', 'manuscript-unavailable', 'compact-layout', 'project-tools-open', 'switcher-open', 'more-open']} for key in ("nav:more-tools",)},
    **{key: {'states': ['page']} for key in ("now:all-sessions", "now:all-tasks", "now:all-projects", "now:open-all-tasks", "now:create-project", "now:bring-manuscript",)},
    **{key: {'states': ['page'], 'dynamic': True, 'hidden_until': 'the live-work read, the catalogue read or the library read lists that row'} for key in ("now:open-running", "now:open-task", "now:open-suggested-task", "now:project-writing", "now:project-tasks", "now:project-open",)},
    **{key: {'states': ['timeline', 'record-open', 'panels-open']} for key in ("history:actor",)},
    **{key: {'states': ['selected', 'next-action-offered', 'panels-open']} for key in ("work:close", "work:edit-open", "work:status-open", "work:use-for-message", "work:related-turns", "work:authored-open", "work:containment-open", "work:disposition-open", "work:evidence-paths", "work:save-authored", "work:save-status",)},
    **{key: {'states': ['catalogue']} for key in ("work:nav-filter",)},
    **{key: {'states': ['workspace', 'source-selected']} for key in ("research:saved-view-choice", "research:overview", "research:browse", "research:selected-inputs", "research:outline-toggle", "research:inspector-toggle", "research:orientation", "research:saved-views", "research:panel-sizes",)},
    **{key: {'states': ['catalogue']} for key in ("backlog:add-task-open", "backlog:guide", "backlog:queue-active", "backlog:queue-all", "backlog:source-contracts", "backlog:historical-open", "backlog:filter-options", "backlog:refresh", "backlog:row-details",)},
    **{key: {'states': ['catalogue'], 'dynamic': True, 'hidden_until': 'the catalogue read carries a suggested_next in the SUGGESTED state'} for key in ("backlog:suggested",)},
    **{key: {'states': ['catalogue'], 'dynamic': True, 'hidden_until': 'the catalogue read offers its query_action fields'} for key in ("backlog:filter",)},
    **{key: {'states': ['catalogue'], 'dynamic': True, 'hidden_until': 'the task row carries a planning_read'} for key in ("backlog:plan",)},
    **{key: {'states': ['catalogue'], 'dynamic': True, 'hidden_until': 'the catalogue read says more rows remain'} for key in ("backlog:more",)},
    **{key: {'states': ['catalogue'], 'dynamic': True, 'hidden_until': 'the catalogue read lists historical obligations'} for key in ("backlog:historical-records",)},
    **{key: {'states': ['catalogue'], 'dynamic': True, 'hidden_until': 'Add task in a project is opened'} for key in ("backlog:add-task-in",)},
    **{key: {'states': ['catalogue'], 'hidden_until': 'Add task in a project is opened and no project is registered'} for key in ("backlog:add-task-create",)},
    **{key: {'states': ['page']} for key in ("projects:task-write", "projects:task-source", "projects:task-tasks", "projects:task-open", "projects:create-toggle", "projects:create", "projects:find-existing", "projects:category",)},
    **{key: {'states': ['page']} for key in ("owners:find",)},
    **{key: {'states': ['page'], 'dynamic': True, 'hidden_until': 'the owner read offers a next read (an owner, its explanation, an input, a page)'} for key in ("owners:read",)},
    **{key: {'states': ['page']} for key in ("dependencies:filter", "dependencies:coverage", "dependencies:refresh", "dependencies:more", "dependencies:open-material", "dependencies:consumer",)},
    **{key: {'states': ['page'], 'dynamic': True, 'hidden_until': 'the dependency read lists that binding'} for key in ("dependencies:inspect", "dependencies:open-binding",)},
    **{key: {'states': ['families']} for key in ("settings:category-models", "settings:category-voice", "settings:category-architecture", "settings:category-runtime", "settings:category-storage", "settings:refresh-providers", "settings:model-policy-source",)},
    **{key: {'states': ['families'], 'dynamic': True, 'hidden_until': 'the provider catalogue lists that provider'} for key in ("settings:provider-models",)},
    **{key: {'states': ['ready', 'panels-open']} for key in ("home:continue-writing",)},
    **{key: {'states': ['panels-open']} for key in ("home:writing-file-details", "home:edit-argument", "home:work-argument", "home:argument-open", "home:edit-brief", "home:save-framing", "home:save-argument", "home:form",)},
    **{key: {'states': ['ready', 'no-manuscript', 'panels-open']} for key in ("home:open-tasks", "home:open-questions", "home:all-activity", "home:open-conversation", "home:guided-tour", "home:brief", "home:document-setup", "home:edit-title",)},
    **{key: {'states': ['panels-open'], 'dynamic': True, 'hidden_until': 'a recent activity row carries an event id'} for key in ("home:read-event-record",)},
    **{key: {'states': ['ready', 'no-manuscript', 'panels-open'], 'dynamic': True, 'hidden_until': 'a recent activity row names a destination that is available'} for key in ("home:recent-open",)},
    **{key: {'states': ['ready', 'no-manuscript', 'panels-open'], 'dynamic': True, 'hidden_until': 'a recent activity row is listed'} for key in ("home:event-details",)},
    **{key: {'states': ['project', 'panels-open']} for key in ("settings:refresh", "settings:edit-writing", "settings:future-defaults", "settings:identities",)},
    **{key: {'states': ['panels-open']} for key in ("settings:inspect-history", "settings:stage-use", "settings:stage-refresh", "settings:profile-identities",)},
    **{key: {'states': ['project', 'panels-open'], 'dynamic': True, 'hidden_until': 'Change future defaults is opened and the providers read has answered'} for key in ("settings:default-select",)},
    **{key: {'states': ['project', 'panels-open']} for key in ("settings:storage",)},
    **{key: {'states': ['panels-open']} for key in ("settings:storage-measure",)},
    **{key: {'states': ['bindings', 'retained-source', 'panels-open']} for key in ("material:refresh-sources", "material:refresh-shared", "material:file-manage", "material:owner", "material:owner-type",)},
    **{key: {'states': ['files', 'readers-open', 'bindings', 'retained-source', 'panels-open']} for key in ("material:file-more", "material:link-options", "material:readers",)},
    **{key: {'states': ['bindings', 'retained-source', 'panels-open'], 'disabled_until': "the source's revision has been inspected"} for key in ("material:prepare-reader",)},
    **{key: {'states': ['bindings', 'retained-source', 'panels-open'], 'disabled_until': "the binding's source has been inspected"} for key in ("material:adopt",)},
    **{key: {'states': ['panels-open']} for key in ("material:remove-reference", "material:discuss", "material:file-history",)},
    **{key: {'states': ['bindings', 'retained-source', 'panels-open'], 'disabled_until': 'a material path is typed'} for key in ("material:inspect",)},
    **{key: {'states': ['bindings', 'retained-source', 'panels-open'], 'disabled_until': 'the material you described has been inspected'} for key in ("material:link",)},
    **{key: {'states': ['files', 'readers-open', 'bindings', 'retained-source', 'panels-open'], 'dynamic': True, 'hidden_until': 'the project has a recorded file'} for key in ("material:read",)},
    **{key: {'states': ['panels-open'], 'dynamic': True, 'hidden_until': 'the project has a shared material binding'} for key in ("material:inspect-binding",)},
    **{key: {'states': ['pending', 'empty', 'comments', 'panels-open', 'note-draft', 'comments-closed', 'comments-paged', 'comments-focus', 'page-failed', 'proposals-more']} for key in ("review:refresh", "review:commission",)},
    **{key: {'states': ['pending', 'empty', 'comments', 'panels-open', 'note-draft', 'comments-closed', 'comments-paged', 'comments-focus', 'page-failed', 'proposals-more'], 'dynamic': True, 'hidden_until': 'the review owner offers that list'} for key in ("review:filter",)},
    **{key: {'states': ['empty', 'panels-open'], 'dynamic': True, 'hidden_until': 'the project offers that reader'} for key in ("research:tab",)},
    **{key: {'states': ['results', 'empty', 'panels-open']} for key in ("research:experiment-open",)},
    **{key: {'states': ['panels-open']} for key in ("research:develop-experiment", "research:develop-visual",)},
    **{key: {'states': ['results', 'empty']} for key in ("research:figures-open",)},
    **{key: {'states': ['timeline', 'record-open', 'panels-open'], 'disabled_until': 'the Graphs tab is the one open (Changes is disabled while it is current)'} for key in ("history:tab-changes",)},
    **{key: {'states': ['panels-open']} for key in ("history:tab-graphs", "history:coverage",)},
    **{key: {'states': ['timeline', 'record-open', 'panels-open']} for key in ("history:refresh", "history:overview",)},
    **{key: {'states': ['not-built', 'build-failed', 'panels-open']} for key in ("output:build", "output:develop-figure", "output:document-setup",)},
    **{key: {'states': ['not-built', 'build-failed', 'panels-open']} for key in ("output:build-details",)},
    **{key: {'states': ['panels-open']} for key in ("output:refresh-derived",)},
    **{key: {'states': ['empty', 'selected', 'read-only']} for key in ("reader-plan:refresh",)},
    **{key: {'states': ['empty']} for key in ("reader-plan:create-item",)},
    **{key: {'states': ['catalogue', 'selected', 'next-action-offered', 'panels-open']} for key in ("work:flat-catalogue",)},
    **{key: {'states': ['read-only', 'panels-open']} for key in ("work:namespaces", "work:dev-workflows",)},
    **{key: {'states': ['selected', 'read-only', 'next-action-offered', 'panels-open']} for key in ("work:progress-open", "work:reinspect", "work:completion-basis",)},
    **{key: {'states': ['panels-open']} for key in ("work:status-details",)},
    **{key: {'states': ['panels-open'], 'dynamic': True, 'hidden_until': 'the task has a containing task'} for key in ("work:open-parent",)},
    **{key: {'states': ['selected', 'next-action-offered', 'panels-open'], 'hidden_until': 'Update task status is opened'} for key in ("work:status-choice",)},
    **{key: {'states': ['catalogue', 'selected', 'next-action-offered', 'panels-open']} for key in ("tasks:add-summary",)},
    **{key: {'states': ['panels-open']} for key in ("tasks:add-more", "tasks:add-submit", "tasks:add-exact", "tasks:add-type", "tasks:add-prerequisites", "tasks:add-parent",)},
    **{key: {'states': ['selected', 'read-only', 'next-action-offered', 'panels-open'], 'dynamic': True, 'hidden_until': 'the relations panel lists that task'} for key in ("work:relation-open",)},
    **{key: {'states': ['selected', 'read-only', 'next-action-offered', 'panels-open'], 'dynamic': True, 'hidden_until': 'the open task has a relations panel'} for key in ("work:relation-tab",)},
    **{key: {'states': ['topology-plain', 'topology-folded']} for key in ("topology:zoom-out", "topology:zoom-in", "topology:fit",)},
    **{key: {'states': ['topology-plain', 'topology-folded'], 'dynamic': True, 'hidden_until': 'the topology lists that node'} for key in ("topology:node",)},
    **{key: {'states': ['panels-open']} for key in ("argument:overview", "argument:map", "argument:reader-plan", "argument:add-object",)},
    **{key: {'states': ['opening', 'write', 'setup-open']} for key in ("writing:mode-write", "writing:mode-tex", "writing:tools",)},
    **{key: {'states': ['opening', 'write', 'setup-open'], 'disabled_until': 'a built PDF exists'} for key in ("writing:mode-pdf",)},
    **{key: {'states': ['setup-open']} for key in ("writing:build", "writing:build-details", "writing:file-history", "writing:setup", "writing:build-log", "writing:build-basis", "writing:open-root",)},
    **{key: {'states': ['panels-open']} for key in ("history:telemetry-limits", "history:overview-details", "history:measurement-limits",)},
    **{key: {'states': ['panels-open'], 'dynamic': True, 'hidden_until': 'the telemetry read issues a filter for that bar, cell or bucket'} for key in ("history:telemetry-filter",)},
    **{key: {'states': ['panels-open'], 'dynamic': True, 'hidden_until': 'the telemetry read lists values for that scope'} for key in ("history:telemetry-select",)},
    **{key: {'states': ['panels-open'], 'hidden_until': 'the telemetry read lists recorded tool calls'} for key in ("history:tool-view",)},
    **{key: {'states': ['panels-open']} for key in ("argument:find", "argument:search", "argument:inventory", "argument:containment-all", "argument:containment-basis", "argument:organise", "argument:uncontained", "argument:changes", "argument:history-basis", "argument:add-part", "argument:group",)},
    **{key: {'states': ['panels-open'], 'dynamic': True, 'hidden_until': 'the owner lists that part'} for key in ("argument:move-part",)},
    **{key: {'states': ['panels-open'], 'dynamic': True, 'hidden_until': 'the owner lists that object'} for key in ("argument:object",)},
    # ---- second pass ----
    **{key: {'states': ['seeded']} for key in ("home:open-next-task", "work:subtasks", "work:more-tasks", "work:more-work", "work:history-read", "work:action-context", "work:location-deeper", "work:progress-basis", "work:choose-evidence", "argument:read-authored", "settings:unverified-processes", "output:reader-plan-absence")},
    **{key: {'states': ['seeded'], 'dynamic': True, 'hidden_until': 'the owner supplies that row'} for key in ("work:namespace-read", "work:action-inspect", "work:action-template", "work:location-open", "work:progress-read")},
    **{key: {'states': ['seeded'], 'disabled_until': 'the owner reports the cleanup available, at least one empty unused folder, and the confirmation box is ticked'} for key in ("settings:cleanup-remove",)},
    **{key: {'states': ['catalogue']} for key in ("research:compare-selection", "research:object-kind", "research:more-objects", "research:availability-reason")},
    **{key: {'states': ['setup-open'], 'dynamic': True, 'hidden_until': 'the owner lists that document file'} for key in ("writing:setup-file",)},
    **{key: {'states': ['running-now'], 'dynamic': True, 'hidden_until': 'the conversation owner observes a turn running for this project'} for key in ("nav:live-task", "nav:live-conversation")},
    **{key: {'states': ['topology-plain', 'topology-folded'], 'dynamic': True, 'hidden_until': 'the topology lists a relationship whose end is an object this view can select or read'} for key in ("topology:relation",)},
    **{key: {'states': ['topology-plain'], 'dynamic': True, 'hidden_until': 'a relationship comes in from outside the page and its owner offers a read'} for key in ("topology:relation-source",)},
    **{key: {'states': ['page'], 'dynamic': True, 'hidden_until': 'the owner lists that project'} for key in ("now:project-title", "projects:project")},
    **{key: {'states': ['seeded'], 'dynamic': True, 'hidden_until': 'the Work owner lists that task on Home'} for key in ("home:task-title",)},
    **{key: {'states': ['panels-open'], 'dynamic': True, 'hidden_until': 'the owner lists that shared material binding and its Manage panel is opened'} for key in ("material:open-owner",)},
    **{key: {'states': ['timeline', 'record-open', 'panels-open']} for key in ("history:download-state",)},
    **{key: {'states': ['page'], 'dynamic': True, 'hidden_until': 'the dependency read lists that binding'} for key in ("dependencies:open-record",)},
    # ---- wave 13 id sweep: states (end) ----
}
# ---- wave 13 id sweep: extra states (begin) ----
_WAVE13_EXTRA_STATES = {
 "history:category": [
  "panels-open"
 ],
 "history:entry": [
  "panels-open"
 ],
 "history:tab": [
  "panels-open"
 ],
 "material:add-document": [
  "panels-open"
 ],
 "material:binding": [
  "panels-open"
 ],
 "material:file": [
  "panels-open"
 ],
 "material:reader": [
  "panels-open"
 ],
 "output:derived": [
  "panels-open"
 ],
 "output:document": [
  "panels-open"
 ],
 "research:result": [
  "panels-open"
 ],
 "settings:save-defaults": [
  "panels-open"
 ],
 "settings:stage": [
  "panels-open"
 ],
 "tasks:add": [
  "panels-open"
 ],
 "tasks:add-open": [
  "panels-open"
 ],
 "work:attempt": [
  "panels-open"
 ],
 "work:containment-save": [
  "panels-open"
 ],
 "work:disposition": [
  "panels-open"
 ],
 "work:item": [
  "panels-open"
 ],
 "work:neighbourhood": [
  "panels-open"
 ],
 "work:next-step": [
  "panels-open"
 ],
 "work:prerequisites": [
  "panels-open"
 ],
 "work:review": [
  "panels-open"
 ],
 "work:review-setup": [
  "panels-open"
 ]
}
for _ident, _more in _WAVE13_EXTRA_STATES.items():
    CONTROL_STATES[_ident]["states"] = [*CONTROL_STATES[_ident]["states"], *_more]
    # ---- wave 13 id sweep: extra states (end) ----
# ---- wave 13 id sweep: earlier controls that also render in a state added this wave (begin) ----
_WAVE13_ALSO_RENDERED: dict[str, list[str]] = {
    "not-built": [
        "output:reader-plan-absence"
    ],
    "build-failed": [
        "output:reader-plan-absence"
    ],
    "seeded": [
        "task:trail",
        "home:continue-writing",
        "argument:overview",
        "settings:stage",
        "output:document",
        "tasks:add-open",
        "home:edit-argument",
        "argument:map",
        "settings:save-defaults",
        "output:derived",
        "tasks:add",
        "home:work-argument",
        "argument:reader-plan",
        "settings:refresh",
        "output:build",
        "work:item",
        "home:argument-open",
        "argument:add-object",
        "settings:edit-writing",
        "output:develop-figure",
        "work:prerequisites",
        "home:edit-brief",
        "argument:find",
        "settings:future-defaults",
        "output:document-setup",
        "work:neighbourhood",
        "home:save-framing",
        "argument:search",
        "settings:identities",
        "output:build-details",
        "work:disposition",
        "home:save-argument",
        "argument:inventory",
        "settings:inspect-history",
        "output:refresh-derived",
        "work:review-setup",
        "home:form",
        "argument:containment-all",
        "settings:stage-use",
        "work:step-waits-on",
        "home:open-tasks",
        "argument:containment-basis",
        "settings:stage-refresh",
        "work:containment-save",
        "home:open-questions",
        "argument:organise",
        "settings:profile-identities",
        "work:attempt",
        "home:all-activity",
        "argument:uncontained",
        "settings:default-select",
        "work:close",
        "home:open-conversation",
        "argument:changes",
        "settings:storage",
        "work:edit-open",
        "home:guided-tour",
        "argument:history-basis",
        "settings:storage-measure",
        "work:status-open",
        "home:brief",
        "argument:add-part",
        "work:use-for-message",
        "home:document-setup",
        "argument:group",
        "work:related-turns",
        "home:edit-title",
        "argument:move-part",
        "work:authored-open",
        "home:read-event-record",
        "argument:object",
        "work:containment-open",
        "home:recent-open",
        "work:disposition-open",
        "home:event-details",
        "work:evidence-paths",
        "work:save-authored",
        "work:save-status",
        "work:nav-filter",
        "work:flat-catalogue",
        "work:namespaces",
        "work:dev-workflows",
        "work:progress-open",
        "work:reinspect",
        "work:completion-basis",
        "work:status-details",
        "work:open-parent",
        "work:status-choice",
        "tasks:add-summary",
        "tasks:add-more",
        "tasks:add-submit",
        "tasks:add-exact",
        "tasks:add-type",
        "tasks:add-prerequisites",
        "tasks:add-parent",
        "work:relation-tab"
    ],
    "catalogue": [
        "research:object",
        "research:lens",
        "research:action",
        "research:refresh",
        "research:help",
        "research:representation",
        "research:timeline",
        "research:conversation",
        "research:save-view",
        "research:open-view",
        "research:saved-view-choice",
        "research:overview",
        "research:browse",
        "research:selected-inputs",
        "research:outline-toggle",
        "research:inspector-toggle",
        "research:orientation",
        "research:saved-views",
        "research:panel-sizes"
    ],
    "panels-open": [
        "research:figures-open",
        "output:reader-plan-absence"
    ],
    "running-now": [
        "conversation:toggle",
        "frame:menu",
        "frame:menu-help",
        "frame:menu-place",
        "frame:more",
        "frame:place",
        "frame:switch",
        "help:guide",
        "nav:manuscript",
        "nav:material",
        "nav:more-tools",
        "nav:overview",
        "nav:research",
        "nav:skip",
        "nav:work",
        "workspace:menu"
    ]
}
for _state, _idents in _WAVE13_ALSO_RENDERED.items():
    for _ident in _idents:
        if _state not in CONTROL_STATES[_ident]["states"]:
            CONTROL_STATES[_ident]["states"] = [*CONTROL_STATES[_ident]["states"], _state]
# ---- wave 13 id sweep: earlier controls that also render in a state added this wave (end) ----
for _ident, _extra in CONTROL_STATES.items():
    _row = CONTROL_DECLARATIONS[_ident]
    if _row["view"] == "work" and "selected" in _extra["states"]:
        _extra["states"] = [*_extra["states"], "next-action-offered"]
    if "view" in _extra:
        _row["view"] = _extra["view"]
    _row["states"] = list(_extra["states"])
    _row["dynamic"] = bool(_extra.get("dynamic", False))
    if "hidden_until" in _extra:
        _row["hidden_until"] = _extra["hidden_until"]
    if "disabled_until" in _extra:
        _row["disabled_until"] = _extra["disabled_until"]
# ---- wave 13 id sweep: guide sentences for rows declared before this wave (begin) ----
# A guide sentence says what pressing the control does, in plain words; the page never carries its own copy (R12).
_WAVE13_DOES = {
    "nav:skip": "Moves the keyboard focus past the navigation to the page's main content. Nothing is changed.",
    "task:trail": "Opens what led to this task: the owner's recorded trail of the work that came before it. It only reads.",
    "writing:sources": "Shows or hides the Sources panel beside the writing page, so a source can be read next to the text. Nothing is changed.",
    "help:read-guide": "Opens the chosen guide in the help layer. Nothing is changed.",
    "tasks:add-open": "Opens the form for a new task, with the cursor in its title. Nothing is created until the form's own Add task is pressed.",
    "tasks:add": "Holds the new task form: title, completion condition, and under it the type, containing task and prerequisites. Nothing is created until Add task is pressed.",
    "workflow:purpose": "Shows or hides the workflow's full purpose text. Nothing is changed.",
    "workflow:saved-read": "Reads the exact body of this saved version of the workflow and shows it. It only reads.",
    "workflow:saved-close": "Closes the saved version being read and returns to the design. Nothing is changed.",
    "workflow:history": "Lists the saved versions of this workflow, newest first, from the owner's history. It only reads.",
    "workflow:history-next": "Reads the next, older page of saved versions from the owner's own continuation. It only reads.",
    "workflow:saved-next": "Reads the next part of a saved version too long to show at once, from the owner's continuation. It only reads.",
    "workflow:saved-workspace": "Opens the complete saved version as an object in Workspace. Nothing is changed.",
    "workflow:design": "Shows this workflow's design: its steps and settings. Nothing is changed.",
    "workflow:runs": "Shows the runs of this workflow and what each did. Nothing is changed.",
    "workflow:guide": "Shows how a design becomes a saved version, a prepared request and an admitted run; saving does not start work. Nothing is changed.",
    "workflow:discard": "Throws away the edits made in this design that are not yet saved and returns to the saved version. Anything already saved stays.",
    "workflow:adapt": "Starts a new draft from the saved version shown, through the choices the owner offers for a new workflow. The saved version itself is not changed.",
    "workflow:lineage-prepare": "Asks the owner to prepare the complete lineage of this workflow for export, when its lineage description permits it. Nothing is changed in the workflow.",
    "workflow:preview": "Asks the owner whether this workflow could run as designed and shows its answer. Nothing is started.",
    "workflow:context-read": "Reads the context a checked step declares and shows it. It only reads.",
    "workflow:uses": "Reads where this saved version was recorded as used and shows the first page. It only reads.",
    "workflow:river": "Reads the observed flow of a listed run: which steps ran and what passed between them. It only reads.",
    "workflow:uses-more": "Reads the next page of recorded uses from the owner's continuation. It only reads.",
    "workflow:river-more": "Reads the next page of the observed flow from the owner's continuation. It only reads.",
    "workflow:river-read": "Reads one recorded response, proposal, return or run named in the flow and shows it. It only reads.",
    "workflow:run-detail": "Opens the owner's full record of this run beside its summary. It only reads.",
    "workflow:app-run-uses": "Reads where the opened run was recorded as used. It only reads.",
    "workflow:app-run-river": "Reads the observed flow of the opened run. It only reads.",
    "workflow:app-run-reply": "Reads the exact reply one step of the opened run gave. It only reads.",
    "workflow:withdraw": "Asks the owner to withdraw a save or preparation whose outcome is not known, so it cannot happen later. It sends the owner's own withdrawal offer.",
    "workflow:stop-run": "Asks the owner to stop this run. The run stops only if the owner records it; the page says what the owner answered.",
    "workflow:stop-check": "Asks the owner whether the Stop request already sent was recorded. It only reads.",
    "workflow:stop-resend": "Sends the original Stop request again, unchanged, after the owner's check shows it was not recorded or recorded nothing.",
    "review-evidence:read": "Opens the evidence behind this review's standing from the owner's records. It only reads.",
    "review-evidence:list": "Lists the review obligations and what each is waiting for, from the owner's records. It only reads.",
    "review-evidence:inspect": "Reads the routes that lead to the evidence for one obligation. It only reads.",
    "review-evidence:phase": "Reads the exact record of one review phase. It only reads.",
    "source:inspect": "Opens the Source inspector: the Source owner's record of which sources this task consumed and how current they are. It only reads.",
    "backlog:historical": "Shows or hides the engine obligations recorded before this app; each is read as the owner holds it. Nothing is changed.",
    "backlog:catalogue": "Shows every task in the workspace as the owner lists it, one page at a time. Nothing is changed.",
    "backlog:filters": "Narrows the list of all tasks by the fields the owner offers for filtering. Nothing is changed.",
    "backlog:inspect": "Opens one task from the list of all tasks, with its full record. It only reads.",
    "backlog:planning": "Saves the planning fields of this task through the owner. The page says what the owner recorded.",
    "backlog:check": "Asks the owner whether the planning save already sent was recorded. It only reads.",
    "research:object": "Chooses which research object the workspace shows. Nothing is changed.",
    "research:lens": "Chooses an optional project to read the object against. Nothing is changed.",
    "research:input": "Includes the shown object projection as an input to the next action. Nothing is sent until an action is run.",
    "research:action": "Runs one action the owner offers on the shown object. The owner's answer is shown beside it.",
    "research:back": "Returns to the object shown before this one. Nothing is changed.",
    "research:refresh": "Reads the research workspace again from its owners. Nothing is changed.",
    "research:help": "Shows or hides help for the research workspace. Nothing is changed.",
    "research:representation": "Switches between the relation map, relation outline, timeline and reading and editor views of the same objects. Nothing is changed.",
    "research:timeline": "Shows the recorded timeline of the shown objects. Nothing is changed.",
    "research:inspect": "Opens the focused object for inspection, using the read its owner offers. It only reads.",
    "nav:backlog": "Opens All tasks for this project. Nothing is changed.",
    "nav:overview": "Opens the project's Home page. Nothing is changed.",
    "nav:work": "Opens the project's Tasks. Nothing is changed.",
    "nav:material": "Opens the project's Sources: its files, readers and references. Nothing is changed.",
    "nav:history": "Opens Activity: what changed in the project and when. Nothing is changed.",
    "nav:settings": "Opens the project's Settings. Nothing is changed.",
    "nav:argument": "Opens Argument and evidence: the project's claims and what supports them. Nothing is changed.",
    "nav:reader-plan": "Opens the Reader plan: the order in which the paper is meant to be read. Nothing is changed.",
    "nav:research": "Opens Research: the project's results and producers. Nothing is changed.",
    "nav:manuscript": "Opens Writing: the manuscript, as source, TeX or PDF. Nothing is changed.",
    "nav:review": "Opens Review and notes: proposed changes and comments. Nothing is changed.",
    "nav:presentation": "Opens Figures and output: the manuscript PDF and derived outputs. Nothing is changed.",
    "nav:menu": "Shows or hides the project navigation on a narrow window. Nothing is changed.",
    "workspace:menu": "Opens the workspace places: Projects, Workspace activity, Workspace dependencies, System owners and App settings. Nothing is changed.",
    "manuscript:outline": "Shows or hides the outline of the manuscript beside the page. Nothing is changed.",
    "manuscript:focus": "Hides the navigation so only the manuscript shows, and brings it back when pressed again. Nothing is changed.",
    "context:return": "Returns to the place you came from before opening this reading. Nothing is changed.",
    "context:work": "Goes to the task the conversation and messages are currently about. Nothing is changed.",
    "context:clear": "Stops treating that task as the subject of the next message. The task itself is not changed.",
    "conversation:toggle": "Shows or hides the conversation panel beside the page. Nothing is sent.",
    "help:guide": "Shows or hides the help layer for the page you are on. Nothing is changed.",
    "reader-plan:open-in-manuscript": "Opens the file the selected section was read from, at its heading when the owner knows it, else the file or the owner's suggested file; the label says which. Nothing is changed.",
    "reader-plan:item": "Selects one plan row and shows its detail, as the owner holds it. Nothing is changed.",
    "reader-plan:relation-map": "Shows or hides the map of how the plan's parts relate; it is read when opened. Nothing is changed.",
    "reader-plan:paragraph-action": "Opens one paragraph's plan action (edit, move or remove) on a read of that paragraph. Nothing is changed until the action is confirmed.",
    "reader-plan:guard": "Opens a read-only view of one saved guard subject. Nothing is changed.",
    "history:entry": "Opens one activity record to show its exact details. It only reads.",
    "history:category": "Chooses which category of activity the timeline lists; manuscript activity is the default. Nothing is changed.",
    "history:tab": "Switches between the list of changes and the graphs drawn from the same record. Nothing is changed.",
    "history:open-target": "Opens the object an activity record affected, when the record names one. Nothing is changed.",
    "work:item": "Opens one task from the list, with its detail. It only reads.",
    "work:next-step": "Runs the one next step the owner offers for a blocked task. The owner's answer is shown beside it.",
    "work:prerequisites": "Shows every prerequisite of this task with its own standing, as the owner records them. Nothing is changed.",
    "work:neighbourhood": "Shows the tasks related to this one as a graph and a list, read one page at a time. Nothing is changed.",
    "work:disposition": "Opens the form for recording what became of this task. Nothing is recorded until the form is sent.",
    "work:review": "Shows the review lifecycle of this task and the phase recorder the owner permits. Nothing is changed.",
    "work:review-setup": "Opens the setup form for the reviews this task needs. Nothing is started until it is sent.",
    "work:continuity-continue": "Continues this task to the approved review through the request the owner issued. The owner's answer is shown beside it.",
    "work:continuity-proof": "Opens the form for attaching proof that the work arrived, using the owner's issued template. Nothing is sent until the form is.",
    "work:continuity-check": "Asks the owner whether the original request, whose outcome is not known, was recorded. It only reads.",
    "work:continuity-resend": "Sends the original request again, unchanged, after the owner's check shows it was not recorded. It is never sent automatically.",
    "work:continuity-review": "Opens the review form for the phase the owner names. Nothing is recorded until it is sent.",
    "work:continuity-retry": "Reads the task's progress again after the first read failed. It only reads.",
    "review:responses": "Opens the review route for this saved comment: Request reviews when none exists, Review responses when one does. Nothing is sent by opening it.",
    "topology:view": "Shows the typed relationships between objects as a drawing and a list. Nothing is changed.",
    "argument:record": "Shows or hides the record of one argument object: its kind, title, proof and formal standing. Nothing is changed.",
    "conversation:context": "Shows what the next message will carry as context, as the owner reads it. It only reads.",
    "manuscript:document-setup": "Shows or hides Document setup: the files the build uses and the exact build basis. Nothing is changed.",
    "manuscript:undo": "Undoes the last edit in the editor. The document changes only through the editor's own save.",
    "manuscript:redo": "Restores the edit just undone in the editor. The document changes only through the editor's own save.",
    "manuscript:template-layout": "Opens the template and layout choices the owner offers for this document. Nothing is changed until one is applied.",
    "template:proof": "Shows or hides the reviewed proof: the build receipt and PDF that applying the template binds. Nothing is changed.",
    "template:apply": "Applies the reviewed template preview to the document through the owner. It is enabled only for the reviewed proof.",
    "output:document": "Shows or hides the manuscript PDF card: its state, when it was built and the Build button. Nothing is changed.",
    "output:derived": "Shows or hides the derived output card: its state and its build. Nothing is changed.",
    "conversation:turn": "Shows or hides the facets of one turn: saved changes, failed attempts and the reply's standing. Nothing is changed.",
    "conversation:artifact": "Shows or hides the artifacts one turn saved. Nothing is changed.",
    "conversation:target": "Shows or hides what the next message is aimed at: its target, the reading attached and its intent. Nothing is changed.",
    "settings:family": "Shows or hides one family of settings with the scope it comes from and what it affects. Nothing is changed.",
    "settings:stage": "Shows or hides the guidance for one writing stage, in place. Nothing is changed.",
    "profile:candidate": "Opens one saved preference suggestion so it can be compared before it is applied. Nothing is changed.",
    "material:add-document": "Opens the form for adding a local document. No file is chosen or uploaded until the form is used.",
    "material:add-literature": "Opens the form for adding a retained original to Literature, with its metadata to fill in. Nothing is added until the form is sent.",
    "conversation:next-message": "Shows or hides the model, effort and other settings the next message will use, and recovery of an unconfirmed earlier request. Nothing is sent.",
    "conversation:add-document": "Opens the form for adding a local document from the conversation. No file is chosen or uploaded until the form is used.",
    "material:reader": "Opens one of the project's readers. It only reads.",
    "material:file": "Marks one recorded file's card; selecting a card has no meaning of its own, and its Read, Add to Literature and More buttons are the controls.",
    "material:binding": "Opens one shared material binding with its currentness, as the owner records it. It only reads.",
    "research:result": "Opens one research result with its currentness. It only reads.",
    "help:layer": "Is the help layer for this page: a glance, tasks, how it works, states and shortcuts. Nothing is changed.",
    "help:close": "Closes the help layer and returns to the page. Esc does the same.",
    "help:task": "Starts a step-by-step tutorial that points at the page's own controls. Nothing is changed in the project.",
    "help:diagram": "Draws how this page's owners fit together, when opened. Nothing is changed.",
    "help:cue": "Is the card beside the control a tutorial step points at, with Back, Next or Skip, and Stop. Nothing is changed in the project.",
    "topology:fold": "Folds or unfolds a wide level of the drawing, whose count is shown. Nothing is changed.",
    "reader-plan:paragraph-expand": "Reads the whole plan of one paragraph, where the display shortened or left out fields. It only reads.",
    "reader-plan:transition-expand": "Reads the full text of a reader transition the display shortened. It only reads.",
    "reader-plan:unit-select": "Opens or closes one planned unit. Nothing is changed.",
    "reader-plan:acknowledge-inputs": "Records that you inspected the plan's inputs and open points, after one fresh read. It records an observation, not a review.",
    "conversation:send": "Sends the message to the conversation. With nothing typed it says 'Write a message first.' and sends nothing.",
    "sessions:send": "Sends the message to the open session. With nothing typed it says 'Write a message first.' and sends nothing.",
    "research:conversation": "Shows or hides the section where the conversation about an opened object appears after Discuss. Nothing is changed.",
    "research:save-view": "Saves the current presentation view, and says beside it when nothing was saved and why.",
    "research:open-view": "Opens a saved presentation view, and says beside it when nothing was opened and why.",
    "work:step-waits-on": "Reads what this step waits on, from the task's own detail read, and shows it with when it was read. It only reads.",
    "work:containment-save": "Saves which task contains this one. Unchanged, it says 'Nothing changed' and sends nothing; after a recorded save it says when and which task now contains this one.",
    "work:attempt": "Shows the last attempt to save this task's authored work: its status, who made it and the revision it was written against. It is not a control.",
    "work:compare": "Shows the draft beside the current work after its basis changed, with a button to use the current work as the basis. It is not a control.",
    "work:result": "Opens the finished result: checks the comment route, build and document with their owners, then opens the PDF.",
    "settings:save-defaults": "Saves the chosen provider, model and effort as the defaults for new conversations. The page says what the owner recorded, or that nothing was recorded and the choices are kept.",
}
for _ident, _does in _WAVE13_DOES.items():
    CONTROL_DECLARATIONS[_ident]["does"] = _does
# ---- wave 13 id sweep: guide sentences for rows declared before this wave (end) ----
# ---- wave 13b id sweep: the controls of the modules the first pass left out (begin) ----
# One table per module: (id, label, kind, guide sentence, states, extra). The guide sentence says what pressing the control does,
# in plain words, and is written here once (R12). `extra` carries dynamic (one instance per owner row, with data-control-owner),
# hidden_until and disabled_until.
def _wave13b(view, renders_in, rows):
    for ident, label, kind, does, states, extra in rows:
        CONTROL_DECLARATIONS[ident] = {"label": label, "view": view, "kind": kind, "rendered": True, "does": does, "renders_in": renders_in,
                                       "states": list(states), "dynamic": bool(extra.get("dynamic", False)),
                                       **{k: v for k, v in extra.items() if k in ("hidden_until", "disabled_until")}}

_A = ("graphs", "graphs-analysis", "graphs-trace", "graphs-usage", "graphs-delivery", "graphs-feedback", "graphs-commissioned", "graphs-failed")   # every Graphs view
_N = ("graphs", "graphs-trace", "graphs-usage", "graphs-delivery", "graphs-feedback", "graphs-commissioned", "graphs-failed")   # every Graphs view that has the tab strip (Graphs & analysis has the list instead)
_wave13b("history", "workspace-analytics.mjs Activity > Graphs, the session analytics views; tests/workspace_control_coverage.test.mjs 'history/graphs*'", (
    ("analytics:refresh", "Refresh", "action", "Reads the shown Graphs view again from the owner; nothing is changed.", _A, {}),
    ("analytics:view-tab", "Activity view", "selection", "Switches Graphs to Overview, Graphs & analysis, Selected activity, Usage, Feedback, Delivery or Coverage and reads that view from the owner; nothing is changed.", _N, {"dynamic": True, "hidden_until": "the page lists that view"}),
    ("analytics:view-select", "Activity view", "selection", "Switches Graphs to another of its views from the list shown beside the plots; it reads that view from the owner and changes nothing.", ("graphs-analysis",), {}),
    ("analytics:open-changes", "Changes & history", "navigation", "Leaves Graphs for the Activity timeline of recorded changes, with the same filters; nothing is changed.", _A, {}),
    ("analytics:open-conversations", "Conversations", "navigation", "Opens the list of saved conversations; nothing is changed.", _A, {}),
    ("analytics:filter-project", "Project activity filter", "selection", "Chooses which project's recorded activity Graphs shows; it applies when Apply filters is pressed.", _A, {"disabled_until": "Graphs is opened without a project, as on the Sessions page; inside a project the project is fixed"}),
    ("analytics:apply-filters", "Apply filters", "action", "Reads the shown Graphs view again with the filters you set; it is the only way a filter takes effect and it changes nothing recorded.", _A, {}),
    ("analytics:more-filters", "More call filters", "disclosure", "Shows the provider, conversation, operation and outcome filters for the plots; nothing is changed.", ("graphs-analysis",), {}),
    ("analytics:basis", "Scope, coverage & recorded basis", "disclosure", "Shows the scope, the coverage counts, the limits and the recorded cut this view was read at; nothing is changed.", ("graphs", "graphs-trace", "graphs-usage", "graphs-delivery", "graphs-feedback", "graphs-commissioned"), {}),
    ("analytics:inspect-conversation", "Inspect conversation activity", "action", "Reads the recorded activity of this one conversation and shows it as Selected activity; nothing is changed.", ("graphs", "graphs-commissioned"), {"dynamic": True, "hidden_until": "the owner lists that conversation"}),
    ("analytics:open-conversation", "Open conversation", "navigation", "Opens this saved conversation in the conversation panel; nothing is sent.", ("graphs", "graphs-trace", "graphs-commissioned"), {"dynamic": True, "hidden_until": "the owner lists that conversation"}),
    ("analytics:open-work", "Open work", "navigation", "Opens the task this conversation or event is recorded against; nothing is changed.", ("graphs", "graphs-trace", "graphs-commissioned"), {"dynamic": True, "hidden_until": "the owner records a task for that row"}),
    ("analytics:read-commissioning-turn", "Read commissioning turn", "navigation", "Opens the saved turn that commissioned this conversation; nothing is changed.", ("graphs-commissioned",), {"dynamic": True, "hidden_until": "the owner records the turn that commissioned that conversation"}),
    ("analytics:note-reply", "Note on latest reply", "action", "Opens a box for a note about this conversation's latest saved reply; nothing is saved until Save response note.", ("graphs", "graphs-commissioned"), {"dynamic": True, "hidden_until": "the owner names the latest saved reply as a feedback target"}),
    ("analytics:conversation-basis", "Recorded conversation basis", "disclosure", "Shows how this conversation's title, models and live state were established; nothing is changed.", ("graphs", "graphs-commissioned"), {"dynamic": True, "hidden_until": "the owner lists that conversation"}),
    ("analytics:more", "More recorded activity", "navigation", "Reads the next page of this view from the owner's own continuation and adds it below; nothing is changed.", ("graphs-trace",), {"hidden_until": "the owner issues a next page for the view"}),
    ("analytics:inspect-record", "Inspect recorded basis", "action", "Reads the exact saved record behind this row from the owner and shows it; nothing is changed.", ("graphs-trace", "graphs-feedback"), {"dynamic": True, "hidden_until": "the owner issues a read for that record"}),
    ("analytics:inspect-admission", "Inspect immutable admission", "action", "Reads the exact saved admission record of this turn from the owner and shows it; nothing is changed.", ("graphs-delivery",), {"dynamic": True, "hidden_until": "the owner issues an admission read for that turn"}),
    ("analytics:read-turn", "Read turn", "navigation", "Opens the saved turn this row belongs to; nothing is changed.", ("graphs-trace", "graphs-usage", "graphs-delivery"), {"hidden_until": "the row names a saved turn"}),
    ("analytics:read-target-turn", "Read target turn", "navigation", "Opens the saved turn this feedback record is about; nothing is changed.", ("graphs-feedback",), {"hidden_until": "the owner lists a feedback record whose target is a saved turn"}),
    ("analytics:usage-attempt", "Usage attempt", "disclosure", "Shows one saved attempt's context counter, logical-turn and binding counts; nothing is changed.", ("graphs-usage",), {"dynamic": True, "hidden_until": "the owner lists that attempt"}),
    ("analytics:audit-observations", "Audit selected observations", "disclosure", "Shows the owner's exact selected observations for this attempt, as saved; nothing is changed.", ("graphs-usage",), {}),
    ("analytics:audit-delivery", "Audit delivery receipt", "disclosure", "Shows the owner's exact delivery receipt for this turn, as saved; nothing is changed.", ("graphs-delivery",), {}),
    ("analytics:feedback-lineage", "Exact target and lineage", "disclosure", "Shows the exact feedback target and its saved lineage; nothing is changed.", ("graphs-feedback",), {"hidden_until": "the owner lists a feedback record"}),
    ("analytics:retry", "Retry this view", "action", "Reads the failed Graphs view again from the owner; nothing is changed.", ("graphs-failed",), {"hidden_until": "a read of the view failed"}),
    ("analytics:audit-record", "Audit exact public record", "disclosure", "Shows the saved record exactly as the owner returned it; nothing is changed.", ("graphs-record",), {}),
    ("analytics:note-close", "Close", "action", "Closes the response note box; the text typed there is kept for this response.", ("graphs-note",), {}),
    ("analytics:note-save", "Save response note", "action", "Saves the note as an observation about this response; the page says what was recorded, or that nothing was and the note is kept.", ("graphs-note",), {}),
    ("analytics:note-read-turn", "Read the saved turn", "navigation", "Opens the saved turn this response came from; nothing is changed.", ("graphs-note",), {"hidden_until": "the page can open saved turns"}),
))
_wave13b("history", "workspace-analysis.mjs Activity > Graphs > Graphs & analysis, the plots; tests/workspace_control_coverage.test.mjs 'history/graphs-analysis'", (
    ("analytics:time-bar", "Calls in a recorded interval", "selection", "Opens the Activity timeline filtered to the calls the owner counted in this recorded interval; nothing is changed.", ("graphs-analysis",), {"dynamic": True, "hidden_until": "the owner returns dated call counts with a filter for that interval"}),
    ("analytics:usage-bar", "Reported usage count", "selection", "Opens the Usage view for the provider and model this bar's reported count belongs to; nothing is changed.", ("graphs-analysis",), {"dynamic": True, "hidden_until": "the owner reports usage for that provider, model and basis"}),
    ("analytics:outcome-bar", "Recorded outcome", "selection", "Opens the Activity timeline filtered to the calls the owner recorded with this outcome; nothing is changed.", ("graphs-analysis",), {"dynamic": True, "hidden_until": "the owner returns a count for that outcome"}),
    ("analytics:runtime-point", "Producer run duration", "selection", "Opens the Activity timeline filtered to the result history of this producer run; nothing is changed.", ("graphs-analysis",), {"dynamic": True, "hidden_until": "the owner returns a timed producer run that has a result-history filter"}),
    ("analytics:run-read", "Producer run", "action", "Opens the Activity timeline filtered to the exact recorded result of this producer run; it is off for a run with no result history.", ("graphs-analysis",), {"dynamic": True, "hidden_until": "the owner returns a timed producer run"}),
    ("analytics:analysis-basis", "Analysis cut and exclusions", "disclosure", "Shows the recorded cut the plots were read at and how many earlier cells and operations were left out; nothing is changed.", ("graphs-analysis",), {}),
))
# the plots of Graphs & analysis are drawn by history-telemetry.mjs: its controls render there too
for _ident in ("history:telemetry-filter", "history:tool-view", "history:telemetry-limits"):
    CONTROL_DECLARATIONS[_ident]["states"] = [*CONTROL_DECLARATIONS[_ident]["states"], "graphs-analysis"]
_wave13b("conversation", "conversation-reading.mjs the reader of one saved message in the conversation panel; tests/workspace_control_coverage.test.mjs 'conversation/reading-*'", (
    ("conversation:reading-next", "Continue reading", "action", "Reads the next page of this saved message from the owner's own continuation and adds it below; nothing is changed.", ("reading-partial",), {"hidden_until": "the saved message is longer than the page read so far"}),
    ("conversation:reading-retry", "Retry reading", "action", "Reads the page that failed again, from the owner; the text already shown is kept and nothing is changed.", ("reading-failed",), {"hidden_until": "a read of this message failed and the message has not changed"}),
    ("conversation:reading-restart", "Restart reading", "action", "Reads this saved message again from its first page, as it is now; the text shown is replaced only when the read succeeds.", ("reading-failed",), {"hidden_until": "a read of this message failed"}),
    ("conversation:reading-details", "Message details", "disclosure", "Shows which saved message this is, the revision it was read at and how many characters of it are shown; nothing is changed.", ("reading-partial", "reading-failed"), {}),
))
_LIT = ("literature-new", "literature-recorded", "literature-lost", "literature-found", "literature-rejected", "literature-edited")
_wave13b("material", "retained-source-literature.mjs and literature-metadata.mjs the Literature source box that Add to Literature opens; tests/workspace_control_coverage.test.mjs 'material/literature-*'", (
    ("literature:close-source", "Close Literature source", "action", "Closes the Literature source box; an import draft you typed is kept for this original.", _LIT, {}),
    ("literature:import-draft", "Import draft", "disclosure", "Shows the details of a new import for this original, kept as a draft; nothing is saved until Save to Literature.", ("literature-recorded", "literature-found"), {"hidden_until": "the original already has a saved Literature source"}),
    ("literature:exact-source", "Exact retained source", "disclosure", "Shows the exact identity of the retained original, as the owner holds it; nothing is changed.", _LIT, {}),
    ("literature:more-fields", "More bibliography details", "disclosure", "Shows the optional bibliography fields: authors, year, type, publisher, title of the work, ISBN and pages; nothing is changed.", _LIT, {}),
    ("literature:item-type", "Type of source", "selection", "Chooses what kind of source this is for the bibliography; an unset choice is left out of the saved entry rather than guessed.", _LIT, {}),
    ("literature:save", "Save to Literature", "action", "Saves the details as this original's Literature source, with the original request kept if the owner's answer is lost; the page says what the owner recorded.", _LIT, {"disabled_until": "the owner permits Literature for this original, no earlier submission is retained and a title and source provenance are filled in"}),
    ("literature:read-source", "Read source", "navigation", "Opens the saved source for reading in the Literature reader, with the claim or passage it was opened from; nothing is changed.", ("literature-recorded", "literature-found"), {"hidden_until": "the original already has a saved Literature source"}),
    ("literature:link-claim", "Link to claim", "action", "Opens the saved source in the Literature reader to link it to a claim; the claim meaning is inspected there and nothing is linked until you confirm.", ("literature-recorded", "literature-found"), {"hidden_until": "the original already has a saved Literature source"}),
    ("literature:saved-metadata", "Saved metadata and bibliography", "disclosure", "Shows the Literature entry and bibliography the owner saved for this original, exactly; nothing is changed.", ("literature-recorded", "literature-found"), {"hidden_until": "the original already has a saved Literature source"}),
    ("literature:check-source", "Check Literature source", "action", "Reads again from the owner whether this original now has a saved Literature source; it sends nothing and changes nothing.", ("literature-lost", "literature-found", "literature-rejected"), {"hidden_until": "an earlier submission is retained, or the owner's standing could not be read"}),
    ("literature:retry-submission", "Retry same Literature submission", "action", "Sends the retained submission again exactly as it was, after you chose to; the owner's answer is shown beside it.", ("literature-lost",), {"hidden_until": "the retained submission has no recorded outcome"}),
    ("literature:edit-details", "Edit details", "action", "Turns the rejected submission back into an editable draft with your text kept; nothing is sent until you save again.", ("literature-rejected",), {"hidden_until": "the owner rejected the retained submission before any effect"}),
    ("literature:validation-details", "Validation details", "disclosure", "Shows the owner's exact reason for rejecting the submission; nothing is changed.", ("literature-rejected",), {"hidden_until": "the owner rejected the retained submission before any effect"}),
    ("literature:use-saved-source", "Use saved source", "action", "Accepts the Literature source the owner already holds and drops the retained submission; your import draft is kept.", ("literature-found",), {"hidden_until": "a submission is retained and the owner now holds a saved source"}),
    ("literature:rejected-submission", "Earlier rejected submission", "disclosure", "Shows the submission the owner rejected and its reason, kept beside the draft you are editing; nothing is changed.", ("literature-edited",), {"hidden_until": "a rejected submission was turned back into a draft"}),
))
_wave13b("review", "feedback-route.mjs openFeedbackReply, the box that reads one complete review response; tests/workspace_control_coverage.test.mjs 'review/response-*'", (
    ("review:response-close", "Close response", "action", "Closes the box that shows one complete review response; nothing is changed.", ("response-partial", "response-failed"), {}),
    ("review:response-continue", "Continue reading response", "action", "Reads the next page of this saved review response from the owner's own continuation and adds it below; nothing is changed.", ("response-partial",), {"hidden_until": "the saved response is longer than the page read so far"}),
    ("review:response-retry", "Retry response read", "action", "Reads the page that failed again, from the owner; the text already shown is kept and nothing is changed.", ("response-failed",), {"hidden_until": "a read of this response failed and the response has not changed"}),
    ("review:response-restart", "Restart response read", "action", "Reads this saved review response again from its first page, as it is now; nothing is changed.", ("response-failed",), {"hidden_until": "a read of this response failed"}),
    ("review:response-basis", "Exact response basis", "disclosure", "Shows which saved response this is, the revision it was read at and how many characters of it are shown; nothing is changed.", ("response-partial", "response-failed"), {}),
))
_C = ("comment-new", "comment-routing", "comment-routed", "comment-lost", "comment-unrecorded")   # every state of the passage comment dialog that renders before a comment is saved or after a save whose answer was lost
_wave13b("review", "feedback-route.mjs openFeedbackComment, the passage comment dialog that Comment on this passage opens in the editor; tests/workspace_control_coverage.test.mjs 'review/comment-*'", (
    ("review:comment-routing", "Reviewers and limits", "disclosure", "Opens the choice of an existing review Work, its saved review settings and limits; opening reads the Work list from the owner, and the route preview of a Work chosen earlier, and changes nothing.", _C, {}),
    ("review:comment-save", "Save comment", "action", "Saves your comment on this passage as written, with the original request kept if the owner's answer is lost; the dialog says what the owner recorded. When the chosen Work's saved review settings are automatic, this button reads Save comment and request reviews and also requests the reviews the owner's preview permits.", _C, {"disabled_until": "the passage was inspected by the owner, no comment has been saved yet and no earlier save is waiting for a check"}),
    ("review:comment-send", "Save and request reviews", "action", "Saves your comment and requests the reviews you previewed in one explicit decision; nothing is requested without it. It is hidden when the Work's saved settings are automatic, because Save comment then requests the reviews.", _C, {"disabled_until": "the owner's preview of the chosen Work permits requesting reviews and the review settings are unchanged since the preview"}),
    ("review:comment-close", "Close comment", "action", "Closes the dialog; the comment you typed is kept as a draft for this passage (the dialog says so if it could not be kept) and nothing is saved by closing.", _C, {}),
    ("review:comment-work", "Existing review Work", "selection", "Chooses which existing Work the reviews of this comment belong to; choosing reads the owner's preview of that Work's review route and requests nothing.", ("comment-routing", "comment-routed"), {}),
    ("review:comment-more-work", "More existing Work", "navigation", "Reads the next page of Work from the owner's own continuation and adds it to the list; nothing is changed.", ("comment-routing", "comment-routed"), {"hidden_until": "the owner issues a next page of Work"}),
    ("review:comment-policy", "Saved review settings", "selection", "Chooses between manual review settings and a saved set of review settings for this Work; choosing reads the owner's preview and saves nothing.", ("comment-routed",), {}),
    ("review:comment-limit", "Review limits", "choice", "Sets one limit for this comment's reviews: reviews allowed, connection attempts per review, time to start reviews or review time limit; it takes effect only through Preview reviews and a save.", ("comment-routed",), {"dynamic": True}),
    ("review:comment-preview", "Preview reviews", "action", "Reads from the owner what reviews your settings would request for this Work, without requesting any.", ("comment-routed",), {}),
    ("review:comment-auto-save", "Save automatic review settings", "action", "Records your recipients and limits as the automatic review settings of this Work through the owner's policy action; it saves no comment.", ("comment-routed",), {"hidden_until": "the chosen settings are not already the saved automatic settings"}),
    ("review:comment-check", "Check save", "action", "Reads from the owner whether the save whose answer was lost was recorded; it sends and changes nothing.", ("comment-lost", "comment-unrecorded"), {"hidden_until": "a save was sent and its outcome is not known"}),
    ("review:comment-retry", "Retry same save", "action", "Sends the retained save again exactly as it was, after a check found no record of it; the owner's answer is shown beside it.", ("comment-unrecorded",), {"hidden_until": "a check found no record of the retained save"}),
    ("review:comment-settle", "Resolve uncertain save", "action", "Asks the owner to settle the retained save as never admitted, keeping any comment already saved; the dialog says what the owner recorded.", ("comment-lost", "comment-unrecorded"), {"hidden_until": "a save was sent, its outcome is not known and the owner offers to settle it"}),
))
_F = ("frame-toolbar", "frame-reading")   # the editor frame's toolbar as the Writing page shows it, and with Reading options opened
_wave13b("manuscript", "writing-panel.mjs and walk.html, the toolbar inside the editor frame (the iframe titled 'Manuscript reader and editor') on the Writing page; tests/workspace_control_coverage.test.mjs 'manuscript/frame-*'", (
    ("editor-frame:zoom-out", "Smaller text", "action", "Makes the manuscript text in the editor smaller; the size is a view choice kept for this browser and nothing in the manuscript changes.", _F, {}),
    ("editor-frame:zoom-in", "Larger text", "action", "Makes the manuscript text in the editor larger; the size is a view choice kept for this browser and nothing in the manuscript changes.", _F, {}),
    ("editor-frame:questions", "Questions & context", "action", "Opens the questions and context the project holds for the passage you are reading; it reads from the owners and changes nothing.", _F, {}),
    ("editor-frame:find", "Find", "action", "Opens the Find and replace box over the manuscript text; finding reads the text on the page and changes nothing, and Replace next there edits and saves a passage.", _F, {}),
    ("editor-frame:reading-options", "Reading options", "disclosure", "Shows the reading choices of the editor: open points, text width, whether your changes are marked, and autosave; nothing is changed by opening it.", _F, {}),
    ("editor-frame:open-points", "Open points", "action", "Opens the open points the project's plan records; it reads from the owners and changes nothing.", ("frame-reading",), {}),
    ("editor-frame:width", "Manuscript width", "selection", "Chooses how wide the manuscript text is drawn: fill the pane, wide text or reading width; a view choice kept for this browser.", ("frame-reading",), {}),
    ("editor-frame:author-changes", "Your changes", "toggle", "Turns the marks that show your own edits and their revisions on or off in the text; a view choice kept for this browser and nothing in the manuscript changes.", ("frame-reading",), {}),
    ("editor-frame:autosave", "Autosave", "toggle", "Turns autosave on or off in this browser; it is off until you turn it on. Off, your edits are saved only by Save changes in the editor band beside the Write, TeX and PDF buttons, which shows while Write edits are unsaved, or by Ctrl-S, and until then they are kept in the editor, also across a reload. On, the paragraph you are typing in is saved a short pause after you stop typing, that paragraph only, and never while its previous save is still out: words typed meanwhile are saved once that save answers; a paragraph another writer changed under your draft, or one the file no longer has, waits for Save changes, Ctrl-S or Keep my text and save it.", ("frame-reading",), {}),
    ("editor-frame:keep-my-text", "Keep my text and save it", "action", "Saves every paragraph you have typed in exactly as it stands in the editor: your text is written over that passage as the file holds it now, and a paragraph of yours the file no longer has is put back at its place as a paragraph of its own; any text it replaces is kept in the manuscript's change record. It is the first control beside every save warning on the frame's status line, and in the box above the manuscript that keeps a paragraph of yours the file no longer has.", ("frame-save-warning",), {}),
    ("editor-frame:show-other-version", "Show the other version", "action", "Opens a panel above the manuscript showing what the file holds now at the paragraph another writer changed while your draft was open; nothing is saved or changed, and your text stays in its paragraph until you save or discard it. It stands beside Keep my text and save it on the frame's status line while such a draft is open.", ("frame-save-warning",), {}),
))
_wave13b("manuscript", "writing-panel.mjs the selection toolbar of the editor frame, shown when text is selected in the manuscript; tests/workspace_control_coverage.test.mjs 'manuscript/frame-bubble'", (
    ("editor-frame:bubble-comment", "Comment", "action", "Opens the comment dialog for the selected text, or says in the frame's status line why it cannot (for example unsaved manuscript edits are held); the dialog saves nothing until you press Save comment there, or Save comment and request reviews when the Work's saved settings are automatic.", ("frame-bubble",), {}),
    ("editor-frame:bubble-discuss", "Discuss", "action", "Prepares a message in the conversation panel about the selected text, to discuss it with the agent; nothing is sent.", ("frame-bubble",), {}),
    ("editor-frame:bubble-revise", "Revise", "action", "Prepares a message in the conversation panel asking the agent to revise the selected text; nothing is sent and nothing is changed.", ("frame-bubble",), {}),
    ("editor-frame:bubble-reference", "Reference", "action", "Opens the choice of a label to insert as a reference at the selection; nothing is inserted until you choose one, and choosing one inserts it and saves the passage at once (when the exact-source box is open it inserts into that box instead, written by the box's Save changes, the editor band's Save changes or Ctrl-S).", ("frame-bubble",), {}),
    ("editor-frame:bubble-citation", "Citation", "action", "Opens the choice of a source to insert as a citation at the selection; nothing is inserted until you choose one, and choosing one inserts it and saves the passage at once (when the exact-source box is open it inserts into that box instead, written by the box's Save changes, the editor band's Save changes or Ctrl-S).", ("frame-bubble",), {}),
    ("editor-frame:bubble-queue", "Queue request", "action", "Opens a box to queue a written request about the selected text for later; nothing is queued until you press Queue request there.", ("frame-bubble",), {}),
))
_wave13b("manuscript", "writing-panel.mjs the passage menu of the editor frame, opened by a right-click on a passage; tests/workspace_control_coverage.test.mjs 'manuscript/frame-menu'", (
    ("editor-frame:menu-insert-reference", "Insert reference…", "action", "Opens the choice of a label to insert as a reference at the place you pressed; nothing is inserted until you choose one, and choosing one inserts it there and saves that passage at once. Only when you press the passage whose exact TeX source box is open, while text in that box is selected, does it insert into the box instead, written by that box's Save changes, Save changes in the editor band or Ctrl-S.", ("frame-menu",), {"hidden_until": "the place pressed is a point where text can be inserted"}),
    ("editor-frame:menu-insert-citation", "Insert citation…", "action", "Opens the choice of a source to insert as a citation at the place you pressed; nothing is inserted until you choose one, and choosing one inserts it there and saves that passage at once. Only when you press the passage whose exact TeX source box is open, while text in that box is selected, does it insert into the box instead, written by that box's Save changes, Save changes in the editor band or Ctrl-S.", ("frame-menu",), {"hidden_until": "the place pressed is a point where text can be inserted"}),
    ("editor-frame:menu-italic", "Italic", "action", "Wraps the selected text, or the word at the caret, in italics written as TeX in the passage, and refuses a selection that crosses an equation, citation or macro; the edit is saved by Save changes in the editor band, which shows while Write edits are unsaved, or by Ctrl-S, or a moment after you stop typing if you turned Autosave on.", ("frame-menu",), {"hidden_until": "the place pressed is a point where text can be inserted"}),
    ("editor-frame:menu-bold", "Bold", "action", "Wraps the selected text, or the word at the caret, in bold written as TeX in the passage, and refuses a selection that crosses an equation, citation or macro; the edit is saved by Save changes in the editor band, which shows while Write edits are unsaved, or by Ctrl-S, or a moment after you stop typing if you turned Autosave on.", ("frame-menu",), {"hidden_until": "the place pressed is a point where text can be inserted"}),
    ("editor-frame:menu-insert-heading", "Insert heading…", "action", "Opens a box for the title, level and position of a new heading beside this passage; nothing changes until you press Insert heading there, which saves your pending edits and then writes the heading to the source.", ("frame-menu",), {}),
    ("editor-frame:menu-paragraph-style", "Paragraph style…", "action", "Opens a box to turn this paragraph into a heading of the level you choose; nothing changes until you press Change paragraph style there, which saves your pending edits and then rewrites the paragraph as a heading in the source.", ("frame-menu",), {"hidden_until": "the passage is a paragraph"}),
    ("editor-frame:menu-queue-request", "Queue a request…", "action", "Opens a box to queue a written request about this passage for later; nothing is queued until you press Queue request there.", ("frame-menu",), {}),
    ("editor-frame:menu-delete-paragraph", "Delete paragraph now", "action", "Deletes this paragraph from the manuscript source at once, after asking who is editing if no one is named, and records the change; it does not wait for Autosave or Save changes, and a paragraph whose own save is still out is not deleted until that save answers.", ("frame-menu",), {"hidden_until": "the passage is a paragraph"}),
    ("editor-frame:menu-edit-passage", "Edit this passage", "action", "Opens this passage for typing in place; what you type is saved by Save changes in the editor band, which shows while Write edits are unsaved, or by Ctrl-S, or a moment after you stop typing if you turned Autosave on. A passage that cannot be typed in place (an equation, a heading with maths, or a passage shown as raw TeX) opens its exact TeX source box instead, which is written by three acts only: that box's Save changes, Save changes in the editor band (shown once the box's text is changed) or Ctrl-S while the box is open; Autosave never writes it. A passage held in an open proposed change is not opened: the frame's status line asks you to accept or reject the proposed change first.", ("frame-menu",), {}),
    ("editor-frame:menu-edit-source", "Edit exact source", "action", "Shows this passage as its exact TeX source in a box for editing in place, except a passage held in an open proposed change, which is not opened: the frame's status line asks you to accept or reject the proposed change first. The source is written by three acts only: that box's Save changes, Save changes in the editor band (shown once the text in the box is changed) or Ctrl-S while the box is open; Autosave never writes it, whatever it is set to, and the box's Cancel closes the box without saving.", ("frame-menu",), {}),
    ("editor-frame:menu-open-tex", "Open in TeX", "navigation", "Opens the TeX source of the file at this passage in the Writing TeX pane; nothing is changed.", ("frame-menu",), {"hidden_until": "the editor is the Writing TeX workbench"}),
    ("editor-frame:menu-questions", "Questions & context", "action", "Opens the questions and context the project holds for this passage; it reads from the owners and changes nothing.", ("frame-menu",), {}),
    ("editor-frame:menu-section-concepts", "Section concepts", "navigation", "Opens the Reader plan item that covers this passage, or the Reader plan to choose one when none or several do; it reads from the owner and changes nothing.", ("frame-menu",), {}),
    ("editor-frame:menu-discuss", "Discuss this passage", "action", "Prepares a message in the conversation panel about this passage, to discuss it with the agent; nothing is sent.", ("frame-menu",), {}),
    ("editor-frame:menu-comment", "Comment on this passage", "action", "Opens the comment dialog for this passage, or says in the frame's status line why it cannot (for example unsaved manuscript edits are held); the owner inspects the passage first and nothing is saved until you press Save comment, or Save comment and request reviews when the Work's saved settings are automatic.", ("frame-menu",), {}),
))
_wave13b("manuscript", "writing-panel.mjs queueRequest, the box that Queue a request opens from the passage menu or the selection toolbar of the editor frame; tests/workspace_control_coverage.test.mjs 'manuscript/frame-queue'", (
    ("editor-frame:queue-submit", "Queue request", "action", "Queues what you typed as a request for the session about this passage, as a task the project records; nothing is queued until you press it and an empty request is not sent.", ("frame-queue",), {}),
    ("editor-frame:queue-cancel", "Cancel", "action", "Closes the box without queueing anything.", ("frame-queue",), {}),
))
_wave13b("manuscript", "walk-card.mjs openFindDialog, the Find box that the editor frame's Find opens; tests/workspace_control_coverage.test.mjs 'manuscript/frame-find'", (
    ("editor-frame:find-next", "Find next", "action", "Finds the next place in the manuscript that matches what you typed, closes the box and moves the reading there; nothing is changed.", ("frame-find",), {}),
    ("editor-frame:find-replace", "Replace next", "action", "Replaces the next match with your replacement text in the passage and saves that passage at once; it does not wait for Autosave or for Save changes in the editor band.", ("frame-find",), {}),
    ("editor-frame:find-close", "Close", "action", "Closes the Find box; what you typed is kept for the next time you open it and nothing is changed.", ("frame-find",), {}),
))
_wave13b("manuscript", "writing-panel.mjs openPoints, the context pane that Questions & context and Open points open in the editor frame; tests/workspace_control_coverage.test.mjs 'manuscript/frame-context'", (
    ("editor-frame:context-close", "Close context", "action", "Closes the questions and context pane and returns the reading position and selection you had; nothing is changed.", ("frame-context",), {}),
))
_wave13b("research", "workspace-literature.mjs and literature-metadata.mjs Research > Literature, the project library, discovery, the source and claim-link boxes and coverage; tests/workspace_control_coverage.test.mjs 'research/literature-*'", (
    ('literature-library:dialog-close', 'Close', 'action', 'Closes the source box or the claim-link box that is open over Literature; a link you were typing is kept as a draft for this source.', ('literature-source', 'literature-source-failed', 'literature-bind'), {}),
    ('literature-library:tab-library', 'Project library', 'selection', 'Shows the sources saved in this project, with the claims and manuscript places they are linked to; nothing is changed.', ('literature-library', 'literature-claim', 'literature-discover', 'literature-zotero', 'literature-local', 'literature-coverage'), {}),
    ('literature-library:tab-discover', 'Discover sources', 'selection', 'Shows the search for scholarly works to save to this project; nothing is searched until you press Search.', ('literature-library', 'literature-claim', 'literature-discover', 'literature-zotero', 'literature-local', 'literature-coverage'), {}),
    ('literature-library:tab-local', 'Add local source', 'selection', 'Shows the form for a source you have yourself, with its own bibliographic details and where they came from; nothing is saved until you press its save button.', ('literature-library', 'literature-claim', 'literature-discover', 'literature-zotero', 'literature-local', 'literature-coverage'), {}),
    ('literature-library:find-literature', 'Find literature for this project', 'action', 'Prepares a message in the conversation panel asking the current agent to search, read and save sources for this project, this claim or this passage; nothing is sent.', ('literature-library', 'literature-claim', 'literature-discover', 'literature-zotero', 'literature-local', 'literature-coverage'), {'hidden_until': 'the page can prepare a message for the conversation panel'}),
    ('literature-library:clear-target', 'Clear claim target', 'action', 'Stops limiting Literature to the claim or passage it was opened for, and shows the whole project library; nothing is changed.', ('literature-claim',), {'hidden_until': 'Literature was opened for one claim or passage'}),
    ('literature-library:scope-select', 'Show sources', 'selection', 'Chooses between the sources linked to this claim and all project sources; it changes only what is listed.', ('literature-claim',), {'hidden_until': 'Literature was opened for one claim'}),
    ('literature-library:browse-all', 'Browse all project sources', 'action', 'Lists all project sources instead of only those linked to this claim; nothing is changed.', ('literature-claim',), {'hidden_until': 'no source is linked to the claim'}),
    ('literature-library:check-currentness', 'Check source currentness', 'action', "Asks the reference owner to check again whether each saved source's metadata is current, and shows what it found; saved links are not changed.", ('literature-library', 'literature-claim', 'literature-coverage'), {}),
    ('literature-library:more-sources', 'Show more project sources', 'navigation', "Reads the next page of the project library from the owner's own continuation and adds it below; nothing is changed.", ('literature-library',), {'hidden_until': 'the owner issues a next page of sources'}),
    ('literature-library:more-citations', 'Load more manuscript citation uses', 'navigation', "Reads the next part of the manuscript for places that cite these sources, from the owner's own continuation; nothing is changed.", ('literature-library',), {'hidden_until': 'the owner issues a next page of citation uses'}),
    ('literature-library:read-source', 'Read source', 'action', 'Opens the source in a box to read what is available (its text or PDF), search it and acquire full text; nothing is linked or saved by opening it.', ('literature-library', 'literature-zotero'), {}),
    ('literature-library:link-claim', 'Link to a claim', 'action', "Opens a box to link this source to one claim with your reason for it; nothing is linked until you inspect the claim's meaning and press Save source link.", ('literature-library',), {}),
    ('literature-library:add-bibliography', 'Add bibliography details', 'action', "Opens Add local source with this argument source's title and provenance filled in, so a bibliography entry can be saved for it; nothing is saved until you press its save button.", ('literature-library',), {'hidden_until': 'the source belongs to the argument and has no bibliography entry'}),
    ('literature-library:inspect-argument-source', 'Inspect argument source', 'navigation', 'Opens this source as an object in Argument & evidence; nothing is changed.', ('literature-library',), {'hidden_until': 'the source belongs to the argument and the page can open argument objects'}),
    ('literature-library:insert-citation', 'Insert citation…', 'action', "Arms the placement of this source's citation at the manuscript caret you choose next; nothing is written until you choose the place.", ('literature-library',), {'hidden_until': 'the source has a citation key and a bibliography entry, and the page can place citations'}),
    ('literature-library:discuss-source', 'Discuss source', 'action', 'Prepares a message in the conversation panel asking about this source and its links; nothing is sent.', ('literature-library',), {'hidden_until': 'the page can prepare a message for the conversation panel'}),
    ('literature-library:update-metadata', 'Update source metadata', 'action', "Asks the reference owner to update this source's bibliography entry from its current metadata; the page says what was recorded.", ('literature-library',), {'hidden_until': 'the source has a citation key and its currentness is not confirmed'}),
    ('literature-library:source-links', 'Claim links and manuscript citations', 'disclosure', 'Shows which claims this source is linked to, with your reasons, and where the manuscript cites it; nothing is changed.', ('literature-library',), {'dynamic': True, 'hidden_until': 'the owner lists that source'}),
    ('literature-library:open-claim', 'Linked claim', 'navigation', 'Opens the claim this source is linked to in Argument & evidence; nothing is changed.', ('literature-library',), {'dynamic': True, 'hidden_until': 'the source is linked to a claim and the page can open argument objects'}),
    ('literature-library:open-passage', 'Manuscript citation', 'navigation', 'Opens the manuscript place where this source is cited; nothing is changed.', ('literature-library',), {'dynamic': True, 'hidden_until': 'the owner finds a citation of the source and the page can open manuscript places'}),
    ('literature-library:inspect-coverage', 'Inspect project coverage', 'action', 'Asks the literature owner for the sources, evidence and citations covering the project, or the selected claim, and shows what it reports; nothing is changed.', ('literature-library', 'literature-claim', 'literature-coverage'), {}),
    ('literature-library:open-coverage-claim', 'Claim in coverage', 'navigation', 'Opens this claim, as the coverage report lists it, in Argument & evidence; nothing is changed.', ('literature-coverage',), {'dynamic': True, 'hidden_until': 'the coverage report lists a claim and the page can open argument objects'}),
    ('literature-library:coverage-previous', 'Previous coverage records', 'navigation', 'Reads the coverage records before these from the owner at the same cut; nothing is changed.', ('literature-coverage',), {'hidden_until': 'the report is not on its first page'}),
    ('literature-library:coverage-more', 'More coverage records', 'navigation', "Reads the next page of coverage records from the owner's own continuation; nothing is changed.", ('literature-coverage',), {'hidden_until': 'the owner issues a next page of coverage records'}),
    ('literature-library:build-manuscript', 'Build selected manuscript', 'action', 'Asks the owner to build the selected manuscript so its bibliography can be checked; the page says whether the build was requested.', ('literature-coverage',), {'hidden_until': 'a coverage report is shown'}),
    ('literature-library:build-status', 'Inspect bibliography build status', 'action', "Reads the manuscript build's current state from the owner and shows it; nothing is changed.", ('literature-coverage',), {'hidden_until': 'a coverage report is shown'}),
    ('literature-library:provider-select', 'Search library', 'selection', 'Chooses whether Search looks in public scholarly works or in your Zotero library; changing it clears the results shown.', ('literature-discover', 'literature-zotero'), {}),
    ('literature-library:search', 'Search', 'action', 'Searches the chosen library for the title, author or topic you typed and lists what it finds; nothing is saved.', ('literature-discover', 'literature-zotero'), {}),
    ('literature-library:save-source', 'Verify DOI & save to library', 'action', "Asks the reference owner to verify the work's identity and save it to this project's library (a Zotero item is attached instead); the page says what was recorded.", ('literature-discover', 'literature-zotero'), {'dynamic': True, 'hidden_until': 'the search found a work not yet in the project library'}),
    ('literature-library:open-in-library', 'Open in project library', 'navigation', 'Shows the project library filtered to this work, which is already saved; nothing is changed.', ('literature-discover',), {'dynamic': True, 'hidden_until': 'a found work is already in the project library'}),
    ('literature-library:review-local', 'Review local metadata', 'action', 'Copies this existing catalogue candidate into Add local source as a draft to check; nothing is saved until you save it there.', ('literature-discover',), {'dynamic': True, 'hidden_until': 'the search found existing local candidates'}),
    ('literature-library:known-doi', 'Add a known DOI', 'disclosure', 'Shows the form to save one work you already know by its DOI; nothing is changed.', ('literature-discover', 'literature-zotero'), {}),
    ('literature-library:save-doi', 'Verify & save', 'action', 'Asks the reference owner to verify this DOI and save the work to the project library; the page says what was recorded.', ('literature-discover', 'literature-zotero'), {'hidden_until': 'Add a known DOI is open'}),
    ('literature-library:local-item-type', 'Source type', 'selection', 'Chooses what kind of source this is for the bibliography.', ('literature-local',), {}),
    ('literature-library:local-save', 'Save source to project library', 'action', 'Saves the details as a local source in the project library, with where they came from recorded; the page says what the owner recorded.', ('literature-local',), {'disabled_until': 'a title and the source provenance are filled in'}),
    ('literature-library:source-select', 'Source or reading note', 'selection', 'Switches the box to another registered source or reading note of this work and reads it from the owner; nothing is changed.', ('literature-source',), {'hidden_until': 'the work has more than one registered source'}),
    ('literature-library:open-pdf', 'Open PDF', 'navigation', 'Opens the registered PDF of this source in the PDF reader; nothing is changed.', ('literature-source',), {'hidden_until': 'the owner issues a PDF address for the source'}),
    ('literature-library:read-text', 'Read text', 'action', "Reads the first page of the source's extracted text from the owner and shows it; a returned passage is recorded only when you link it.", ('literature-source',), {'hidden_until': 'the owner reports the source text as available'}),
    ('literature-library:find-passage', 'Find passage', 'action', 'Searches the registered source content for the words you typed and shows the matching passage; nothing is saved.', ('literature-source',), {'hidden_until': 'the owner reports the source text as available'}),
    ('literature-library:next-passage', 'Read next passage', 'navigation', "Reads the next passage of this source from the owner's own continuation and adds it below.", ('literature-source',), {'hidden_until': 'the owner issues a next passage'}),
    ('literature-library:candidate-url', 'Inspect candidate URL', 'navigation', 'Opens the address of a full-text candidate the owner found, in a new window; nothing is fetched.', ('literature-source',), {'dynamic': True, 'hidden_until': 'the owner lists a full-text candidate with a web address'}),
    ('literature-library:fetch-candidate', 'Fetch this full-text candidate', 'action', "Asks the owner to fetch this candidate as the source's full text; the reference is kept if the fetch fails.", ('literature-source',), {'dynamic': True, 'hidden_until': 'the owner lists a full-text candidate'}),
    ('literature-library:fetch-url', 'Fetch / retry full text', 'action', "Asks the owner to fetch the web address you typed as the source's full text; the reference is kept if the fetch fails.", ('literature-source',), {'hidden_until': 'the source is not a retained original'}),
    ('literature-library:publisher-link', 'Open publisher / source page', 'navigation', "Opens the publisher's or source's own page in a new window; nothing is changed.", ('literature-source', 'literature-discover', 'literature-zotero'), {'hidden_until': 'the source has a web address'}),
    ('literature-library:retry-source', 'Retry source inspection', 'action', 'Reads the source from the owner again after a failed read; nothing is changed.', ('literature-source-failed',), {'hidden_until': 'the read of the source failed'}),
    ('literature-library:claim-select', 'Claim', 'selection', "Chooses the claim to link this source to; choosing it reads the claim's meaning from the owner.", ('literature-bind',), {}),
    ('literature-library:more-claims', 'Load more claims', 'navigation', "Reads the next page of eligible claims from the owner's own continuation and adds them to the list.", ('literature-bind',), {'hidden_until': 'the owner issues a next page of claims'}),
    ('literature-library:relation-select', 'Relationship', 'selection', 'Chooses how the source relates to the claim (supports, challenges, background, method or extends); it is your interpretation.', ('literature-bind',), {}),
    ('literature-library:reading-select', 'Reading status', 'selection', 'Chooses how much of the source you read; record partial or read only after inspecting it.', ('literature-bind',), {}),
    ('literature-library:inspect-claim', 'Inspect current claim meaning', 'action', "Reads the claim's present meaning from the owner and shows it, so the link can be saved against it; nothing is changed.", ('literature-bind',), {}),
    ('literature-library:use-claim-revision', 'Use this inspected claim revision', 'action', 'Chooses the inspected claim meaning as the one this link is saved against; nothing is saved yet.', ('literature-bind',), {'hidden_until': 'the claim meaning was inspected by pressing Inspect current claim meaning'}),
    ('literature-library:read-passage-here', 'Read source passage here', 'action', "Reads a passage of the source in this box and keeps the owner's receipt for it, to record with the link; nothing is saved yet.", ('literature-bind',), {}),
    ('literature-library:save-link', 'Save source link', 'action', 'Saves the link between this source and the claim with your reason, relationship and reading status, against the inspected claim meaning; the page says what was recorded.', ('literature-bind',), {'disabled_until': 'a claim meaning was inspected and chosen, and a reason is written'}),
))
_wave13b("research", "writing-evidence.mjs Research > Formal proof, the project setup box; tests/workspace_control_coverage.test.mjs 'research/formal-setup'", (
    ("research:formal-setup", "Set up formal checking", "disclosure", "Shows where the project's formal checking is set up, its manifest path and the one next step; nothing is changed.", ("formal-setup",), {}),
    ("research:formal-setup-claim", "Set up intended claim", "action", "Prepares a message in the conversation panel asking Eigen to choose the intended proof target and create only the Lean files it needs; nothing is sent.", ("formal-setup",), {"hidden_until": "the owner reports the formal setup"}),
))
_wave13b("review", "workspace-review.mjs Review & notes: the note box, the record cards, paging and the proposal list; tests/workspace_control_coverage.test.mjs 'review/comments*', 'review/note-draft', 'review/page-failed', 'review/proposals-more'", (
    ('review:new-note', 'New project note', 'action', 'Opens a box to write a note about the whole project; nothing is saved until you press Save note.', ('comments', 'note-draft', 'comments-closed', 'comments-paged', 'comments-focus'), {'hidden_until': 'the history owner has answered the review page'}),
    ('review:note-save', 'Save note', 'action', 'Saves the note, or the reply, through the history owner against the revision you reviewed; the page says what was recorded and keeps your text if it was not.', ('note-draft',), {'disabled_until': 'text is written'}),
    ('review:note-cancel', 'Cancel', 'action', 'Closes this note box and forgets its draft; nothing is saved.', ('note-draft',), {}),
    ('review:note-review-revision', 'Review current save revision', 'action', "Reads the project's present revision from the history owner and shows it beside the draft; nothing is saved.", ('note-draft',), {}),
    ('review:note-use-revision', 'Use reviewed revision for this draft', 'action', 'Makes the revision you just reviewed the one this draft is saved against; nothing is saved yet.', ('note-draft',), {'hidden_until': 'the current revision was reviewed by pressing Review current save revision'}),
    ('review:record-inspect', 'Inspect full record', 'action', 'Reads this one note or comment from the history owner and shows it alone; nothing is changed.', ('comments', 'note-draft', 'comments-closed', 'comments-paged', 'comments-focus'), {'dynamic': True, 'hidden_until': 'the history owner lists that record'}),
    ('review:record-open-passage', 'Open passage', 'navigation', 'Opens the manuscript passage this note or comment is about, read exactly from the owner; nothing is changed.', ('comments', 'note-draft', 'comments-closed', 'comments-paged', 'comments-focus'), {'dynamic': True, 'hidden_until': 'the record is tied to a manuscript file'}),
    ('review:record-address', 'Address with Eigen', 'action', 'Prepares a message in the conversation panel asking Eigen to address this comment, with its passage; nothing is sent.', ('comments', 'note-draft', 'comments-focus'), {'dynamic': True, 'hidden_until': 'the comment is open and is not a global note'}),
    ('review:record-resolve', 'Resolve', 'action', 'Marks this comment resolved through the history owner, against the revision it was read at; the page says what was recorded.', ('comments', 'note-draft', 'comments-focus'), {'dynamic': True, 'hidden_until': 'the comment is open and is not a global note'}),
    ('review:record-dismiss', 'Dismiss', 'action', 'Marks this comment dismissed through the history owner, against the revision it was read at; the page says what was recorded.', ('comments', 'note-draft', 'comments-focus'), {'dynamic': True, 'hidden_until': 'the comment is open and is not a global note'}),
    ('review:record-reply', 'Reply', 'action', 'Opens a box to reply to this comment as a new note linked to it; nothing is saved until you press Save reply.', ('comments', 'note-draft', 'comments-focus'), {'dynamic': True, 'hidden_until': 'the comment is open and is not a global note'}),
    ('review:record-reopen', 'Reopen', 'action', 'Marks this resolved, dismissed or superseded comment open again through the history owner; its earlier history stays.', ('comments-closed', 'comments-paged'), {'dynamic': True, 'hidden_until': 'the comment is resolved, dismissed or superseded'}),
    ('review:record-reply-to', 'Reply to note', 'navigation', 'Shows the earlier note this reply answers, read exactly from the owner; nothing is changed.', ('comments-closed', 'comments-paged'), {'dynamic': True, 'hidden_until': 'the record is a reply'}),
    ('review:record-change', 'Review change in manuscript', 'navigation', 'Opens the saved manuscript edit this record points to, with its changes shown; nothing is changed.', ('comments-closed', 'comments-paged'), {'dynamic': True, 'hidden_until': 'the record is a saved manuscript edit tied to a file'}),
    ('review:record-history', 'Status history', 'disclosure', 'Shows each status this record had, with when and by whom; nothing is changed.', ('comments-closed', 'comments-paged'), {'dynamic': True, 'hidden_until': 'the record has recorded status changes'}),
    ('review:more', 'More records', 'navigation', "Reads the next page of records from the history owner's own continuation; nothing is changed.", ('comments-closed',), {'hidden_until': 'the history owner issues a next page'}),
    ('review:previous', 'Previous records', 'navigation', 'Reads the page of records before this one; nothing is changed.', ('comments-paged',), {'hidden_until': 'the page is not the first'}),
    ('review:back', 'Back to review page', 'navigation', 'Leaves the single record and returns to the review page where you were; nothing is changed.', ('comments-focus',), {'hidden_until': 'one record is shown alone'}),
    ('review:retry', 'Retry this page', 'action', 'Reads the review page again after a failed read; nothing is changed.', ('page-failed',), {'hidden_until': 'the read of the review page failed'}),
    ('review:proposal-open', 'Review in manuscript', 'navigation', 'Opens this proposed change in the manuscript with its changes shown; the choice is yours there.', ('pending', 'proposals-more'), {'dynamic': True, 'hidden_until': 'the proposal owner lists that proposal'}),
    ('review:proposal-provenance', 'Provenance', 'disclosure', 'Shows where this proposal came from, its version and its recorded state; nothing is changed.', ('pending', 'proposals-more'), {'dynamic': True, 'hidden_until': 'the proposal owner lists that proposal'}),
    ('review:proposal-more', 'Inspect more proposal candidates', 'navigation', "Reads the next page of proposal candidates from the proposal owner's own continuation; nothing is changed.", ('proposals-more',), {'hidden_until': 'the proposal owner issues a next read'}),
))
_wave13b("settings", "workspace-app.mjs, workspace-writing-style.mjs and profile-preferences.mjs App settings > Writing & voice, Structural preferences and Storage & recovery; tests/workspace_control_coverage.test.mjs 'settings/writing-voice', 'settings/storage-recovery*', 'settings/architecture'", (
    ('settings:voice-profile', 'Global voice profile', 'selection', 'Chooses which shared voice profile file this page shows and edits; it does not change the voice profile any project selects.', ('writing-voice',), {}),
    ('settings:storage-project', 'Open project storage and recovery', 'navigation', 'Opens the Settings of the project you came from, where its storage and recovery are shown; nothing is changed.', ('storage-recovery-project',), {'hidden_until': 'the page was opened from a project'}),
    ('settings:storage-choose', 'Choose a project to inspect its saved data', 'navigation', 'Opens the Projects page so you can choose a project whose saved data to inspect; nothing is changed.', ('storage-recovery',), {'hidden_until': 'the page was not opened from a project'}),
    ('writing-style:refresh', 'Refresh style', 'action', 'Reads the shared profile and its guidance again from the writing-style owner; nothing is changed.', ('writing-voice',), {}),
    ('writing-style:guidance', 'Read the shared writing guidance', 'disclosure', 'Shows the operative guidance this profile gives the writer, as saved; nothing is changed.', ('writing-voice',), {}),
    ('writing-style:identity', 'Profile identity', 'disclosure', 'Shows which profile file this is and its revision, as the owner holds them; nothing is changed.', ('writing-voice',), {}),
    ('writing-style:read-profile', 'Read complete profile', 'action', 'Reads the whole profile text from the owner and shows it; nothing is changed.', ('writing-voice',), {}),
    ('writing-style:edit-profile', 'Edit shared profile', 'action', 'Opens the profile text for editing against the revision you read; nothing is saved until you save it.', ('writing-voice',), {'disabled_until': 'the owner reports the profile as editable from this repository'}),
    ('writing-style:sources', 'Sources and examples', 'action', 'Shows the sources and examples the profile was calibrated from, as the owner records them; nothing is changed.', ('writing-voice',), {}),
    ('writing-style:suggestions', 'Generated suggestions', 'action', 'Shows the preference suggestions saved for this profile, to compare one with the current text; nothing is changed.', ('writing-voice',), {}),
    ('preferences:refresh', 'Refresh preferences', 'action', 'Reads the effective preferences and their saved suggestions again from the profile owner; nothing is changed.', ('preferences', 'architecture'), {}),
    ('preferences:read-effective', 'Read effective preferences', 'action', 'Reads the complete effective preferences from the owner and shows them; nothing is changed.', ('preferences', 'architecture'), {}),
    ('preferences:generate', 'Generate suggestion', 'action', 'Prepares a request in a conversation asking Eigen for a preference suggestion from your recent work; nothing is sent.', ('preferences', 'architecture'), {}),
    ('preferences:edit', 'Edit structural preferences', 'action', 'Opens the structural preferences for editing against the revision read; nothing is saved until you preview and save.', ('architecture',), {'hidden_until': 'the page can edit this family of preferences'}),
))
# structural preferences mounted with editing offered show the same controls as the saved-candidates mount
for _ident, _row in CONTROL_DECLARATIONS.items():
    if _row["view"] == "settings" and "preferences" in _row["states"] and "architecture" not in _row["states"]:
        _row["states"] = [*_row["states"], "architecture"]
# the category strip and the scope ladder stay on screen whichever category is chosen
for _ident in ("settings:family", "settings:category-models", "settings:category-voice", "settings:category-architecture", "settings:category-runtime", "settings:category-storage"):
    CONTROL_DECLARATIONS[_ident]["states"] = [*CONTROL_DECLARATIONS[_ident]["states"], *(x for x in ("writing-voice", "storage-recovery", "storage-recovery-project") if x not in CONTROL_DECLARATIONS[_ident]["states"])]
_wave13b("manuscript", "manuscript-editor.mjs Writing > TeX, the source pane; tests/workspace_control_coverage.test.mjs 'manuscript/source-tex'", (
    ('writing:source-file', 'Source file', 'selection', 'Chooses which source file of the manuscript the TeX pane shows; unsaved edits are kept as a draft for the file they belong to.', ('source-tex',), {}),
    ('writing:source-reload', 'Reload saved source', 'action', 'Reads the shown file again from its owner and replaces the pane with what is saved; an unsent draft is kept until you discard it.', ('source-tex',), {}),
    ('writing:source-preamble', 'Preamble', 'action', 'Opens the manuscript preamble (the lines before the document begins) in the pane; nothing is changed.', ('source-tex',), {}),
    ('writing:source-copy', 'Copy draft', 'action', 'Copies the draft text you are editing to the clipboard; nothing is saved or sent.', ('source-tex',), {}),
    ('writing:source-compare', 'Compare saved source', 'action', 'Shows your draft beside the saved source of the file, to see what differs; nothing is saved.', ('source-tex',), {}),
    ('writing:source-discard', 'Discard source draft', 'action', 'Throws away the draft of this file and shows the saved source again; what was saved is not changed.', ('source-tex',), {}),
))
# the editor band stays on screen over the TeX pane
for _ident in ("writing:mode-write", "writing:mode-tex", "writing:tools"):
    CONTROL_DECLARATIONS[_ident]["states"] = [*CONTROL_DECLARATIONS[_ident]["states"], "source-tex"]
_wave13b("work", "workspace-work.mjs Tasks > one task: blockers, completion evidence and the next-step row; tests/workspace_control_coverage.test.mjs work states", (
    ('work:blocker-subject', 'Waiting-on Work', 'navigation', 'Opens the other Work this one waits on, by the title its owner gives it; nothing is changed.', ('seeded',), {'dynamic': True, 'hidden_until': 'the owner names another Work as the subject of a blocker'}),
    ('work:blocker-action', 'Blocker next step', 'action', "Runs or reads the further step the owner offers for this blocker; the owner's answer is shown beside it.", ('seeded',), {'dynamic': True, 'hidden_until': 'the owner offers more than one step for a blocker'}),
    ('work:blocker-read', 'Read recorded details', 'action', 'Reads the exact record behind this blocker from its owner and shows it; nothing is changed.', ('seeded',), {'dynamic': True, 'hidden_until': 'the owner issues a read handle for a blocker'}),
    ('work:blocker-exact', 'Exact reason and required conditions', 'disclosure', "Shows the owner's exact reason this task is blocked and what must be true to clear it; nothing is changed.", ('seeded',), {'dynamic': True, 'hidden_until': 'the task has a blocker'}),
    ('work:completion-evidence', 'Exact completion evidence and changed inputs', 'disclosure', 'Shows the exact currentness record of this completed task, including which inputs changed since it was accepted; nothing is changed.', ('seeded',), {'dynamic': True, 'hidden_until': 'the task is complete and its acceptance is not current'}),
    ('work:evidence-read', 'Read evidence', 'action', "Reads one piece of this task's completion evidence from its owner and shows it; nothing is changed.", ('seeded',), {'dynamic': True, 'hidden_until': 'the owner issues a read handle for completion evidence'}),
    ('work:next-go', 'Go to this step', 'action', 'Moves focus to the step this task waits on, lower on the page; nothing is changed.', ('seeded',), {'hidden_until': 'a blocker offers a permitted next step'}),
    ('work:review-open', 'Record a review phase', 'action', 'Opens the form that records a review phase for this task, where you choose and save it; nothing is saved by opening it.', ('seeded',), {'hidden_until': 'the owner permits recording a review phase'}),
    ('work:open-contained', 'Open its contained Work', 'navigation', 'Opens the Work this task contains, in the navigator; nothing is changed.', ('seeded',), {'dynamic': True, 'hidden_until': 'the task contains other Work'}),
    ('work:needs-open', 'See what this task needs', 'action', 'Moves focus to the list of what this task waits on, or what needs rechecking, lower on the page; nothing is changed.', ('seeded',), {'hidden_until': 'the task has a blocker or a completion that needs review'}),
))
# where the controls of the Tasks states render (observed by the coverage harness; wave 13b)
_WORK_NEW = {"work:blocker-subject": ["task-waiting"], "work:blocker-action": ["task-review-required"], "work:blocker-read": ["task-held"], "work:blocker-exact": ["next-action-offered", "task-review-required", "task-waiting", "task-held", "panels-open"], "work:completion-evidence": ["task-review-required"], "work:evidence-read": ["task-review-required"], "work:next-go": ["next-action-offered", "task-review-required", "task-waiting", "task-held", "panels-open"], "work:review-open": ["selected", "next-action-offered", "panels-open"], "work:open-contained": ["task-contained"], "work:needs-open": ["next-action-offered", "task-review-required", "task-waiting", "task-held", "panels-open"]}
_WORK_ADD = {"tasks:add-open": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:nav-filter": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:item": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:subtasks": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:more-tasks": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:flat-catalogue": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:more-work": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:namespaces": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:namespace-read": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:dev-workflows": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:close": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:status-open": ["task-contained", "task-review-required", "task-waiting", "task-held"], "task:trail": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:edit-open": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:action-template": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:action-inspect": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:progress-open": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:step-waits-on": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:progress-basis": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:progress-read": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:completion-basis": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:review-setup": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:relation-tab": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:relation-open": ["task-contained", "task-waiting"], "work:neighbourhood": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:use-for-message": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:related-turns": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:reinspect": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:status-details": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:history-read": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:action-context": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:authored-open": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:save-authored": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:attempt": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:containment-open": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:containment-save": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:disposition": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:disposition-open": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:status-choice": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:choose-evidence": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:evidence-paths": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:save-status": ["task-contained", "task-review-required", "task-waiting", "task-held"], "tasks:add": ["task-contained", "task-review-required", "task-waiting", "task-held"], "tasks:add-summary": ["task-contained", "task-review-required", "task-waiting", "task-held"], "tasks:add-submit": ["task-contained", "task-review-required", "task-waiting", "task-held"], "tasks:add-more": ["task-contained", "task-review-required", "task-waiting", "task-held"], "tasks:add-type": ["task-contained", "task-review-required", "task-waiting", "task-held"], "tasks:add-parent": ["task-contained", "task-review-required", "task-waiting", "task-held"], "tasks:add-prerequisites": ["task-contained", "task-review-required", "task-waiting", "task-held"], "tasks:add-exact": ["task-contained", "task-review-required", "task-waiting", "task-held"], "work:next-step": ["task-review-required", "task-waiting", "task-held"], "work:prerequisites": ["task-review-required", "task-waiting", "task-held"]}
for _ident, _st in _WORK_NEW.items():
    CONTROL_DECLARATIONS[_ident]["states"] = list(_st)
for _ident, _st in _WORK_ADD.items():
    CONTROL_DECLARATIONS[_ident]["states"] = [*CONTROL_DECLARATIONS[_ident]["states"], *(x for x in _st if x not in CONTROL_DECLARATIONS[_ident]["states"])]
_wave13b("material", "workspace-material.mjs Sources > shared material, the link form; tests/workspace_control_coverage.test.mjs 'material/bindings-artifact'", (
    ("material:artifact-scope", "Artifact scope", "selection", "Chooses whether the artifact path is read in the project's files or in the manuscript's files; it applies when you inspect the material.", ("bindings-artifact",), {"hidden_until": "the material owner type is Project artifact"}),
))
# where the controls of the material states render (observed by the coverage harness; wave 13b)
_MATERIAL_NEW = {"material:artifact-scope": ["bindings-artifact"]}
_MATERIAL_ADD = {"material:add-document": ["bindings-artifact"], "material:refresh-sources": ["bindings-artifact"], "material:refresh-shared": ["bindings-artifact"], "material:binding": ["bindings-artifact"], "material:read": ["bindings-artifact"], "material:file-manage": ["bindings-artifact"], "material:file": ["bindings-artifact"], "material:file-more": ["bindings-artifact"], "material:link-options": ["bindings-artifact"], "material:owner-type": ["bindings-artifact"], "material:owner": ["bindings-artifact"], "material:inspect": ["bindings-artifact"], "material:readers": ["bindings-artifact"]}
for _ident, _st in _MATERIAL_NEW.items():
    CONTROL_DECLARATIONS[_ident]["states"] = list(_st)
for _ident, _st in _MATERIAL_ADD.items():
    CONTROL_DECLARATIONS[_ident]["states"] = [*CONTROL_DECLARATIONS[_ident]["states"], *(x for x in _st if x not in CONTROL_DECLARATIONS[_ident]["states"])]
_wave13b("research-workbench", "research-workbench.mjs, research-workbench-view.mjs and research-geometry.mjs Explore: the object overview, Consequences, Handover and Settings tabs and the relation views; tests/workspace_control_coverage.test.mjs 'research-workbench/object-*', 'workflow-settings', 'relation-*'", (
    ('research:inspect-owner', 'Inspect owner record', 'action', "Opens the exact record the owner holds behind this object's history, in the inspector; nothing is changed.", ('object-overview',), {'hidden_until': 'the owner issues a history read for the object'}),
    ('research:identity-facts', 'Identity, currentness and exact owner facts', 'disclosure', "Shows the object's exact identity, the basis and scope it was read at, its standing and coverage, as the owner returned them; nothing is changed.", ('object-overview',), {}),
    ('research:dependents', 'Inspect recorded dependents', 'action', 'Reads what the owner records as depending on this object and shows it; nothing is changed.', ('object-overview',), {'hidden_until': 'the owner issues a dependents read for the object'}),
    ('research:handover-add', 'Add this inspected object to handover choices', 'action', 'Adds the object you are looking at, with its inspected basis, to the choices for a handover; nothing is sent.', ('object-overview',), {'hidden_until': 'the owner issues a handover entry for the object'}),
    ('research:setting-facts', 'Exact setting facts and edit guard', 'disclosure', "Shows the owner's exact facts for this setting and the guard an edit would need; nothing is changed.", ('object-overview',), {}),
    ('research:setting-origin', 'Where a setting comes from', 'disclosure', "Shows which scope this setting's value comes from, from the owner's own chain; nothing is changed.", ('object-overview',), {'dynamic': True, 'hidden_until': 'the owner gives a chain of origins for that setting'}),
    ('research:setting-instructions', 'Complete instructions', 'disclosure', 'Shows the complete instruction text of this workflow step; nothing is changed.', ('object-overview',), {'hidden_until': 'the step carries instruction text'}),
    ('research:frontier-explore', 'Explore supplied boundary', 'navigation', 'Reads the next neighbourhood the owner supplies at this boundary of the shown relations; nothing is changed.', ('object-overview',), {'dynamic': True, 'hidden_until': 'the owner supplies a read at the frontier of the neighbourhood'}),
    ('research:restart-neighbourhood', 'Read current neighbourhood', 'navigation', "Reads the neighbourhood again from its start through the owner's own restart read; nothing is changed.", ('object-overview',), {'hidden_until': 'the owner issues a restart read for the neighbourhood'}),
))
# where the controls of the explore states render (observed by the coverage harness; wave 13b)
_EXPLORE_NEW = {"research:inspect-owner": ["object-overview"], "research:identity-facts": ["object-overview"], "research:dependents": ["object-consequences"], "research:handover-add": ["object-handover"], "research:setting-facts": ["workflow-settings"], "research:setting-origin": ["workflow-settings"], "research:setting-instructions": ["workflow-settings"], "research:frontier-explore": ["relation-outline"], "research:restart-neighbourhood": ["relation-outline", "relation-map"]}
_EXPLORE_ADD = {"research:overview": ["object-overview", "object-consequences", "object-handover", "workflow-settings", "relation-outline", "relation-map"], "research:action": ["object-overview", "object-consequences", "object-handover", "workflow-settings", "relation-outline", "relation-map"], "research:help": ["object-overview", "object-consequences", "object-handover", "workflow-settings", "relation-outline", "relation-map"], "research:refresh": ["object-overview", "object-consequences", "object-handover", "workflow-settings", "relation-outline", "relation-map"], "research:outline-toggle": ["object-overview", "object-consequences", "object-handover", "workflow-settings", "relation-outline", "relation-map"], "research:inspector-toggle": ["object-overview", "object-consequences", "object-handover", "workflow-settings", "relation-outline", "relation-map"], "research:conversation": ["object-overview", "object-consequences", "object-handover", "workflow-settings", "relation-outline", "relation-map"], "research:orientation": ["object-overview", "object-consequences", "object-handover", "workflow-settings", "relation-outline", "relation-map"], "research:representation": ["object-overview", "object-consequences", "object-handover", "workflow-settings", "relation-outline", "relation-map"], "research:timeline": ["object-overview", "object-consequences", "object-handover", "workflow-settings", "relation-outline", "relation-map"], "research:object": ["relation-outline"]}
for _ident, _st in _EXPLORE_NEW.items():
    CONTROL_DECLARATIONS[_ident]["states"] = list(_st)
for _ident, _st in _EXPLORE_ADD.items():
    CONTROL_DECLARATIONS[_ident]["states"] = [*CONTROL_DECLARATIONS[_ident]["states"], *(x for x in _st if x not in CONTROL_DECLARATIONS[_ident]["states"])]
# ---- wave 13b id sweep: the controls of the modules the first pass left out (end) ----

# Every declared state names its source evaluator below. The omnibus registry distinguishes its own
# mounts from the named focused evaluators. `harness` names the real shell (mountWorkspace over the markup-parsing DOM
# double tests/helpers/html_dom.mjs with owner-shaped answers tests/helpers/shell_fixture.mjs) or the
# view's own existing harness. Real-browser geometry, focus order and provider behaviour stay the root's C12.
_FULL = "the real shell (mountWorkspace) over tests/helpers/shell_fixture.mjs"
STATE_COVERAGE: dict[str, dict[str, dict[str, str]]] = {
    "workflows": {**{state: {"coverage": "source", "harness": "mountWorkflowEditor native progression and draft retention; tests/workflow_operation_frontend.test.mjs"} for state in ("empty", "runs", "guide", "draft-design")}, **{state: {"coverage": "source", "harness": "mountWorkflowEditor; tests/workflow_first_use.test.mjs exact saved child and draft separation"} for state in ("selected", "saved-reading")},
                  **{state: {"coverage": "source", "harness": "mountWorkflowEditor with actual public owner history/body offers, explicit disclosure; tests/workflow_history_frontend.test.mjs"} for state in ("history-offered", "history-open", "history-next-offered", "saved-body-partial", "saved-body-complete", "lineage-prepare-offered")},
                  **{state: {"coverage": "source", "harness": "focused conditional workflow mounts over public owner samples and controlled transport; tests/workflow_operation_frontend.test.mjs"} for state in ("check-offered", "check-result", "withdraw-offered", "observation-offered", "observation-next-offered", "river-reads-offered", "run-detail-offered", "stop-offered", "stop-pending", "stop-resend-offered")},
                  "river-run": {"coverage": "source", "harness": "mountWorkflowRiver (the opened run's river) over owner-shaped river reads, and the opened run's declared controls read from workspace-workflow-editor.mjs; tests/workflow_river.test.mjs"}},
    "review-evidence":{name:{"coverage":"source","harness":"openReviewEvidence over tests/workspace_review_evidence.test.mjs owner-emitted responses; browser layout separately observed"} for name in ("aggregate","list","support","changed")},
    "source-inspector":{"reading":{"coverage":"source","harness":"openSourceInspector, tests/workspace_source_inspector.test.mjs"}},
    "historical-obligations":{"reading":{"coverage":"source","harness":"openHistoricalObligations, tests/workspace_source_inspector.test.mjs"}},
    "backlog":{state:{"coverage":"source","harness":"mountBacklog controlled owner catalogue/planning, tests/workspace_backlog.test.mjs; real browser acceptance separate"} for state in ("catalogue","selected","planning","pending")},
    "research-workbench": {**{state: {"coverage": "source", "harness": "mountResearchWorkbench over public owner-shaped exact source window; tests/research_workbench.test.mjs"} for state in ("workspace", "source-selected")},
                           "focus-inspection-offered": {"coverage": "source", "harness": "actual relationship geometry Inspector with owner-issued detail_read; tests/research_geometry.test.mjs"}},
    "shell": {**{state: {"coverage": "source", "harness": _FULL} for state in _SHELL},
              "global-entry": {"coverage": "source", "harness": "global mountGlobalHelp; tests/first_use_shell.test.mjs"},
              "project-tools-open": {"coverage": "source", "harness": _FULL + ", More project tools opened explicitly; tests/human_workspace_shell.test.mjs"},
              "switcher-open": {"coverage": "source", "harness": _FULL + ", the frame's project switcher opened over the library read; tests/workspace_control_coverage.test.mjs"},
              "more-open": {"coverage": "source", "harness": _FULL + ", the frame's More list opened; tests/workspace_control_coverage.test.mjs"}},
    "now": {"page": {"coverage": "source", "harness": "mountNow over owner-shaped live-work, catalogue and library reads (markup DOM double); tests/workspace_control_coverage.test.mjs"}},
    "projects": {"page": {"coverage": "source", "harness": "initProjectWork on the Projects page over an owner-shaped library read (markup DOM double); tests/workspace_control_coverage.test.mjs"}},
    "dependencies": {"page": {"coverage": "source", "harness": "mountWorkspaceDependencies over an owner-shaped dependency read (markup DOM double); tests/workspace_control_coverage.test.mjs"}},
    "owners": {"page": {"coverage": "source", "harness": "mountOwnerDiscovery over an owner-shaped discovery read; tests/workspace_control_coverage.test.mjs"}},
    "overview": {"ready": {"coverage": "source", "harness": _FULL}, "no-manuscript": {"coverage": "source", "harness": _FULL + " with capabilities.manuscript false"}},
    "work": {"trail-offered": {"coverage": "source", "harness": "issued provenance entry/controller; tests/task_trail.test.mjs"},
             "list-open": {"coverage": "source", "harness": "selected Task with Choose another task opened explicitly; tests/human_workspace_shell.test.mjs"},
             "next-action-offered": {"coverage": "source", "harness": _FULL + ", selected Task with an actual permitted blocker read action"},
             "catalogue": {"coverage": "source", "harness": _FULL + ", Tasks with the existing task creator"},
             "selected": {"coverage": "source", "harness": _FULL + ", selected Tasks with the existing task creator"},
             "read-only": {"coverage": "source", "harness": "mountOperatorWork readOnly"},
             **{state: {"coverage": "source", "harness": "focused mounted selected Task continuity controls over owner-shaped answers; tests/eigen_continuity_frontend.test.mjs"}
                for state in ("continuity-continue-offered", "continuity-proof-offered", "continuity-unresolved", "continuity-resend-offered",
                              "continuity-review-offered", "continuity-read-failed")},
             # WAVE 11 CENSUS REPAIRS
             "draft-compared": {"coverage": "source", "harness": "mountOperatorWork with a stale authored-work draft and Compare pressed; tests/work_port.test.mjs"},
             "result-offered": {"coverage": "source", "harness": "mountOperatorWork over a completed Task with one recorded route; tests/human_workspace_shell.test.mjs"}},
    "material": {"files": {"coverage": "source", "harness": "mountMaterial with recorded files"},
                 "readers-open": {"coverage": "source", "harness": "existing direct Material mount with Other project reading views explicitly opened; tests/workspace_control_coverage.test.mjs"},
                 "bindings": {"coverage": "source", "harness": _FULL + ", Sources with its selected binding and Optional: link an existing source open"},
                 "retained-source": {"coverage": "source", "harness": _FULL + ", Material with one retained original capability and shared binding; help targets only"}},
    "history": {"timeline": {"coverage": "source", "harness": "mountHistory"}, "record-open": {"coverage": "source", "harness": "mountHistory, one entry opened"},
                "graphs": {"coverage": "source", "harness": _FULL + ", Activity with the Graphs tab chosen"}},
    "settings": {"families": {"coverage": "source", "harness": "mountAppSettings"}, "project": {"coverage": "source", "harness": _FULL + ", Settings view"},
                 "preferences": {"coverage": "source", "harness": "mountProfilePreferences with saved candidates"}},
    "argument": {"record": {"coverage": "source", "harness": "renderConceptRecord"}},
    "reader-plan": {"empty": {"coverage": "source", "harness": "mountReaderPlan with no sections"}, "selected": {"coverage": "source", "harness": "mountReaderPlan on the display fixture"},
                    "read-only": {"coverage": "source", "harness": "mountReaderPlan readOnly"}},
    "research": {"results": {"coverage": "source", "harness": "mountEvidence with one recorded result"}, "empty": {"coverage": "source", "harness": _FULL + ", Research with no results"}},
    "manuscript": {"source-host": {"coverage": "source", "harness": "native Writing artifact host; tests/human_workspace_shell.test.mjs"},
                   "tools-open": {"coverage": "source", "harness": "native Writing editor with Document tools opened explicitly; tests/human_workspace_shell.test.mjs"},
                   "opening": {"coverage": "source", "harness": _FULL + ", Manuscript view before the reader is ready"},
                   "write": {"coverage": "source", "harness": "createManuscriptEditor with a ready reader frame (markup DOM double)"},
                   "setup-open": {"coverage": "source", "harness": _FULL + ", Document setup opened (owner document offers a template)"},
                   "template-open": {"coverage": "source", "harness": "renderTemplateCandidate without a reviewed proof"},
                   "template-reviewed": {"coverage": "source", "harness": "renderTemplateCandidate with its reviewed proof"}},
    "review": {"pending": {"coverage": "source", "harness": _FULL + ", Review with one queued proposal"}, "empty": {"coverage": "source", "harness": _FULL + ", Review with an empty queue"}, "comments": {"coverage": "source", "harness": _FULL + ", Review Comments with an exact-origin saved passage comment; help targets only"}},
    "presentation": {"not-built": {"coverage": "source", "harness": _FULL + ", Figures & output with the owner-generated document"},
                     "build-failed": {"coverage": "source", "harness": _FULL + ", Figures & output with a failed build"}},
    "conversation": {"open": {"coverage": "source", "harness": "WorkspaceSession.prototype.appendTurn over a stubbed session"},
                     "composer": {"coverage": "source", "harness": _FULL + ", Conversation opened"},
                     "options-open": {"coverage": "source", "harness": "full mounted WorkspaceSession and chrome, Options opened explicitly; tests/human_workspace_shell.test.mjs"},
                     "context-open": {"coverage": "source", "harness": _FULL + ", Conversation opened and Context opened"}},
    "shared": {"topology-plain": {"coverage": "source", "harness": "mountTopology, three nodes"}, "topology-folded": {"coverage": "source", "harness": "mountTopology, fifty nodes"},
               "guard-inspector": {"coverage": "source", "harness": "renderReaderGuard on the six subjects"}},
}

# ---- wave 13 id sweep: states added to existing views (begin) ----
VIEW_STATES["overview"]["panels-open"] = "Home with every disclosure on the page opened"
STATE_COVERAGE["overview"]["panels-open"] = {"coverage": "source", "harness": _FULL + ", the Home page with every disclosure opened; tests/workspace_control_coverage.test.mjs"}
VIEW_STATES["settings"]["panels-open"] = "project Settings with every disclosure on the page opened"
STATE_COVERAGE["settings"]["panels-open"] = {"coverage": "source", "harness": _FULL + ", the project Settings page with every disclosure opened; tests/workspace_control_coverage.test.mjs"}
VIEW_STATES["material"]["panels-open"] = "Sources with every disclosure on the page opened"
STATE_COVERAGE["material"]["panels-open"] = {"coverage": "source", "harness": _FULL + ", the Sources page with every disclosure opened; tests/workspace_control_coverage.test.mjs"}
VIEW_STATES["research"]["panels-open"] = "Research with every disclosure on the page opened"
STATE_COVERAGE["research"]["panels-open"] = {"coverage": "source", "harness": _FULL + ", the Research page with every disclosure opened; tests/workspace_control_coverage.test.mjs"}
VIEW_STATES["history"]["panels-open"] = "Activity with every disclosure on the page opened"
STATE_COVERAGE["history"]["panels-open"] = {"coverage": "source", "harness": _FULL + ", the Activity page with every disclosure opened; tests/workspace_control_coverage.test.mjs"}
# wave 13b: the states of the controls declared above for modules the first pass left out
VIEW_STATES["conversation"]["reading-partial"] = "one saved message read in pages, the first page shown and a next page offered"
STATE_COVERAGE["conversation"]["reading-partial"] = {"coverage": "source", "harness": "mountMessageReading over the owner's captured message-part read in a short page; tests/workspace_control_coverage.test.mjs"}
VIEW_STATES["conversation"]["reading-failed"] = "one saved message whose next page could not be read: the shown text is kept and Retry and Restart are offered"
STATE_COVERAGE["conversation"]["reading-failed"] = {"coverage": "source", "harness": "mountMessageReading over the owner's captured message-part read, a continuation refused; tests/workspace_control_coverage.test.mjs"}
for _mode, _words, _how in (
        ("new", "the Literature source box for a retained original with no saved source", "the box over a standing of NONE"),
        ("recorded", "the Literature source box for an original that already has a saved source", "the box over a standing of RECORDED"),
        ("lost", "the Literature source box after a submission whose answer was lost: the submission is retained", "a Save whose owner answer never came"),
        ("found", "the Literature source box where a retained submission turned out to be saved: the owner now holds the source", "Check Literature source answered RECORDED"),
        ("rejected", "the Literature source box after the owner rejected the submission before any effect", "a Save refused with the owner's closed-schema refusal"),
        ("edited", "the Literature source box after Edit details: the rejected submission sits beside the editable draft", "Edit details pressed on a rejected submission")):
    VIEW_STATES["material"]["literature-" + _mode] = _words
    STATE_COVERAGE["material"]["literature-" + _mode] = {"coverage": "source", "harness": "openRetainedSourceLiterature over the shapes tests/retained_source_literature.test.mjs holds for the Literature owner, " + _how + "; tests/workspace_control_coverage.test.mjs"}
VIEW_STATES["review"]["response-partial"] = "one complete review response read in pages, the first page shown and a next page offered"
STATE_COVERAGE["review"]["response-partial"] = {"coverage": "source", "harness": "openFeedbackReply over the owner's captured message-part read in a short page; tests/workspace_control_coverage.test.mjs"}
VIEW_STATES["review"]["response-failed"] = "one complete review response whose next page could not be read: the shown text is kept and Retry and Restart are offered"
STATE_COVERAGE["review"]["response-failed"] = {"coverage": "source", "harness": "openFeedbackReply over the owner's captured message-part read, a continuation refused; tests/workspace_control_coverage.test.mjs"}

_COMMENT = "openFeedbackComment over the owner's captured answers of the seeded throwaway project (tests/fixtures/shell/captured-w13c-comment.json): authoring/correction-prepare, work/state and work/delivery route-preview, "
VIEW_STATES["review"]["comment-new"] = "the passage comment dialog right after the owner inspected the selected passage: Reviewers and limits closed, nothing typed or saved"
STATE_COVERAGE["review"]["comment-new"] = {"coverage": "source", "harness": _COMMENT + "the dialog as it opens; tests/workspace_control_coverage.test.mjs"}
VIEW_STATES["review"]["comment-routing"] = "the passage comment dialog with Reviewers and limits opened: the owner's list of existing Work is shown, no Work chosen"
STATE_COVERAGE["review"]["comment-routing"] = {"coverage": "source", "harness": _COMMENT + "Reviewers and limits pressed; tests/workspace_control_coverage.test.mjs"}
VIEW_STATES["review"]["comment-routed"] = "the passage comment dialog with an existing Work chosen: the owner's preview of its review route, the saved settings choice and the limits are shown"
STATE_COVERAGE["review"]["comment-routed"] = {"coverage": "source", "harness": _COMMENT + "the first Work chosen; tests/workspace_control_coverage.test.mjs"}
VIEW_STATES["review"]["comment-lost"] = "the passage comment dialog after Save was sent and the owner's answer never came: the exact request is retained and a check is offered"
STATE_COVERAGE["review"]["comment-lost"] = {"coverage": "source", "harness": _COMMENT + "Save pressed with the connection lost (the one write is refused, no answer invented); tests/workspace_control_coverage.test.mjs"}
VIEW_STATES["review"]["comment-unrecorded"] = "the passage comment dialog after Check save found no record of the lost Save: the same request may be retried or settled"
STATE_COVERAGE["review"]["comment-unrecorded"] = {"coverage": "source", "harness": _COMMENT + "Check save pressed, answered by the owner's reconcile and comparison reads; tests/workspace_control_coverage.test.mjs"}

VIEW_STATES["manuscript"]["frame-toolbar"] = "the editor frame's own toolbar on the Writing page: smaller and larger text, Questions & context, Find and Reading options closed"
STATE_COVERAGE["manuscript"]["frame-toolbar"] = {"coverage": "source", "harness": "the real walk.html toolbar markup with the toolbar lines of writing-panel.mjs run over it, a stand-in walk and the owner-free local state; tests/workspace_control_coverage.test.mjs"}
VIEW_STATES["manuscript"]["frame-reading"] = "the editor frame's toolbar with Reading options opened: open points, text width, your changes and autosave"
STATE_COVERAGE["manuscript"]["frame-reading"] = {"coverage": "source", "harness": "the same toolbar with Reading options opened; tests/workspace_control_coverage.test.mjs"}

VIEW_STATES["manuscript"]["frame-bubble"] = "the editor frame's selection toolbar shown over selected text: Comment, Discuss, Revise, Reference, Citation and Queue request"
STATE_COVERAGE["manuscript"]["frame-bubble"] = {"coverage": "source", "harness": "the selection-toolbar lines of writing-panel.mjs, cut from its text and run over a stand-in walk; tests/workspace_control_coverage.test.mjs"}
VIEW_STATES["manuscript"]["frame-menu"] = "the passage menu opened by a right-click on a paragraph of the seeded project's manuscript, over the frame's own captured model rows"
STATE_COVERAGE["manuscript"]["frame-menu"] = {"coverage": "source", "harness": "the contextmenu handler of writing-panel.mjs, cut from its text and run over the paragraph rows and insertion point the seeded project's frame reports (tests/fixtures/shell/captured-w13c-frame.json); tests/workspace_control_coverage.test.mjs"}

VIEW_STATES["manuscript"]["frame-save-warning"] = "the editor frame's status line showing a save warning while you have unsaved text, with a draft whose paragraph another writer changed"
STATE_COVERAGE["manuscript"]["frame-save-warning"] = {"coverage": "source", "harness": "writing-panel.mjs offerKeep cut from its text and run over a stand-in walk reporting an unsaved draft whose paragraph another writer changed (editState().moved); tests/workspace_control_coverage.test.mjs"}
VIEW_STATES["manuscript"]["frame-find"] = "the Find box opened over the manuscript by the editor frame's Find"
STATE_COVERAGE["manuscript"]["frame-find"] = {"coverage": "source", "harness": "walk-card.mjs openFindDialog imported and called over the frame's skeleton markup; tests/workspace_control_coverage.test.mjs"}
VIEW_STATES["manuscript"]["frame-context"] = "the questions and context pane opened on the seeded project's paragraph, over the owner's own answer to GET /concepts/plan/context: no canonical section and no point"
STATE_COVERAGE["manuscript"]["frame-context"] = {"coverage": "source", "harness": "writing-panel.mjs openPoints cut from its text and run over the owner's captured concepts plan context answer for the paragraph (tests/fixtures/shell/captured-w13c-frame.json); tests/workspace_control_coverage.test.mjs"}

VIEW_STATES["manuscript"]["frame-queue"] = "the Queue a request box opened on the seeded project's paragraph"
STATE_COVERAGE["manuscript"]["frame-queue"] = {"coverage": "source", "harness": "writing-panel.mjs queueRequest cut from its text and called with the paragraph row and its text from the seeded project's frame (tests/fixtures/shell/captured-w13c-frame.json); tests/workspace_control_coverage.test.mjs"}
# wave 13b: the Graphs tab (session analytics) one state per view, mounted by the real shell over the owners' captured answers
STATE_COVERAGE["history"]["graphs"] = {"coverage": "source", "harness": _FULL + ", Activity with the Graphs tab chosen, over the owners' captured analytics answers (tests/fixtures/shell/captured-w13b-graphs.json); tests/workspace_control_coverage.test.mjs"}
for _state, _words, _how in (
        ("graphs-analysis", "Graphs with its Graphs & analysis view chosen: the plots and the call filters", "the Graphs & analysis view over the owners' captured answers"),
        ("graphs-trace", "Graphs with Selected activity chosen: one recorded event per row and a further page", "the Selected activity view over the owners' captured trace, with its next page"),
        ("graphs-usage", "Graphs with Usage chosen: reported usage and one card per saved attempt", "the Usage view over the owners' captured answer"),
        ("graphs-delivery", "Graphs with Delivery chosen: one recorded delivery receipt per turn", "the Delivery view over the owners' captured answer"),
        ("graphs-feedback", "Graphs with Feedback chosen and the owner listing one recorded feedback record", "the Feedback view over the owner's actual feedback emission (tests/fixtures/session-analytics-joined-3e69533c3.json, project renamed)"),
        ("graphs-commissioned", "Graphs with a listed conversation that a saved turn commissioned", "the Overview over the owner's actual sessions emission with a commissioning turn (tests/fixtures/session-analytics-joined-3e69533c3.json, project renamed)"),
        ("graphs-failed", "Graphs whose view could not be read: the owner's refusal and Retry", "a failed owner read of the view"),
        ("graphs-record", "the exact saved record behind one Selected activity row, opened from Inspect recorded basis", "renderAnalyticsRecord over the owner's captured record read"),
        ("graphs-note", "the response note box opened by Note on latest reply", "openResponseFeedback over the response target the owner names")):
    VIEW_STATES["history"][_state] = _words
    STATE_COVERAGE["history"][_state] = {"coverage": "source", "harness": (_how if _state in ("graphs-record", "graphs-note") else _FULL + ", " + _how) + "; tests/workspace_control_coverage.test.mjs"}
for _state, _words, _how in (
        ("note-draft", "Review & notes, Comments, with the New project note box open and the current save revision reviewed", "the shell's Comments tab over a captured-shape saved comment, New project note and Review current save revision pressed"),
        ("comments-closed", "Review & notes, Closed: a resolved comment with its status history, a reply and a saved manuscript edit, a further page offered", "the shell's Closed tab over owner-shaped records of the history owner"),
        ("comments-paged", "Review & notes, Closed, after More records: the second page with Previous records", "the shell's Closed tab, More records pressed, over owner-shaped records"),
        ("comments-focus", "Review & notes, one comment read alone, with Back to review page", "the shell's Comments tab, Inspect full record pressed"),
        ("page-failed", "Review & notes whose Comments page could not be read: the owner's refusal and Retry", "the shell's Comments tab over a refused history read"),
        ("proposals-more", "Review & notes with a proposal listed and a further page of candidates offered", "the shell over one queued proposal whose owner issues a next read")):
    VIEW_STATES["review"][_state] = _words
    STATE_COVERAGE["review"][_state] = {"coverage": "source", "harness": _FULL + ", " + _how + "; tests/workspace_control_coverage.test.mjs"}
for _state, _words, _how in (
        ("writing-voice", "App settings with Writing & voice chosen: the shared voice profile and its guidance", "mountAppSettings over the owner-shaped app-settings answer, Writing & voice pressed"),
        ("storage-recovery", "App settings with Storage & recovery chosen, not opened from a project", "mountAppSettings, Storage & recovery pressed"),
        ("storage-recovery-project", "App settings with Storage & recovery chosen, opened from a project", "mountAppSettings with return_project in the address, Storage & recovery pressed"),
        ("architecture", "Structural preferences with editing offered: refresh, read effective, generate and edit", "mountProfilePreferences with saved candidates and editing enabled")):
    VIEW_STATES["settings"][_state] = _words
    STATE_COVERAGE["settings"][_state] = {"coverage": "source", "harness": _how + "; tests/workspace_control_coverage.test.mjs"}
VIEW_STATES["manuscript"]["source-tex"] = "Writing with the TeX source pane open: the file choice, reload, preamble, copy, compare and discard"
STATE_COVERAGE["manuscript"]["source-tex"] = {"coverage": "source", "harness": "createManuscriptEditor with a ready reader frame, TeX pressed (markup DOM double); tests/workspace_control_coverage.test.mjs"}
for _state, _words in (
        ("task-contained", "Tasks, a task that contains other Work, with its completion evidence"),
        ("task-review-required", "Tasks, a completed task whose completion needs review: its blocker, its further steps and what changed"),
        ("task-waiting", "Tasks, a task that waits on another Work: the waiting-on link and the step to take"),
        ("task-held", "Tasks, a task held by an owner blocker that offers one prepared step and one read")):
    VIEW_STATES["work"][_state] = _words
    STATE_COVERAGE["work"][_state] = {"coverage": "source", "harness": _FULL + ", Tasks over the owners' captured detail, continuity and observe reads of one seeded task (tests/fixtures/shell/captured-w13b-tasks.json); tests/workspace_control_coverage.test.mjs"}
VIEW_STATES["material"]["bindings-artifact"] = "Sources with shared-material linking opened and the owner type set to Project artifact"
STATE_COVERAGE["material"]["bindings-artifact"] = {"coverage": "source", "harness": _FULL + ", Sources with the link options opened and Project artifact chosen; tests/workspace_control_coverage.test.mjs"}
for _state, _words in (
        ("object-overview", "Explore with one task opened, on Purpose & links: its identity facts and the owner's record"),
        ("object-consequences", "Explore with one task opened, on Consequences: the recorded dependents"),
        ("object-handover", "Explore with one task opened, on Handover: adding the inspected object to the handover choices"),
        ("workflow-settings", "Explore with one workflow definition opened, on Settings: where each setting comes from"),
        ("relation-outline", "Explore with the Relation outline chosen: the supplied explicit neighbourhood"),
        ("relation-map", "Explore with the Relation map chosen: the current neighbourhood")):
    VIEW_STATES["research-workbench"][_state] = _words
    STATE_COVERAGE["research-workbench"][_state] = {"coverage": "source", "harness": "mountResearchWorkbench over the owners' captured /work/discovery reads of the seeded project (tests/fixtures/shell/captured-w13b-explore.json); tests/workspace_control_coverage.test.mjs"}
VIEW_STATES["research"]["formal-setup"] = "Research, Formal proof, with formal checking not yet set up and no precise target: the setup box"
STATE_COVERAGE["research"]["formal-setup"] = {"coverage": "source", "harness": "mountEvidence over the owners' captured formal state and targets reads of the seeded project; tests/workspace_control_coverage.test.mjs"}
VIEW_STATES["research"]["literature-library"] = "Literature, Project library: the sources saved in the project, one with claim links and manuscript citations, one belonging to the argument, a further page offered"
VIEW_STATES["research"]["literature-claim"] = "Literature opened for one claim with no source linked: the scope choice, Browse all project sources and Clear claim target"
VIEW_STATES["research"]["literature-discover"] = "Literature, Discover sources, public scholarly search with a found work, one already in the library and one existing local candidate"
VIEW_STATES["research"]["literature-zotero"] = "Literature, Discover sources with My Zotero library chosen and one found item"
VIEW_STATES["research"]["literature-local"] = "Literature, Add local source: the form for a source you have yourself"
VIEW_STATES["research"]["literature-source"] = "the source box of one registered source with extracted text in pages, a PDF, a second source and full-text candidates"
VIEW_STATES["research"]["literature-source-failed"] = "the source box whose read of the source failed: the owner's refusal and Retry"
VIEW_STATES["research"]["literature-bind"] = "the box that links one source to a claim, with the claim meaning inspected and a further page of claims offered"
VIEW_STATES["research"]["literature-coverage"] = "Literature with Inspect project coverage pressed: the owner's report, a claim in it and both continuations"
for _state, _how in (
        ("literature-library", "mountLiterature over the owner's captured literature-uses read (one saved source) and owner-shaped rows for the links, citations and the argument source"),
        ("literature-claim", "mountLiterature with a claim target over the owner's captured empty claim-linked read"),
        ("literature-discover", "mountLiterature, Discover sources, over an owner-shaped discovery answer"),
        ("literature-zotero", "mountLiterature, Discover sources with Zotero, over an owner-shaped search answer"),
        ("literature-local", "mountLiterature, Add local source"),
        ("literature-source", "readSource over the owner's reference_source answer with text, PDF, candidates and a second source (owner-shaped: the seeded project holds no fetched source)"),
        ("literature-source-failed", "readSource over a refused owner read"),
        ("literature-bind", "linkSource over the owner's captured reference_source and concept catalog answers with an owner-shaped eligible claim"),
        ("literature-coverage", "mountLiterature, Inspect project coverage, over the owner's captured literature_scope answer with owner-shaped claim and page fields")):
    STATE_COVERAGE["research"][_state] = {"coverage": "source", "harness": _how + "; tests/workspace_control_coverage.test.mjs"}
VIEW_STATES["presentation"]["panels-open"] = "Figures and output with every disclosure on the page opened"
STATE_COVERAGE["presentation"]["panels-open"] = {"coverage": "source", "harness": _FULL + ", the Figures and output page with every disclosure opened; tests/workspace_control_coverage.test.mjs"}
VIEW_STATES["review"]["panels-open"] = "Review and notes with every disclosure on the page opened"
STATE_COVERAGE["review"]["panels-open"] = {"coverage": "source", "harness": _FULL + ", the Review and notes page with every disclosure opened; tests/workspace_control_coverage.test.mjs"}
VIEW_STATES["work"]["panels-open"] = "Tasks with every disclosure on the page opened"
STATE_COVERAGE["work"]["panels-open"] = {"coverage": "source", "harness": _FULL + ", the Tasks page with every disclosure opened; tests/workspace_control_coverage.test.mjs"}
VIEW_STATES["argument"]["panels-open"] = "Argument and evidence with every disclosure on the page opened"
STATE_COVERAGE["argument"]["panels-open"] = {"coverage": "source", "harness": _FULL + ", the Argument and evidence page with every disclosure opened; tests/workspace_control_coverage.test.mjs"}
VIEW_STATES["research-workbench"]["catalogue"] = "the workspace catalogue as the owner lists it for the whole workspace: object kinds, a further page and the working surface"
STATE_COVERAGE["research-workbench"]["catalogue"] = {"coverage": "source", "harness": "mountResearchWorkbench over the owner's captured workspace answer (tests/fixtures/shell/captured-w13.json); tests/workspace_control_coverage.test.mjs"}
VIEW_STATES["overview"]["seeded"] = "Home over the owners' captured answers for a seeded project: a ready next task, subtasks, further pages, an authored argument, storage observations and an unconfigured derived output"
STATE_COVERAGE["overview"]["seeded"] = {"coverage": "source", "harness": _FULL + ", Home over captured owner answers (tests/fixtures/shell/captured-w13.json); tests/workspace_control_coverage.test.mjs"}
VIEW_STATES["work"]["seeded"] = "Tasks and the open task over the owners' captured answers for a seeded project: a ready next task, subtasks, further pages, an authored argument, storage observations and an unconfigured derived output"
STATE_COVERAGE["work"]["seeded"] = {"coverage": "source", "harness": _FULL + ", Tasks and the open task over captured owner answers (tests/fixtures/shell/captured-w13.json); tests/workspace_control_coverage.test.mjs"}
VIEW_STATES["argument"]["seeded"] = "Argument and evidence over the owners' captured answers for a seeded project: a ready next task, subtasks, further pages, an authored argument, storage observations and an unconfigured derived output"
STATE_COVERAGE["argument"]["seeded"] = {"coverage": "source", "harness": _FULL + ", Argument and evidence over captured owner answers (tests/fixtures/shell/captured-w13.json); tests/workspace_control_coverage.test.mjs"}
VIEW_STATES["settings"]["seeded"] = "project Settings over the owners' captured answers for a seeded project: a ready next task, subtasks, further pages, an authored argument, storage observations and an unconfigured derived output"
STATE_COVERAGE["settings"]["seeded"] = {"coverage": "source", "harness": _FULL + ", project Settings over captured owner answers (tests/fixtures/shell/captured-w13.json); tests/workspace_control_coverage.test.mjs"}
VIEW_STATES["presentation"]["seeded"] = "Figures and output over the owners' captured answers for a seeded project: a ready next task, subtasks, further pages, an authored argument, storage observations and an unconfigured derived output"
STATE_COVERAGE["presentation"]["seeded"] = {"coverage": "source", "harness": _FULL + ", Figures and output over captured owner answers (tests/fixtures/shell/captured-w13.json); tests/workspace_control_coverage.test.mjs"}
VIEW_STATES["shell"]["running-now"] = "the project navigation with a turn the conversation owner observes running, bound to a task"
STATE_COVERAGE["shell"]["running-now"] = {"coverage": "source", "harness": _FULL + ", the shell over the owner's captured health and running-session answers (tests/fixtures/shell/captured-w13.json); tests/workspace_control_coverage.test.mjs"}
    # ---- wave 13 id sweep: states added to existing views (end) ----


def help_controls(project: str = "") -> dict[str, Any]:
    """The control registry with its states and coverage (the `controls` help concept)."""
    return {"controls": [{"id": key, **value} for key, value in CONTROL_DECLARATIONS.items()],
            "view_states": VIEW_STATES, "coverage": STATE_COVERAGE}


# THE DEFAULT AREAS PROJECTION: the once-per-session `areas` read no longer lists controls. It carries
# `controls: {known: N, read: <the controls read>}`: how many controls the help owner declares, and the one
# existing read that returns them (identity, label, page, kind, states and the guide sentence of each). The
# list left the overview on 8 November 2026 (wave 13): with every visible control declared it passed the 32 KiB
# ceiling again, and a list that grows with the app cannot ride in a read taken once per session. The guide
# takes the control ids from that controls read (workspace-guide.mjs journeySteps), not from the overview.
# The projection is part of the owner version: a changed default geometry can never reuse an older cached
# version, and default, controls and guides reads keep one shared version.
HELP_DEFAULT_PROJECTION: dict[str, Any] = {"name": "laplace.help-default-projection/4", "controls": ["known", "read"]}


def help_areas_version() -> str:
    return digest({"areas": AREA_DECLARATIONS, "journeys": JOURNEY_DECLARATIONS, "controls": CONTROL_DECLARATIONS, "diagrams": DIAGRAM_DECLARATIONS,
                   "states": VIEW_STATES, "coverage": STATE_COVERAGE, "guides": GUIDE_DECLARATIONS,
                   "projection": HELP_DEFAULT_PROJECTION})


def help_diagrams() -> list[dict[str, Any]]:
    """The declared diagrams as the topology view's input: nodes, edges, layout hints."""
    return [{"id": key, "area": key, **value} for key, value in DIAGRAM_DECLARATIONS.items()]


def help_checklist(project: str = "") -> dict[str, Any]:
    """THE ACCEPTANCE CHECKLIST (C10): generated from the declarations, one row per area: the
    controls that must render, the states a chip legend must show, the journeys that must run and
    the diagram that must open. Source-tested coverage is what the suite proves per row; actual
    coverage is the root's browser check against the same rows."""
    rows = []
    for area_id, area in AREA_DECLARATIONS.items():
        controls = [{"id": ident, "kind": row["kind"], "rendered": row["rendered"]} for ident, row in CONTROL_DECLARATIONS.items()
                    if row["view"] == area["view"] or (area_id == "overview" and row["view"] == "shell")]
        rows.append({"area": area_id, "view": area["view"], "title": area["title"], "controls": controls,
                     "states": [state["label"] for state in area["states"]], "journeys": list(area["journeys"]),
                     "diagram": area_id in DIAGRAM_DECLARATIONS, "shortcuts": len(area["shortcuts"]),
                     "view_states": {state: STATE_COVERAGE[area["view"]][state]["coverage"] for state in VIEW_STATES.get(area["view"], {})}})
    shared = [{"id": ident, "kind": row["kind"], "rendered": row["rendered"]} for ident, row in CONTROL_DECLARATIONS.items() if row["view"] == "shared"]
    return {"schema_version": "laplace.help-checklist/1", "project": project, "version": help_areas_version(),
            "rows": rows, "shared_controls": shared,
            "totals": {"areas": len(rows), "controls": len(CONTROL_DECLARATIONS), "rendered": sum(1 for row in CONTROL_DECLARATIONS.values() if row["rendered"]),
                       "journeys": len(JOURNEY_DECLARATIONS), "steps": sum(len(j["steps"]) for j in JOURNEY_DECLARATIONS.values()), "diagrams": len(DIAGRAM_DECLARATIONS),
                       "states": sum(len(s) for s in VIEW_STATES.values()),
                       "states_source_covered": sum(1 for v in STATE_COVERAGE.values() for c in v.values() if c["coverage"] == "source"),
                       "states_actual_only": sum(1 for v in STATE_COVERAGE.values() for c in v.values() if c["coverage"] == "actual")},
            "method": "Source coverage: each rendered control names its module, each journey step names a declared control and observed fact, and diagram edges name their nodes. The coverage registry names the omnibus or focused evaluator for each source state; those controlled DOM checks are separate from actual browser geometry, focus and complete task acceptance. A source declaration alone does not establish actual coverage."}


def validate_help_declarations() -> None:
    """Every journey step names a declared control and a fact the shell observes; every
    area's journeys exist; every journey's area exists. Refused at import, not at use."""
    def facts(predicate):
        if "all" in predicate:
            for item in predicate["all"]:
                yield from facts(item)
            return
        yield predicate.get("fact")
    for journey_id, journey in JOURNEY_DECLARATIONS.items():
        if journey["area"] not in AREA_DECLARATIONS:
            raise ValueError("journey %r names an undeclared area %r" % (journey_id, journey["area"]))
        for step in journey["steps"]:
            if step["control"] not in CONTROL_DECLARATIONS:
                raise ValueError("journey %r step %r names an undeclared control %r" % (journey_id, step["id"], step["control"]))
            for fact in facts(step["done"]):
                if fact not in OBSERVATION_FACTS:
                    raise ValueError("journey %r step %r names an unobserved fact %r" % (journey_id, step["id"], fact))
    for area_id, area in AREA_DECLARATIONS.items():
        for journey_id in area["journeys"]:
            if journey_id not in JOURNEY_DECLARATIONS:
                raise ValueError("area %r names an undeclared journey %r" % (area_id, journey_id))
    for ident, row in CONTROL_DECLARATIONS.items():
        states = VIEW_STATES.get(row["view"], {})
        if not row.get("states"):
            raise ValueError("control %r declares no state" % ident)
        for state in row["states"]:
            if state not in states:
                raise ValueError("control %r names an undeclared state %r of view %r" % (ident, state, row["view"]))
    for view, states in VIEW_STATES.items():
        for state in states:
            cover = STATE_COVERAGE.get(view, {}).get(state)
            if not cover or cover.get("coverage") != "source" or not cover.get("harness"):
                raise ValueError("view %r state %r has no source render coverage harness" % (view, state))
    for area_id, diagram in DIAGRAM_DECLARATIONS.items():
        if area_id not in AREA_DECLARATIONS:
            raise ValueError("diagram %r names an undeclared area" % area_id)
        ids = [node["id"] for node in diagram["nodes"]]
        if len(set(ids)) != len(ids) or not diagram.get("title") or not diagram.get("description"):
            raise ValueError("diagram %r needs unique nodes, a title and a description" % area_id)
        for edge in diagram["edges"]:
            if edge["source"] not in ids or edge["target"] not in ids:
                raise ValueError("diagram %r edge %r names an undeclared node" % (area_id, edge))
        for ident, rank in diagram["layout"]["rank"].items():
            if ident not in ids or not isinstance(rank, int) or rank < 0:
                raise ValueError("diagram %r ranks an undeclared node %r" % (area_id, ident))
        for group in diagram["layout"]["groups"]:
            if any(ident not in ids for ident in group["nodes"]):
                raise ValueError("diagram %r group %r names an undeclared node" % (area_id, group["id"]))


validate_help_declarations()


def _concept_read(project: str, concept: str) -> dict[str, Any]:
    """The one read that returns a help concept: the same object `reads` lists and the overview's controls entry carries."""
    return {"operation": "help", "payload": {"concept": concept},
            "http": {"method": "GET", "route": "/authoring/help", "query": {**({"project": project} if project else {}), "view": concept}}}


def _controls_read(project: str) -> dict[str, Any]:
    return _concept_read(project, "controls")


def help_areas(project: str = "", concept: str = "") -> dict[str, Any]:
    """The areas, journeys and controls, rendered from the declarations; one or all."""
    # the areas payload is the once-per-session read (finite content ceiling, < 32 KiB in the
    # ordinary emitted JSON, including a long project name): areas carry the size of their
    # diagram, and controls are {known, read}: the count of declared controls and the read that returns
    # them. Diagrams, guides, the checklist and the control rows are their own concepts read when opened
    rendered = {
        "areas": [{"id": key, **{k: v for k, v in value.items() if v != []}, **({"diagram": {"title": DIAGRAM_DECLARATIONS[key]["title"], "nodes": len(DIAGRAM_DECLARATIONS[key]["nodes"]),
                                                    "edges": len(DIAGRAM_DECLARATIONS[key]["edges"])}} if key in DIAGRAM_DECLARATIONS else {})}
                  for key, value in AREA_DECLARATIONS.items()],
        "journeys": [{"id": key, **value} for key, value in JOURNEY_DECLARATIONS.items()],
        # The overview carries the count of declared controls and the controls read that returns them.
        "controls": {"known": len(CONTROL_DECLARATIONS), "read": _controls_read(project)},
    }
    value: dict[str, Any] = {"schema_version": HELP_AREAS_SCHEMA, "project": project,
                             "version": help_areas_version(), "observation_facts": list(OBSERVATION_FACTS),
                             "predicate_language": ["equals", "not_equals", "truthy", "all"]}
    if concept:
        if concept not in HELP_OWNER_CONCEPTS:
            raise ValueError("help owner concept must be one of " + ", ".join(HELP_OWNER_CONCEPTS))
        value["requested_concept"] = concept
        if concept == "diagrams":
            value["diagrams"] = help_diagrams()
        elif concept == "guides":
            # Deliberate separate read: never inflate the default areas response
            # with full recipes, and never expose mutable canonical declarations.
            value["guides"] = json.loads(json.dumps([{"id": key, **guide} for key, guide in GUIDE_DECLARATIONS.items()]))
        elif concept == "checklist":
            value["checklist"] = help_checklist(project)
        elif concept == "controls":
            value.update(help_controls(project))
        else:
            value[concept] = rendered[concept]
        return value
    value.update(rendered)
    value["reads"] = {concept: _concept_read(project, concept) for concept in ("diagrams", "checklist", "guides", "controls")}
    return value


def help_index(operations, concept: str = "", *, project: str = "") -> dict[str, Any]:
    """What a `help` call with no operation is answered with, at the altitude it asked for.

    THE THIRD ALTITUDE.  `help {operation}` is one act and a concept read is its
    operation index. A bare `help` previously returned BOTH all operation rows and
    the concept index, duplicating the discovery path in one response. It now returns
    only the navigable concept index; a deliberate full traversal remains exact by
    reading every advertised concept.
    (14,420 characters for the old catalogue, measured as `help.catalogue_chars` in
    evidence/WRITING_CONSOLIDATION_2026-10-03/harness2/baseline/economy.json); a session
    that knows the CONCEPT it is working on - the object half of the grammar's verb x
    concept pair - had nothing in between.  `help {concept}` is that altitude, and a bare
    help now carries the concept list so the altitude is askable rather than guessable.
    The door keeps one return shape; this decides what goes in it.
    """
    if concept in HELP_OWNER_CONCEPTS:
        # THE HELP OWNER'S OWN CONCEPTS (G8): the workspace's areas, task journeys and the
        # control registry, from the one declaration set the help layer also renders.
        return help_areas(project, concept)
    if concept:
        rows = catalogue(operations, concept=concept)
        homes=native_read_homes(project,concept)
        actions=[home for home in native_homes(project,concept) if home["verb"]!="read"]
        if not rows and not homes and not actions:
            raise ValueError("Unknown concept; help with no payload lists the deployed "
                             "concepts under `concepts`.")
        result={"requested_concept": concept, "catalogue": rows}
        if actions:result["native_actions"]=actions
        if homes:
            result["read_navigation"]=homes[0]
            if len(homes)>1:result["read_homes"]=homes
        return result
    return {"concepts": [{**row,**({"read_navigation": homes[0]} if (homes:=native_read_homes(project,row["concept"])) else {})}
                         for row in concepts(operations)],
            "read_one_concept": {"operation": "help", "payload": {"concept": "<from concepts>"}},
            # the workspace itself, as the help owner declares it; the same read the HTTP
            # `view=areas` door and the help layer consume
            "workspace_help": {"version": help_areas_version(), "concepts": list(HELP_OWNER_CONCEPTS),
                               "read": {"operation": "help", "payload": {"concept": "areas"}},
                               "http": {"method": "GET", "route": "/authoring/help", "query": {"project": project or "<project>", "view": "areas"}}}}


def concepts(operations=None) -> list[dict[str, Any]]:
    """The concepts the deployed operations speak, each with its verbs and a count.

    The altitude between "every operation" and "one operation".  A session that knows
    the concept it is working on (the grammar's object half) asks for that concept and
    is given its rows, not the whole table: measured, the bare catalogue is 14,420
    characters and the largest concept's rows are a fraction of it.
    """
    names = sorted(operations if operations is not None else DECLARATIONS)
    rows: dict[str, dict[str, Any]] = {}
    for name in names:
        declaration = DECLARATIONS.get(name)
        if declaration is None:
            continue
        per_concept: dict[str, set[str]] = {}
        for verb, concept in declaration.acts:
            per_concept.setdefault(concept, set()).add(verb)
        for concept, verbs in per_concept.items():
            row = rows.setdefault(concept, {"concept": concept, "verbs": [], "operations": 0})
            row["operations"] += 1
            row["verbs"] = sorted(set(row["verbs"]) | verbs)
    for row in rows.values():
        row["verbs"].sort()
    for home in native_homes():
        row=rows.setdefault(home['concept'],{'concept':home['concept'],'verbs':[],'operations':0})
        row['verbs']=sorted(set(row['verbs'])|{home['verb']})
    return [rows[key] for key in sorted(rows)]


def catalogue(operations=None, concept: str = "") -> list[dict[str, Any]]:
    """The index, from the same declarations.  One row per operation: what it is, not
    a paragraph about it.  The bare catalogue was 13,194 characters of summaries
    (context-economy.md finding 4); a row here is the verb, the concept, the homes it
    guards and one short clause."""
    names = sorted(operations if operations is not None else DECLARATIONS)
    rows: list[dict[str, Any]] = []
    for name in names:
        declaration = DECLARATIONS.get(name)
        if declaration is None:
            if not concept:
                rows.append({"operation": name})
            continue
        pairs = [(verb, selected) for verb, selected in declaration.acts
                 if not concept or selected == concept]
        if concept and not pairs:
            continue
        row = {"operation": name, "verb": declaration.verb,
               "concept": declaration.concept, "does": declaration.does,
               "guards": list(declaration.homes)}
        if concept:
            from laplace.native import verbs as writing_verbs
            selected_routes = [route for route in writing_verbs.routes_for(name)
                               if route.concept == concept]
            row.update({"concept": concept, "verb": pairs[0][0],
                        "acts": [{"verb": route.verb,
                                  "legacy": writing_verbs.old_spelling(route),
                                  "native": route.door == "both"}
                                 for route in selected_routes]})
        rows.append(row)
    return rows





def http_catalogue() -> list[dict[str, Any]]:
    return [{"route": declaration.route, "methods": list(declaration.methods),
             "operation": name, "verb": declaration.verb,
             "concept": declaration.concept, "does": declaration.does,
             "source_operation": declaration.source_operation or None,
             "header": declaration.header, "enforced_at": cited(declaration.header_door),
             "outputs": list(declaration.outputs),
             "consumers": declaration.resolved_consumers(),
             "rules": [rule.rendered() for rule in declaration.http_rules()]}
            for name, declaration in sorted(HTTP_DECLARATIONS.items())]


def resolved_derived(declaration: Declaration, *, contract=False) -> dict[str, Any]:
    """Call every producer this declaration names and return what they produce.

    A declaration states WHERE a derived fact lives and never what it is, so help cannot
    disagree with the row source even for one call --- the rule ``acts`` already follows for
    the route table.  An unimportable producer raises here, with the spec in the message,
    rather than serving a door with a silently missing field."""
    import importlib
    produced: dict[str, Any] = {}
    for key, spec in ((declaration.contract_derived if contract else declaration.derived) or {}).items():
        module, _, function = str(spec).partition(":")
        if not module or not function:
            raise ValueError("a derived help field names 'module:function'; %r names %r"
                             % (key, spec))
        produced[key] = getattr(importlib.import_module(module), function)()
    return produced


def _http_detail(name: str, declaration: Declaration) -> dict[str, Any]:
    query_policy = ({"lossless_query": True} if declaration.extras.get("lossless_query") is True else {})
    return {**resolved_derived(declaration), **query_policy,
            "route": declaration.route, "methods": list(declaration.methods),
            "operation": name, "verb": declaration.verb,
            "concept": declaration.concept, "acts": [list(pair) for pair in declaration.pairs],
            "source_operation": declaration.source_operation or None,
            "does": declaration.does, "input": declaration.payload,
            "header": {"required": declaration.header,
                       "enforced_at": cited(declaration.header_door)},
            "outputs": list(declaration.outputs), "errors": list(declaration.errors),
            "recoverable": list(declaration.recoverable),
            "consumers": declaration.resolved_consumers(),
            "response_sources": declaration.resolved_responses(),
            "rules": [rule.rendered() for rule in declaration.http_rules()],
            "line_numbers": COORDINATE_LAW,
            "version": digest([declaration.route, declaration.methods, name,
                               declaration.payload, declaration.outputs,
                               declaration.resolved_consumers(),
                               declaration.source_operation,
                               [rule.rendered() for rule in declaration.http_rules()],
                               declaration.resolved_responses()] + ([query_policy] if query_policy else []))}


def http_help(route: str, method: str = "", operation: str = "") -> dict[str, Any]:
    method = str(method or "").upper()
    matches = [(name, declaration) for name, declaration in HTTP_DECLARATIONS.items()
               if declaration.route == route
               and (not method or method in declaration.methods)
               and (not operation or name == operation)]
    if not matches:
        raise ValueError("no declared HTTP door at %r%s" %
                         (route, " with method " + method if method else ""))
    if len(matches) == 1:
        return _http_detail(*matches[0])
    choices = [{"operation": name, "methods": list(declaration.methods),
                "verb": declaration.verb, "concept": declaration.concept}
               for name, declaration in matches]
    return {"route": route, "method": method or None, "ambiguous": True,
            "alternatives": choices,
            "read_one": {"operation": "help", "payload": {
                "route": route, "method": method or "<GET-or-POST>",
                "http_operation": "<from alternatives>"}},
            "line_numbers": COORDINATE_LAW,
            "version": digest(choices)}


def _site_projection(root: Path, repository: str, site: str, *,
                     files: dict | None = None) -> dict[str, Any]:
    rel, _, raw_line = site.rpartition(":")
    line = int(raw_line)
    source = (Path(root) / rel).resolve()
    reference = _serving_source(rel)
    key = (source, reference)
    loaded = files.get(key) if files is not None else None
    if loaded is None:
        if not source.is_file() or not source.is_relative_to(Path(root).resolve()):
            raise ValueError("interface source is unavailable inside the selected repository: " + rel)
        data = source.read_bytes()
        if not reference.is_file() or data != reference.read_bytes():
            raise ValueError("interface source identity differs from the code serving this declaration: " + rel)
        lines = data.decode("utf-8", errors="replace").splitlines(keepends=True)
        offsets = [0]
        for value in lines:
            offsets.append(offsets[-1] + len(value))
        loaded = (len(data), hashlib.sha256(data).hexdigest(), lines, offsets)
        if files is not None:
            files[key] = loaded
    size, sha256, lines, offsets = loaded
    if not 0 < line <= len(lines):
        raise ValueError("interface source range is outside the selected source: " + site)
    offset = offsets[line - 1]
    limit = len(lines[line - 1]) or 1
    return {"site": site, "path": rel, "line_start": line, "line_end": line,
            "bytes": size, "sha256": sha256,
            "read": {"operation": "repository", "payload": {
                "action": "read", "repository": repository, "path": rel,
                "offset": offset, "limit": limit}}}


def interface_projection(root: Path, repository: str, *, offset: int = 0,
                         limit: int = 20, route: str = "", method: str = "") -> dict[str, Any]:
    """A bounded derived join over declarations and their exact source consumers.

    This is diagnostic navigation, not a route registry or a source-work lifecycle.  Its
    revision includes every source byte identity it cites; a checkout that differs from the
    code serving the declarations is refused rather than projected approximately.
    """
    method = str(method or "").upper()
    if method and method not in {"GET", "POST"}:
        raise ValueError("interface method must be GET or POST")
    rows = []
    for name, declaration in sorted(HTTP_DECLARATIONS.items()):
        if route and declaration.route != route:
            continue
        if method and method not in declaration.methods:
            continue
        peers = sorted(other for other, candidate in HTTP_DECLARATIONS.items()
                       if candidate.route == declaration.route
                       and set(candidate.methods) & set(declaration.methods))
        request = declaration.payload
        contract = http_help(declaration.route, declaration.methods[0], name)
        sites = {"handler": declaration.handler, **declaration.resolved_consumers(),
                 **declaration.resolved_responses()}
        rows.append({"operation": name, "route": declaration.route,
                     "methods": list(declaration.methods),
                     "verb": declaration.verb, "concept": declaration.concept,
                     "acts": [list(pair) for pair in declaration.pairs],
                     "source_operation": declaration.source_operation or None,
                     "owner": declaration.handler,
                     "request": {"required": list(request.get("required") or []),
                                 "properties": sorted((request.get("properties") or {}).keys()),
                                 "version": contract["version"]},
                     "response": {"outputs": list(declaration.outputs),
                                  "errors": list(declaration.errors),
                                  "recoverable": list(declaration.recoverable),
                                  "guards": [rule.rendered() for rule in declaration.http_rules()
                                             if rule.kind == "identity"]},
                     "consumers": declaration.resolved_consumers(),
                     "response_sources": declaration.resolved_responses(),
                     "route_ambiguity": peers if len(peers) > 1 else [],
                     "contract_read": {"operation": "help", "payload": {
                         "route": declaration.route,
                         "method": declaration.methods[0],
                         "http_operation": name}},
                     "sites": sites})
    source_sites = sorted({site for row in rows for site in row["sites"].values()})
    # One exact source snapshot per file in this request. Every page still checks the
    # complete cited source set; no bytes or identities survive into a later request.
    files: dict = {}
    all_sources = [_site_projection(Path(root), repository, site, files=files)
                   for site in source_sites]
    source_by_site = {source["site"]: source for source in all_sources}
    public_rows = [{key: value for key, value in row.items() if key != "sites"} for row in rows]
    from laplace.native import verbs as writing_verbs
    revision = digest({"table": writing_verbs.HTTP_GENERATED_FROM,
                       "rows": public_rows,
                       "sources": [(row["site"], row["sha256"]) for row in all_sources]})
    page_rows = rows[offset:offset + limit]
    page = public_rows[offset:offset + limit]
    page_sites = sorted({site for row in page_rows for site in row["sites"].values()})
    sources = [source_by_site[site] for site in page_sites]
    next_offset = offset + len(page) if offset + len(page) < len(public_rows) else None
    continuation = None if next_offset is None else {"operation": "repository", "payload": {
        "action": "interface", "repository": repository, "offset": next_offset,
        "limit": limit, **({"route": route} if route else {}),
        **({"method": method} if method else {})}}
    return {"schema_version": "laplace.http-interface-projection/1",
            "authority": "Derived diagnostic projection; declarations and source owners remain authoritative.",
            "repository": repository, "revision": revision,
            "offset": offset, "next_offset": next_offset, "truncated": next_offset is not None,
            "total": len(public_rows), "items": page, "sources": sources,
            "continuation": continuation}


def _serving_source(rel: str) -> Path:
    """Resolve a public ``src/laplace`` coordinate inside the executing package."""
    logical = Path(rel)
    try:
        package_rel = logical.relative_to("src/laplace")
    except ValueError as exc:
        raise ValueError("declaration source is outside the executing laplace package: " + rel) from exc
    package = _PACKAGE.resolve()
    source = (package / package_rel).resolve()
    if not source.is_relative_to(package):
        raise ValueError("declaration source escapes the executing laplace package: " + rel)
    return source


# Native declarations bootstrap HTTP after their table is complete. This also
# supports native-first imports, where this module sees native partially loaded.
from laplace.native import declared as _declared       # noqa: E402,F401


# ---------------------------------------------------------------------------
# WHICH DOORS TAKE `by`.  The request carries a writer because a note could not record
# one (friction report: 140 notes from six writers read back under a single name), and the
# owners today do FOUR different things with it.  A lane may not discover that one door at
# a time, so the grammar DECLARES it, with the site that decides each case.  The four
# statuses, each measured on this tree (`by_census.py` beside this module re-measures them
# and `test_grammar.py` fails if any citation stops saying what is claimed here):
#
#   overwritten  the module door REPLACES the caller's value with the constant
#                `"eigen:session"` before the owner sees it (writing_tools.py:309).  The
#                contract declares `by` and the owner records it, so a caller gets no
#                refusal and no attribution either: every writer is recorded as one name.
#                This is the 140-notes defect itself, in the code that causes it.
#   refused      a door that validates unknown keys and whose key set does not list `by`.
#                The caller is refused outright: `structure_change payload contains unknown
#                keys: by` (measured through project_structure.py:710).
#   dropped      no key check and no overwrite: the key is accepted, nothing reads it, and
#                the writer is lost silently.  The default, and the largest class.
#   declared     the contract declares `by`, the owner reads it, the door leaves it alone.
#                Historical audit: none of its original 73 operations was in this class.
#
# Current contract: outer Request.by is bounded requested attribution on existing
# receipts, never universally injected into owner data. Literal owner by travels
# through owner_by and must pass the selected actual owner input schema. This
# dated census is diagnostic only; owner-bound actors and permissions stay intact.
# ---------------------------------------------------------------------------
# Retained dated census, not current admission or current source coordinates.
# by_at derives current schema admission and names its current dispatch below.
BY_AT_DOORS: dict[str, tuple[str, str]] = {
    "project_metadata_change": ("overwritten", "writing_tools._execute fixes eigen:session; writing_projects.change_metadata records that actor"),
    # --- overwritten: writing_tools.py:309 sets payload["by"] = "eigen:session" ---
    "concept_change": ("overwritten", "writing_tools.py:309 overwrites it; the contract "
                       "declares it for all 13 operations (concepts_surface.py:1021 "
                       "validates against those properties)"),
    "logical_plan_change": ("overwritten", "writing_tools.py:309 overwrites it; "
                            "writing_contracts.py:604 adds `by` to every operation variant"),
    "writing_style_change": ("overwritten", "writing_tools.py:309 overwrites it; "
                             "writing_style.save reads payload['by'] at "
                             "writing_style.py:465"),
    "writing_style_profile_change": ("overwritten", "writing_tools.py:309 overwrites it; "
                                     "writing_style.py:371-372 lists `by` as optional and "
                                     ":428 reads it, but the door already replaced it"),
    # --- refused: a door that validates unknown keys, with no `by` in its key set ---
    "storage": ("refused", "writing_tools.py:215 validates exact payload keys"),
    "storage_prune": ("refused", "writing_tools.py:215 and writing_storage.py:170 validate exact payload keys"),
    "app_settings": ("declared", "writing_tools.py:626 accepts the read audit label and drops it before global owner dispatch"),
    "material_references": ("declared", "writing_tools.py:626 drops the optional read audit label by before owner dispatch"),
    "material_reference_change": ("overwritten", "writing_tools.py:630 overwrites by with eigen:session before registry membership mutation"),
    "materials": ("refused", "project_work_surface.py:19 accepts only offset and limit"),
    "source": ("refused", "writing_tools.py:194, the `allowed` set"),
    "help": ("refused", "writing_tools.py:211, only operation and project"),
    "writing_stage": ("refused", "writing_stages.py:58, {stage, view, known_revision}"),
    "writing_style": ("refused", "writing_style.py:225, {view, profile}"),
    "writing_style_calibration": ("refused",
                                  "writing_style.py:288, {sources, purpose, genre}"),
    "repository": ("refused", "writing_sources.py:203 against the action's schema: "
                   "`repository list has irrelevant or unknown fields: by`"),
    "structure_change": ("refused", "project_structure.py:746 validates the whole payload "
                         "with additionalProperties False and :710 raises "
                         "`structure_change payload contains unknown keys: by`"),
    "literature_scope": ("refused", "writing_tools.py:215 against CONTRACTS[op] properties"),
    "literature_lookup": ("refused", "writing_tools.py:215"),
    "literature_discover": ("refused", "writing_tools.py:215"),
    "literature_import": ("refused", "writing_tools.py:215"),
    "literature_bind": ("refused", "writing_tools.py:215"),
    "literature_uses": ("refused", "writing_tools.py:215"),
    "reference_source": ("refused", "writing_tools.py:215"),
    "reference_text": ("refused", "writing_tools.py:215"),
    "reference_fetch": ("refused", "writing_tools.py:215"),
    "proposal_supersede": ("refused", "writing_tools.py:215"),
    "apply_revision": ("refused", "authoring_surface.py:2166 — ONLY in the `proposal` "
                       "wrapper form: {proposal, project} and nothing else. A flat "
                       "apply_revision payload drops it instead"),
}
BY_DEFAULT_STATUS = (
    "dropped",
    "no door on this operation's path validates unknown keys and nothing reads `by`, so "
    "This diagnostic describes literal owner data, never outer Request.by. "
    "Current admission permits owner by only where the selected declaration actually names it; "
    "it is not an admission allowlist.")
BY_STATUSES = ("declared", "overwritten", "refused", "dropped")


def by_at(operation: str) -> tuple[str, str]:
    """Current literal-owner admission projected from its effective declaration.

    The retained census above is dated diagnostic evidence, never permission.
    Outer requested attribution is recorded separately from owner data/actors.
    """
    if operation not in DECLARATIONS:
        return "refused", "No current owner declaration admits literal by"
    def declared(row):
        return "by" in row.get("properties", {}) or any(declared(item)
            for axis in ("anyOf","oneOf","allOf") for item in row.get(axis,()))
    if not declared(owner_input_schema(operation)):
        return "refused", "laplace.native.declarations.validate_owner_payload rejects undeclared literal by; outer requested attribution is separate"
    status, reason = BY_AT_DOORS.get(operation, ("declared", "Current selected owner input explicitly declares literal by"))
    if status == "overwritten":
        return "overwritten", "Current gateway fixes the owner actor; inspect " + str(DECLARATIONS[operation].handler) + "; outer requested attribution is separate"
    return "declared", "Current owner input explicitly declares literal by; the dated census is not admission"
