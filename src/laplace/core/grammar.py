"""The uniform grammar of the writing system: homes, tokens, requests, receipts.

One sentence holds the whole module: **a door never names a field without naming the
home its value comes from.**  A home is a place a value lives; a token names a home
and the exact state it was in; a request presents tokens; a refusal hands back the
tokens that would have been accepted.

What this module deliberately does NOT do
-----------------------------------------
It does not mint a new digest FOR THE 37 HOMES AN OWNER ALREADY MINTS.  For recipe O
(25 homes) the token's ``digest`` is the byte-identical value the owner publishes today,
read from the owner at a named path; for recipe B (12 homes) it is a sha256 of the same
file bytes the owner digests with its own function (``manuscript_structure.py:46-51``
``_digest_bytes``/``_digest``).  The ONE home whose owner numbers it with a monotone
integer instead of a digest, ``authoring-state``, is a recipe-B home over the one file
that integer counts (``pipeline/authoring.py:24`` names it, ``:63-86`` resolves it,
``:434`` increments the counter inside it and ``:244`` rewrites it), so the token grammar
has ONE digest form and no counter form.  For the
23 recipe-J homes NO OWNER PUBLISHES A VALUE AT ALL and this layer computes one; that is
stated here, in GRAMMAR.md §1 and in the generated obtain table, because a parity claim
cited for a J home would be false.  The conventional default refused is to define a fresh
revision scheme and migrate the owners onto it: that would break differential replay
parity on the first commit, and parity against the recorded corpus is this campaign's
acceptance condition.  The grammar's contribution is that the home is *named* and the
mint rule is *written down once*, not that the bytes change.

It does not add a mapping file.  ``HOME_KINDS`` below is the mapping, and it is the
same table the request shape, the refusal's resolver and the shim all read.  A second
file that had to agree with this one is the shape of the defect the grammar exists to
end (20 guard names over 9 values, friction report §1).

Measurements this module answers (evidence/WRITING_FRICTION_2026-10-01/wave1/):
  * synthesis.md §1.1   29 of 74 refusals, 94 of 210 recorded failures, are an identity
                        guard whose home was not named.  ``require`` answers it.
  * synthesis.md §1.1   ``bind_results`` names only the guard it checked first.
                        ``require`` checks every expected token and reports every one.
  * synthesis.md §1.10  ``retry_instruction`` reaches two of the caller paths.  The
                        resolver is built by ``require``, which is on every path.
  * synthesis.md §1.4   ``ok`` with ``applied: null``.  ``Receipt.outcome`` is a status,
                        not a field name.
  * synthesis.md §1.7   the banked row carries the operation name, not the verb or the
                        altitude.  ``Receipt.banked_row`` carries verb, concept, altitude.
  * verb-altitude-audit.md §1.3  one ``source`` read returns six identity fields holding
                        three values.  Three homes, named here, one mint rule each.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

__all__ = [
    "VERBS", "ALTITUDES", "HOME_KINDS", "Home", "Token", "mint", "parse", "matches",
    "identity", "Request", "Affected", "Receipt", "Refusal", "Refused", "require",
    "concept_object", "concept_altitude", "Shim", "SHIMS", "digest_bytes",
    "GUARD_NAMES", "PUBLISHED_NAMES",
    "digest_canonical_json",
    "PAYLOAD_CARRIERS", "carrier_for", "owner_key_for", "to_payload", "to_owner_payload",
    "WRITER_FIELD",
]

# ---------------------------------------------------------------------------
# 1. The verb alphabet.  Nine verbs, closed.
#
# A verb is individuated by its GATE: what must be proven before the act, and which
# homes the receipt must account for afterwards.  Two acts that differ only in their
# payload are the same verb at different concepts.  The author's rule --- "the verbs
# act as the gate ... completely uniform grammar, specialised to the concept" --- is
# enforced structurally here: a concept may add payload keys and may not add a verb.
#
#   read    gate: nothing.          owes: the current token of every home it read.
#   create  gate: the container.    owes: a home that did not exist (before = None).
#   change  gate: the target.       owes: the same home id, a new token.
#   move    gate: both containers.  owes: two container tokens; the moved home's own
#                                   token UNCHANGED.  (That is why it is not `change`.)
#   delete  gate: the target.       owes: after = None for the target.
#   bind    gate: BOTH endpoints.   owes: a relation home.  Two-home gate, so not `create`.
#   place   gate: container + placed home + the container's ORDER.  owes: the container.
#                                   The only verb whose gate includes an order.
#   run     gate: the inputs.       owes: outcome `banked` plus a run token to poll.
#                                   The only verb whose receipt is not final at return.
#   record  gate: a STATE, not only an identity (the run must be COMPLETE and current,
#                                   research_surface.py:1224-1229).  The only verb with
#                                   a state precondition.
# ---------------------------------------------------------------------------
VERBS: tuple[str, ...] = ("read", "create", "change", "move", "delete",
                          "bind", "place", "run", "record")

# The audit's lexicon, now declared.  No operation declares an altitude today
# (synthesis.md §6), which is why the altitude column had to be assigned by hand.
ALTITUDES: tuple[str, ...] = ("project", "book", "chapter", "section", "paragraph",
                              "plan", "claim", "relation", "evidence", "run")

_CONCEPT = re.compile(r"^(?P<object>[a-z][a-z0-9-]*)@(?P<altitude>[a-z]+)$")
_KIND = re.compile(r"^[a-z][a-z0-9-]*$")
_HEX = re.compile(r"^(?:sha256:)?(?P<hex>[0-9a-fA-F]{64})$")
# ONE owner numbers its home with a monotone integer instead of a digest:
# pipeline/authoring.py:93-94 keeps `revision` and `argument_revision` as ints, compares
# `revision` at :398-399 and increments it at :434 (`argument_revision` at :94/:432 is
# published and compared by nothing).  The token does NOT carry that integer.  The
# `authoring-state` home's one minting rule digests THE BYTES THE COUNTER COUNTS: the
# project's `authoring.json` -- `_STATE_NAME` at :24, the path its owner resolves at
# :63-86, the file `_write` rewrites at :244 and :435/:1177/:1256 -- which is why that
# home is recipe B and the digest has exactly ONE form.  A second form would mean two
# parse rules, two mint rules and two comparison semantics for one `expected` field, and
# a lane would have to know which home it held before it could compare.  `framing` and
# `argument` are two recipe-J content homes guarded THROUGH that one home.


def concept_object(concept: str) -> str:
    m = _CONCEPT.match(concept)
    if m is None:
        raise ValueError("concept must be <object>@<altitude>, got %r" % (concept,))
    return m["object"]


def concept_altitude(concept: str) -> str:
    m = _CONCEPT.match(concept)
    if m is None:
        raise ValueError("concept must be <object>@<altitude>, got %r" % (concept,))
    if m["altitude"] not in ALTITUDES:
        raise ValueError("unknown altitude %r; the alphabet is %r"
                         % (m["altitude"], ALTITUDES))
    return m["altitude"]


# ---------------------------------------------------------------------------
# 2. The two byte recipes.  Everything a token digests is one of these.
# ---------------------------------------------------------------------------
def digest_bytes(data: bytes) -> str:
    """Recipe B --- the exact bytes of a file, nothing added, nothing sorted."""
    return hashlib.sha256(data).hexdigest()


def digest_canonical_json(value: Any) -> str:
    """Recipe J --- one canonicalisation for every structured home.

    ``sort_keys``, ``ensure_ascii=False``, the tightest separators, ``default=str``.
    This is project_structure.py:14-17's spelling, chosen because it is the one the
    largest number of owners already use.  Owners that spell it differently today
    (concepts_surface.py:20-22 omits separators and ensure_ascii) keep their own
    bytes until replay parity retires the difference; see ``HomeKind.source``.
    """
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False, default=str,
        separators=(",", ":")).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 3. Homes and tokens.   rev:<home-kind>:<home-id>:<digest>
#
# home-kind  contains no colon (enforced).
# home-id    is the project, then the identity within it, joined by `::`:
#              `<project>`                      a whole-project home (plan, concept-network)
#              `<project>::<id>`                a home inside one project (concept-node, source-file)
#              `::<id>`                         a home that is NOT per project (style-profile, which
#                                               writing_style.py:34 reads from profiles/voice/, and
#                                               which the census measured identical across projects)
#            A home-id MAY contain colons, because real node ids do
#            (`def:task-relative-representation`), so a token is parsed from both ends
#            and never by splitting on every colon.  `::` is the only segment separator.
# digest     is lowercase hex sha256 with no prefix.  A caller may paste the owner's
#            `sha256:`-prefixed spelling; `mint` and `parse` normalise it, exactly as
#            revision_identity.py:9-22 does, so no caller is refused over a spelling.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Home:
    """A place a value lives: a kind from HOME_KINDS and an id within that kind."""
    kind: str
    id: str = ""

    def __post_init__(self) -> None:
        if not _KIND.match(self.kind):
            raise ValueError("home kind must be lower-kebab with no colon: %r" % (self.kind,))
        if self.kind not in HOME_KINDS:
            raise ValueError("unknown home kind %r" % (self.kind,))

    @property
    def key(self) -> tuple[str, str]:
        return (self.kind, self.id)

    @property
    def segments(self) -> tuple[str, str]:
        """(project, identity-within-project).  See the id rule above."""
        project, _, rest = self.id.partition("::")
        return (project, rest)

    @property
    def within(self) -> str:
        """The identity inside the project: a node id, a path, a section id, a run id."""
        project, rest = self.segments
        return rest if "::" in self.id else ""

    def __str__(self) -> str:
        return "%s:%s" % (self.kind, self.id)


@dataclass(frozen=True)
class Token:
    kind: str
    home_id: str
    digest: str

    @property
    def home(self) -> Home:
        return Home(self.kind, self.home_id)

    @property
    def key(self) -> tuple[str, str]:
        return (self.kind, self.home_id)

    def __str__(self) -> str:
        return "rev:%s:%s:%s" % (self.kind, self.home_id, self.digest)


def _normal_digest(value: Any) -> str:
    """ONE form: lowercase hex sha256.  The owner's `sha256:`-prefixed and upper-case
    spellings normalise; an integer counter does not, because a counter is not an
    identity of the bytes and the home whose owner keeps one (`authoring-state`) mints
    over those bytes instead."""
    text = str(value if value is not None else "")
    if isinstance(value, bool):
        raise ValueError("a token digest is not a boolean")
    if isinstance(value, int):
        raise ValueError(
            "a token digest has one form, sha256, and %r is a counter. The one home an "
            "owner numbers with a counter is `authoring-state`; its minting rule digests "
            "the bytes that counter counts (its project's authoring.json), so mint it "
            "with identity(Home('authoring-state', project)) and keep the counter in the "
            "refusal's sentence, where pipeline/authoring.py:398-399 serves it." % (value,))
    m = _HEX.match(text)
    if m is None:
        raise ValueError("a token digest is a sha256 hex string, optionally `sha256:`-"
                         "prefixed; there is no second form; got %r" % (value,))
    return m["hex"].lower()


# THE ONE RESERVED SEGMENT.  A digest may arrive in the owner's own spelling,
# `sha256:<64 hex>` (project_structure.py:14-17 publishes exactly that), so in
# `rev:plan:proj:sha256:<hex>` the segment before the hex belongs to the DIGEST and never
# to the home id.  Splitting the digest off from the right without that rule ate the
# prefix into the id: `parse` returned home id `proj:sha256` - a home that does not exist -
# while the digest normalised correctly and NOTHING refused, so a refusal built from such a
# token named the wrong home, which is the misdirected resolver `needed` exists to prevent.
# The rule is made lossless in both directions by refusing to MINT a home id whose last
# segment is this word: no token can exist whose id ends in it, so the parse is unambiguous.
# The spelling is EXACTLY the owner's, lower case: revision_identity.py:6 normalises
# `(?:sha256:)?([0-9a-fA-F]{64})` and nothing else, so the grammar tolerates neither more
# nor less than the door it has to agree with.
_DIGEST_PREFIX = "sha256"


def mint(kind: str, home_id: str, digest: Any) -> Token:
    """Make a token.  The digest is the owner's value, normalised, never recomputed."""
    if not _KIND.match(kind):
        raise ValueError("home kind must be lower-kebab with no colon: %r" % (kind,))
    if kind not in HOME_KINDS:
        raise ValueError("unknown home kind %r; the alphabet is in HOME_KINDS" % (kind,))
    text_id = str(home_id or "")
    if text_id.rpartition(":")[2] == _DIGEST_PREFIX:
        raise ValueError(
            "a home id may not end with the segment %r: that segment immediately before "
            "the digest is the digest's own prefix (the owner's spelling, "
            "project_structure.py:14-17), and a token whose id ended in it could not be "
            "parsed back to one home. Got %r." % (_DIGEST_PREFIX, text_id))
    return Token(kind, text_id, _normal_digest(digest))


def parse(raw: str | Token) -> Token:
    if isinstance(raw, Token):
        return raw
    text = str(raw or "")
    if not text.startswith("rev:"):
        raise ValueError("a token starts with `rev:`; got %r" % (text,))
    try:
        _, kind, rest = text.split(":", 2)
    except ValueError as exc:
        raise ValueError("a token is rev:<kind>:<id>:<digest>; got %r" % (text,)) from exc
    if ":" not in rest:
        raise ValueError("a token is rev:<kind>:<id>:<digest>; got %r" % (text,))
    home_id, digest = rest.rsplit(":", 1)
    # The reserved segment, moved back onto the digest where it belongs.  `_normal_digest`
    # then strips it, so `parse` of the owner's spelling and `parse` of ours agree on BOTH
    # the home id and the digest, and `str(parse(t))` is the one normal form.
    head, sep, last = home_id.rpartition(":")
    if last == _DIGEST_PREFIX and _HEX.match(digest):
        home_id, digest = (head if sep else ""), "%s:%s" % (last, digest)
    return mint(kind, home_id, digest)


def matches(expected: str | Token, observed: str | Token) -> bool:
    """Same home, same state.  Spelling-tolerant on the digest, exact on the home."""
    try:
        want, have = parse(expected), parse(observed)
    except ValueError:
        return False
    return want.key == have.key and want.digest == have.digest


# ---------------------------------------------------------------------------
# 4. The home alphabet.  ONE minting rule per home kind.
#
# `bytes` states what is digested, so the token is reproducible by anyone from the
# repository alone.  `source` is the live code that produces that value today, and
# `recipe` says whether this layer computes it (B/J) or reads it from the owner (O).
# `guards_today` lists every field name the friction report counted for this home ---
# which is how the shim knows what to rewrite, and the only place an old name survives.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class HomeKind:
    kind: str
    id_is: str
    bytes: str
    recipe: str          # "B" exact file bytes | "J" canonical JSON | "O" owner value
    source: str          # file:line in src/laplace that produces the value today
    guards_today: tuple[str, ...] = ()   # names a DOOR asks for and compares
    read: str = ""       # the one read a caller uses to obtain this token
    published_as: tuple[str, ...] = ()   # names a READ returns this same value under
    closes: str = ""     # when identity() CANNOT obtain this home: the read or the owner
                         # publication that would close it.  Required unless the home is
                         # wired in OWNER_READS or has recipe B (see MINT_STATUS).
    guard_doors: tuple[str, ...] = ()    # "<guard>=<file:line>" for a guard the audit's
                         # verb matrix does not attribute to this home: the door that
                         # actually COMPARES it.  Without one, a declared guard is prose.
    # There is no `same_value_as`: two kinds over one set of bytes IS two sources of
    # truth, and round 2 of this packet deleted the one pair that had it (two plan kinds
    # over one owner read became the single `plan` home).  test_grammar.py asserts no two kinds declare the same
    # owner read, so the alias cannot come back under a blessing.


def _k(*args: Any, **kw: Any) -> HomeKind:
    h = HomeKind(*args, **kw)
    return h


HOME_KINDS: dict[str, HomeKind] = {h.kind: h for h in (
    _k("source-file", "repository-relative path of one .tex file",
       "the file's exact bytes", "B", "manuscript_structure.py:46-51; manuscript_blocks.py:50",
       ("expected_source_digest", "before"),
       "source {files:[path]} -> sources[0].sha256",
       ("sha256", "raw_file_sha256", "full_text_sha256", "expected_source_digest"),
       guard_doors=("before=manuscript_blocks.py:166 (`if path.read_text(encoding=\"utf-8\") "
                    "== edit[\"before\"]`) and :242 compare the WHOLE file text against "
                    "`before` during undo and rollback; the SPAN-level `before` is the "
                    "prose home, compared at review_surface.py:1860",)),
    _k("selected-edition", "project",
       "the selected manuscript root file's exact bytes", "O", "manuscript_source.py:263",
       ("expected_source_revision", "expected_root_digest"),
       "source {} -> document.revision",
       ("revision", "source_revision", "document.revision")),
    _k("source-traversal", "project",
       "sha256 over the traversal IN SOURCE ORDER of each row's `file` + NUL + its full "
       "`text` + NUL --- the owner's own _revision, not a sorted snapshot",
       "O", "pipeline/authoring.py:439-447 (_revision), computed at :722 and published at "
       ":796 as source.source_revision; help visual_place warns in prose that it MUST NOT "
       "be sent as expected_source_revision (§1.3). NOT manuscript_structure.py:349-353, "
       "which digests a sorted [{file,sha256}] snapshot as the SOURCE_ONLY fallback of the "
       "fallback: a different value under a name one letter apart, and my own first "
       "reading of this home",
       (), "source {} -> source_revision"),
    _k("plan-file", "project",
       "the canonical projection_plan.json file's exact bytes", "O",
       "project_structure.py:176, :303 (authority.plan_revision)",
       ("expected_plan_revision",), "structure {} -> authority.plan_revision"),
    _k("plan-section", "project + section id",
       "canonical JSON of that section's row in the plan projection", "J",
       "NOT MINTED TODAY -- the gap `place` closes (synthesis.md §1.8: reconcile said "
       "CURRENT while plan order and \\input order disagreed in 4 of 7 positions)",
       (), "structure {} -> sections[id]"),
    _k("plan", "project",
       "canonical JSON of {authority, sections, gaps} of the plan projection --- the "
       "value `structure {} -> revision` returns, NOT the whole projection_plan.json "
       "document (those bytes are the `plan-file` home). Round 2 of this packet merged "
       "its duplicate kind into this one: one set of bytes had two kinds, `identity()` "
       "minted both, and `require` answered a present, unchanged home with "
       "`unknown-home` and an empty `needed`", "O",
       "project_structure.py:308 via _digest :14-17",
       ("expected_revision", "expected_plan_revision"), "structure {} -> revision"),
    _k("concept-network", "project",
       "canonical JSON of {rows, nodes, relations} of the whole conceptric network",
       "O", "concepts_surface.py:20-22 _revision; minted at :123 and published at :136 by "
       "state(), minted and published at :752 by logical_plan() --- one value, two reads",
       ("base_revision", "expected_concept_revision", "concept_revision"),
       "concept {node} -> revision  (identical to logical_plan -> revision; measured)",
       ("revision",)),
    _k("concept-node", "project + node id",
       "canonical JSON of {node, content, relations, sources, prerequisites}", "O",
       "concepts_surface.py:78-82 _content_revision",
       ("mutation_revision",), "concept {node} -> content_revision",
       ("content_revision", "mutation_revision")),
    _k("concept-catalogue", "project + query",
       "canonical JSON of the WHOLE sorted row set, page-independent", "O",
       "concepts_surface.py:167", (),
       "logical_plan {view:catalog} -> revision  (NOT a change guard; §1.3's trap)"),
    _k("claim-meaning", "project + node id",
       "canonical JSON of {kind, meaning, mathematics, source_refs} of one claim",
       "O", "literature_support.py:64-76 meaning_revision",
       ("claim_revision",), "concept {node} -> source_support.meaning_revision"),
    _k("result", "project + record id",
       "canonical JSON of the research record with its own `revision` key removed",
       "O", "research_surface.py:571-573 _record_revision",
       ("expected_revision", "result_revision"), "research {view:result} -> revision"),
    _k("result-binding", "project + claim id + result id",
       "canonical JSON of the binding row", "J", "research_surface.result_bindings",
       (), "structure {} -> evidence",
       closes="research_surface.result_bindings(manuscript, result_ids, ...) takes "
              "a manuscript PATH and a list of result ids, not a project, so it "
              "does not fit the one project/root call shape; either give it a "
              "project-shaped read or have state_payload publish the binding rows "
              "keyed by (claim, result) with their own digest "),
    _k("run", "project + run id",
       "canonical JSON of research_runs/run-<id>.json merged with its receipt at read",
       "O", "research_surface.py:799-812", (), "run_status {id} -> state",
       closes="research_surface.state_payload publishes producer_runs rows, but a "
              "live row carries pid, deadline_at and finished_at, so two reads of a "
              "RUNNING home would mint two tokens; research_surface.py:799-812 "
              "already settles a run with its receipt -- publish that settled value "
              "and this home becomes readable "),
    _k("producer", "project + producer path",
       "the declared producer file's exact bytes", "B", "research_surface.py:206-213",
       ("source_revision",), "research {view:full} -> current_dependencies[].sha256"),
    _k("artifact", "project + scope + path",
       "the artifact file's exact bytes", "B", "writing_tools.py:98-99 _artifact_revision",
       ("expected_revision", "before"), "read_artifact {path, scope} -> revision"),
    _k("visual-spec", "project + spec id",
       "canonical JSON of the figure spec", "O", "visuals_surface.py:237 vp.digest(spec",
       ("expected_revision",), "visuals {} -> specs[id].spec_revision",
       closes="same owner as visual: visuals_surface exposes only handle(...). "
              "visuals_surface.py:237 digests the spec already; export the specs "
              "projection as a module read and wire it "),
    _k("visual", "project + spec id",
       "canonical JSON of {spec_revision, placed_file, placed_caption}", "J",
       "visuals_surface.py:393 writes; :430 observes placement",
       (), "visuals {} -> placement",
       closes="visuals_surface exposes only handle(path, query, method, body, "
              "repo_root) -- an HTTP surface with no module-level read, while "
              "visuals_surface.py:237 already digests a spec. Export the "
              "specs/placement projection as a module read and wire it. NOTE: the "
              "guard expected_source_revision was declared on THIS home in round 1 "
              "of this packet and is removed, because both doors that compare that "
              "name (visuals_surface.py:349-350 and project_structure.py:777) "
              "compare the SELECTED EDITION, so selected-edition is its only home "),
    _k("note", "project + note id",
       "canonical JSON of the row the author-history page publishes for this note", "J",
       "pipeline/authoring.py:1150 writes the row {id, created, text, kind, scope, anchor, "
       "by, status, base_revision}; it publishes NO identity of its own --- its "
       "base_revision is the authoring-state home's counter, not this home's digest --- so "
       "this layer digests the published row.  Measured: author_history.history(project, "
       "{view: corrections}) returns 20 rows keyed `activity:journal:WR-...` with "
       "{id, at, status, summary, targets} and no revision.  NO GUARD: round 1 of this "
       "packet declared `supersedes` on this home.  It is a REFERENCE to another note's "
       "id, not an identity of any home's state --- writing_contracts.py:433 types it "
       "`_STRING` inside the note input and :436 says it \"explicitly replaces an "
       "obsolete instruction\" beside `reply_to`; the only comparisons in the tree are "
       "against ids (manuscript_structure.py:644 `row.get(\"supersedes\") == receipt_id`, "
       "concepts_surface.py:456, and pipeline/authoring.py:1143-1146 looks the row up by "
       "id), never against a revision.  So it travels in the request PAYLOAD, the way "
       "`anchor_text` does, and map_verbs.NOT_A_GUARD records it as a miscount in the "
       "20-name census",
       (),
       "author_history {view:corrections} -> rows[id]"),
    _k("storage", "project", "canonical JSON of measured store sizes", "J",
       "writing_storage.inspect", (), "storage {} -> bytes"),
    _k("task", "project + task id", "canonical JSON of the task row", "J",
       "project_work.py:124-140 state", (), "project {} -> tasks[id]"),
    _k("obligation", "project + node id", "canonical JSON of the obligation projection",
       "J", "concepts_surface.py logical_plan -> obligations", (),
       "logical_plan {} -> obligations[id]"),
    _k("relation", "project + source + rel + target",
       "canonical JSON of the typed edge row", "J",
       "concepts_surface.py:_relations (projection)", (), "concept_tree {node} -> relations"),
    _k("source-ref", "project + node id",
       "canonical JSON of the node's source_refs list", "J",
       "concepts_surface.py:_source_refs", (), "concept {node} -> focus.source"),
    _k("reference", "citekey",
       "canonical JSON of {version, modified} plus the provider metadata identity",
       "O", "references_surface.py:651, :478 _digest(_metadata(item))", (),
       "reference {key} -> source.revision"),
    _k("reference-text", "citekey + reading id",
       "the fetched full text's exact bytes", "B", "references_surface.py:207", (),
       "reference_text {key} -> reading_id"),
    _k("reference-candidate", "provider + query",
       "canonical JSON of the provider's returned row", "J",
       "references_surface.literature_discover", (), "literature_discover {q}",
       closes="the value is a provider's returned row, so obtaining it would make a "
              "NETWORK call and a read must not. Caller-value by design: the "
              "candidate is minted from the row the caller already received "),
    _k("material-reference", "project + binding id", "canonical registry membership fact with a consumed owner pin", "J",
       "writing_projects.material_references", (), "material_references {id,view:source}",
       closes="Read the exact binding and its owner identity; membership never grants owner write permission."),
    _k("project-metadata", "project",
       "canonical JSON of the project's registry_projects.json row", "O",
       "writing_projects.py:126-129 _metadata", ("expected_revision",),
       "project_metadata {} -> revision"),
    # the project authoring lifecycle (writing.project_lifecycle): one source-optional project's transition into a
    # selected manuscript and reader/argument plan ownership
    _k("project-lifecycle", "project",
       "canonical JSON of the registry row, the selected-source status/identity and the plan ownership facts", "O",
       "writing.project_lifecycle.observe", ("expected_project_lifecycle",),
       "project_metadata {} -> authoring_lifecycle.revision",
       closes="Starting authoring creates or adopts the manuscript and declares the plan owner; it writes no plan, prose or concept."),
    _k("guide-catalogue", "project",
       "canonical JSON of [{path, role, sha256}] over ALL configured guides", "O",
       "project_protocol.py:98-104 catalog_revision", ("expected_catalog_revision",),
       "project_guidance {} -> catalog_revision"),
    _k("guide-instructions", "project",
       "canonical JSON of [{path, role, sha256}] over the INSTRUCTIONS-role guides only",
       "O", "project_protocol.py:94-97, :103 (revision); :80-85 states why it is separate "
       "from catalog_revision -- a handoff update must be observable without invalidating a "
       "context that never read it",
       (), "project_guidance {} -> revision"),
    _k("guide-document", "project + guide path",
       "the guide Markdown file's exact bytes", "B", "project_protocol.py:72",
       ("before",), "project_guidance {path} -> sha256"),
    _k("style-profile", "repository-relative voice profile path (GLOBAL, not per project)",
       "the profile Markdown file's exact bytes", "O",
       "writing_style.py:34 _file_digest, :158", ("expected_profile_revision",),
       "writing_style {view:profile} -> profile_revision"),
    _k("style-state", "project",
       "canonical JSON of {profile, profile_revision, guidance, genre, provenance_revision}",
       "O", "writing_style.py:184-186", ("expected_revision",),
       "writing_style {view:summary} -> revision"),
    _k("style-provenance", "project",
       "canonical JSON of the provenance summary", "O",
       "writing_style.py:_provenance_summary", ("expected_provenance_revision",),
       "writing_style {view:provenance} -> provenance.revision"),
    _k("style-calibration", "project",
       "canonical JSON of the calibration projection", "J",
       "writing_style.writing_style_calibration", (), "writing_style_calibration {}",
       closes="writing_style.calibration(project, payload, repo_root) requires the "
              "calibration request as a payload, so there is no payload-free read "
              "of this home; writing_style would have to publish the current "
              "calibration in state() "),
    _k("stage", "project + stage",
       "canonical JSON of {stage, recipe, profiles, selected_source}", "O",
       "writing_stages.py:116-117", ("known_revision",), "writing_stage {stage} -> revision"),
    _k("proposal", "project + proposal id",
       "owner-sealed instance of authored content and immutable consumed input basis", "O",
       "manuscript_proposals.proposal_version (opaque instance); authored bytes separately proposal_content_sha256",
       (), "read proposal@paragraph -> returned exact proposal/version/edit/basis handles",
       closes="Read the exact owner proposal_version/identities from proposal preview, "
              "pending proposals or exact turn detail. Apply and decision require that "
              "instance; callers must not derive it from authored JSON or renew it with "
              "a later read. proposal_content_sha256 identifies authored bytes only."),
    _k("prose", "project + file + line range",
       "the exact bytes of the addressed block, whole lines", "B",
       "review_surface.py:1860 (`if current != before:`, the comparison --- VERIFIED by "
       "`grep -n 'current != before' src/laplace/manuscript/review_surface.py` -> 1860, against HEAD "
       "and in a worktree; the round-1 judgement asked for :1859 and is wrong); "
       "manuscript_blocks.py:50",
       ("before",),
       "source {files:[path]} -> blocks[]  (the exact span text stays EXACT and travels "
       "as payload.anchor_text, which is content, not identity: proposal_preflight.py:81, "
       ":93-97 must not be given to a model)",
       guard_doors=("before=review_surface.py:1860",)),
    _k("block", "project + file + line range",
       "the exact bytes of one parsed block", "B", "manuscript_blocks.py:50",
       ("expected_source_digest",), "source {files:[path]} -> blocks[]",
       guard_doors=("expected_source_digest=manuscript_blocks.py:49-52 (origin) and "
                    ":175-176, :221-222 (destination); manuscript_structure.py:540, :917",)),
    _k("section", "project + section id",
       "the section's source file bytes", "B", "manuscript_structure.py:50", (),
       "source {files:[path]}"),
    _k("heading", "project + file + line",
       "the heading line's exact bytes", "B", "manuscript_structure.py:46", (),
       "source {files:[path]}"),
    _k("chapter", "project + chapter file",
       "the chapter file's exact bytes", "B", "manuscript_structure.py:50", (),
       "source {files:[path]}"),
    _k("claim-position", "project + section id + claim id",
       "canonical JSON of {section, order, claim} in the plan", "J",
       "NOT MINTED TODAY -- `place`'s order obligation", (), "structure {} -> sections[].nodes",
       closes="no owner publishes a claim's position. project_structure.state's "
              "sections[].nodes carries the order implicitly; the lane that "
              "implements place must publish {section, order, claim} -- this is "
              "finding 1.8, reconcile saying CURRENT while plan order and input "
              "order disagreed in 4 of 7 positions "),
    _k("spine-position", "project + node id",
       "canonical JSON of {node, order} in the spine", "J",
       "concepts_surface.py:566 ledger_revision (nearest existing)", (),
       "logical_plan {} -> reader_order",
       closes="concepts_surface.logical_plan publishes reader_order as a STATUS "
              "dict {status, reason, revision, source_outline, omitted_sections}, "
              "not a position per node; the place lane must publish the node's own "
              "order "),
    _k("build", "project + mode",
       "the compiled PDF's exact bytes", "O", "document_style.py:422 pdf_sha256", (),
       "build_status {} -> pdf_sha256",
       closes="document_style.status(project, root) publishes {status, style} only; "
              "the pdf_sha256 at document_style.py:422 lives in the build receipt, "
              "not in the status projection "),
    _k("export", "project + mode",
       "the exported PDF's exact bytes", "O", "document_style.py:249", (),
       "export_pdf -> sha256",
       closes="obtaining it would RUN document_style.export_pdf at :249, i.e. do "
              "work, and a read must not. Caller-value by design, minted from the "
              "export receipt "),
    _k("experiment", "project + run id",
       "canonical JSON of {producer digest, declaration, inputs}", "O",
       "research_surface.py:206-213 + the run declaration", (), "run_status {id}",
       closes="research_surface publishes experiments with no digest (0 rows on the "
              "measured project); the value is a run declaration plus its producer "
              "digest research_surface.py:206-213, which nothing assembles into a "
              "published home "),
    _k("proof", "project + node id + declaration",
       "canonical JSON of {concept-network token, producer token, declaration}", "J",
       "pipeline/formal_verification.py:268, :396", (), "proof_targets {node}",
       closes="pipeline/formal_verification.py:268, :396 digests at verification "
              "time and no read republishes it; the proof lane must publish it "
              "beside the check receipt "),
    _k("turn", "turn id", "the delivered prompt's exact bytes", "O",
       "authoring_surface.py:1230 context_sha256", (),
       "conversation_history {} -> turns[id].context_sha256",
       closes="authoring_surface.session_turn_detail(root, project, ident, view) "
              "needs a turn id AND a view, so it is not a project-shaped read; the "
              "context_sha256 at :1230 is published inside the delivery record of "
              "one turn "),
    _k("act-ledger", "project",
       "canonical JSON of the activity projection page", "J", "author_history.py:758",
       (), "author_history {view:activity}",
       closes="author_history.history(project, {view: activity}, root) publishes "
              "the page, but the page carries as_of, a wall clock measured in this "
              "packet, so two reads of an UNCHANGED ledger would mint two tokens. "
              "The owner must publish a page digest that excludes as_of before this "
              "home can be read "),
    _k("change-history", "project", "canonical JSON of the author-change projection",
       "J", "manuscript_fragments.author_changes", (), "author_changes {}",
       closes="manuscript_fragments.author_changes publishes the projection and, "
              "like act-ledger, its rows carry live turn state; the same as_of "
              "exclusion is the fix "),
    _k("contract", "operation or empty",
       "canonical JSON of the published operation contract", "O",
       "writing_contracts.py:550 operation_contract", (), "help {operation}",
       closes="writing_contracts.operation_contract is keyed by an OPERATION, not a "
              "project, so it does not fit the project/root call shape; the "
              "generated-contract lane owns this home and publishes its digest with "
              "the contract "),
    _k("document-form", "project", "canonical JSON of the document style record", "J",
       "document_style.py:139-142 load() returns the raw document_style.json record (or {} "
       "when absent, which is this project's case) and publishes no revision, so this layer "
       "digests the record",
       (), "document {}"),
    _k("pipeline", "project", "canonical JSON of the pipeline projection", "J",
       "writing_pipeline.state", (), "pipeline {view:summary}"),
    _k("project", "project", "canonical JSON of the project projection", "J",
       "writing_tools.py project read", (), "project {}"),
    _k("repository", "project", "canonical JSON of the listed repository tree", "J",
       "writing_sources.py", (), "repository {action:list}",
       closes="writing_sources lists the tree on request with a path and a limit, "
              "so the value is a VIEW of a listing rather than a home with one "
              "settled value; a listing digest over the tracked paths would close "
              "it "),
    _k("repository-file", "project + path", "the file's exact bytes", "B",
       "writing_sources.py", (), "repository {action:read, path}"),
    _k("authoring-state", "project",
       "the exact bytes of the project's `authoring.json` --- THE BYTES THE COUNTER "
       "COUNTS.  The owner numbers this home with a monotone integer `revision` rather "
       "than a digest, and the token digests the file that integer lives in and counts, "
       "so the token grammar keeps one digest form.  The file: `_STATE_NAME` "
       "(pipeline/authoring.py:24) under the directory the owner's own `_state_path` "
       "(:63-86) resolves; `_write` (:244) is the only writer.  Measured consequence, "
       "stated because a replay will see it: :1084 rewrites the file for a context write "
       "WITHOUT incrementing `revision`, so this token discriminates one state the "
       "counter does not --- strictly more conservative (it can refuse where the counter "
       "accepted, never accept where the counter refused), and the counter itself stays "
       "in the refusal sentence the owner serves at :398-399.  ONE home, guarded by both "
       "the framing concept and the argument concept, under three accepted aliases for "
       "the one name",
       "B", "pipeline/authoring.py:93 (blank), :113 (coerced), :386-392 (accepts "
       "base_revision, expected_revision and revision as aliases), :398-399 (compares, and "
       "SERVES the value: `revision conflict: expected 0, current 2` -- the synthesis names "
       "this one of the three best refusals in the system), :434 (incremented). The sibling "
       "`argument_revision` (:94, :432) is published and compared by nothing",
       ("base_revision", "expected_revision", "revision"),
       "project {} -> revision  (pipeline/authoring.load -> revision)",
       ("revision", "argument_revision")),
    _k("framing", "project",
       "canonical JSON of the framing record {purpose, audience, question}", "J",
       "pipeline/authoring.py:_public (:288-289); its identity is authoring-state, not its "
       "own digest -- the content home and the guard home differ here exactly as "
       "concept-node differs from concept-network",
       (), "project {} -> framing"),
    _k("argument", "project",
       "canonical JSON of the sustained-argument record", "J",
       "pipeline/authoring.py:288-289; guarded through authoring-state", (),
       "project {} -> argument"),
)}

# Every guard name the friction report counted, resolved to its home.  A name that
# appears under two homes is listed under both; that is the measured fact (§1.3), and
# the pair (operation, name) resolves it -- see map_verbs.py GUARD_HOME.
GUARD_NAMES: dict[str, tuple[str, ...]] = {}
for _h in HOME_KINDS.values():
    for _g in _h.guards_today:
        GUARD_NAMES.setdefault(_g, ())
        GUARD_NAMES[_g] = GUARD_NAMES[_g] + (_h.kind,)

# The names a READ returns this value under.  The friction report's 20-name census is of
# published read fields; the guard census is of asked-for fields.  They are different sets and
# conflating them is how `sha256` came to look like a guard: `source` publishes it, no door
# compares it.  A payload may not speak a GUARD name; it may mention a PUBLISHED name freely,
# because a published name is where the caller got the value, not what it must send.
PUBLISHED_NAMES: dict[str, tuple[str, ...]] = {}
for _h in HOME_KINDS.values():
    for _p in _h.published_as:
        PUBLISHED_NAMES.setdefault(_p, ())
        PUBLISHED_NAMES[_p] = PUBLISHED_NAMES[_p] + (_h.kind,)


# ---------------------------------------------------------------------------
# 5. identity(home) --- ONE implementation per home kind.
#
# A byte home (recipe B) is read and digested here, exactly.  An owner-projection home
# (recipe O) is read THROUGH the owner and its published value is used verbatim, so the
# token is parity-safe.  A home with recipe J has no owner value today; this layer mints
# it from the stated canonical JSON, which is how `plan-section`, `claim-position` and
# `spine-position` become guardable at all.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class OwnerRead:
    """ONE read per home kind, declared: the owner, the call, the path, the selector.

    `form` must equal the kind's `recipe` (test_grammar.py proves it for all 58):
      O  the owner publishes the identity as a string at `path`; used verbatim.
      B  the owner read returns the FILE this home is: a path, and the token is a sha256
         of its exact bytes.  Wired for the one home whose owner keeps a counter instead
         of a digest (`authoring-state`); every other recipe-B home's id IS its path.
      J  no owner publishes an identity for this home.  The owner read gives this layer
         the home's own VALUE and the digest is computed here, by `digest_canonical_json`.
         Every J token is therefore a digest no owner holds; that is stated, never hidden.
    """
    module: str
    func: str
    args: str                    # the owner's own calling spelling; see _CALLS below
    path: str = ""               # dotted path into the return; "" is the whole return
    by_id: bool = False          # index the list at `path` by this home's own id
    form: str = "O"              # O | C | J
    payload: str = ""            # json payload for a read that takes one
    note: str = ""               # why this read and not another


# The owner call spellings, each the owner's own.  No normalising: writing_tools.py:941
# types `root: Path` and never coerces it, and 25 of 73 operations raise a Python internal
# error on a string root (synthesis.md §1.10).  This layer passes a Path or nothing.
_CALLS: dict[str, Callable[..., Any]] = {
    "p,r":          lambda f, p, n, r, pl: f(p, r),
    "p,r=root":     lambda f, p, n, r, pl: f(p, root=r),
    "p,r=repo":     lambda f, p, n, r, pl: f(p, repo_root=r),
    "p,n=,r=root":  lambda f, p, n, r, pl: f(p, node=n, root=r),
    "p,n,r":        lambda f, p, n, r, pl: f(p, n, r),
    "p,None,r":     lambda f, p, n, r, pl: f(p, None, r),
    "p,pl,r":       lambda f, p, n, r, pl: f(p, pl, r),
    "p,sel,r=repo": lambda f, p, n, r, pl: f(p, selection=pl or {}, repo_root=r,
                                             context_id=""),
    "r,p":          lambda f, p, n, r, pl: f(r, p),
}

# ---------------------------------------------------------------------------
# OWNER_READS --- the wired half of the home alphabet, measured on a real project.
# A kind absent from this table and not recipe B cannot be obtained from the home alone;
# its HomeKind.closes states the read or the owner publication that would close it, and
# `MINT_STATUS` / GRAMMAR.md §2.1 render the whole partition so no lane has to run the
# module to find out.  Verified by evidence/.../grammar/obtain_census.py on
# `synthetics-foundations` (a project tracked at HEAD, so every worktree carries it).
# ---------------------------------------------------------------------------
OWNER_READS: dict[str, OwnerRead] = {
    # --- the owner publishes the identity (recipe O)
    "selected-edition": OwnerRead("laplace.manuscript.manuscript_source", "resolve", "p,r=repo",
                                  "revision"),
    "source-traversal": OwnerRead(
        "laplace.pipeline.authoring", "inspect", "p,sel,r=repo", "source_revision",
        note="pipeline/authoring.py:722 computes it with _revision (:439-447) and :796 "
             "publishes it; NOT manuscript_structure.py:349-353, which digests a sorted "
             "[{file,sha256}] snapshot for the SOURCE_ONLY `plan` fallback --- a "
             "different value under a name one letter apart"),
    "plan-file": OwnerRead("laplace.manuscript.project_structure", "state", "p,r",
                           "authority.plan_revision"),
    "plan": OwnerRead("laplace.manuscript.project_structure", "state", "p,r", "revision"),
    "concept-network": OwnerRead("laplace.research.concepts", "state", "p,n=,r=root",
                                 "revision"),
    "concept-node": OwnerRead("laplace.research.concepts", "state", "p,n=,r=root",
                              "content_revision"),
    "concept-catalogue": OwnerRead("laplace.research.concepts", "catalog", "p,r=root",
                                   "revision"),
    "claim-meaning": OwnerRead("laplace.research.literature_support", "meaning_revision", "p,n,r"),
    "result": OwnerRead("laplace.research.research_catalogue", "state_payload", "p,r=root",
                        "results", by_id=True, form="O", note="row['revision']"),
    "reference": OwnerRead("laplace.research.references_surface", "attached", "p,r=root",
                           "associations", by_id=True, form="O",
                           note="row['source']['revision']"),
    "stage": OwnerRead("laplace.writing.stages", "inspect", "p,None,r", "revision"),
    "project-metadata": OwnerRead("laplace.projects.library", "metadata", "p,r",
                                  "revision"),
    "project-lifecycle": OwnerRead("laplace.projects.project_lifecycle", "observe", "p,r", "revision"),
    "guide-catalogue": OwnerRead("laplace.manuscript.project_protocol", "load", "p,r",
                                 "catalog_revision"),
    "guide-instructions": OwnerRead("laplace.manuscript.project_protocol", "load", "p,r", "revision"),
    "style-profile": OwnerRead("laplace.manuscript.writing_style", "state", "p,r=repo",
                               "profile_revision"),
    "style-state": OwnerRead("laplace.manuscript.writing_style", "state", "p,r=repo", "revision"),
    "style-provenance": OwnerRead("laplace.manuscript.writing_style", "state", "p,r=repo",
                                  "provenance.revision"),
    # --- the owner numbers the home with a counter, so the token digests the bytes the
    # counter counts: the owner's own resolver names the file, this layer reads it (B)
    "authoring-state": OwnerRead("laplace.pipeline.authoring", "_state_path", "p,r", "0",
                                 form="B",
                                 note="the public read (`load`) returns the state and the "
                                      "counter but not the path, so the one wired read is "
                                      "the owner's own path resolver and the digest is of "
                                      "that file's exact bytes. What would end the private "
                                      "call: authoring publishing either the state path or "
                                      "a digest of the file beside `revision`"),
    # --- no owner publishes an identity: this layer digests the home's own value (J)
    "plan-section": OwnerRead("laplace.manuscript.project_structure", "state", "p,r", "sections",
                              by_id=True, form="J"),
    "storage": OwnerRead("laplace.projects.writing_storage", "inspect", "p,r", "bytes", form="J"),
    "task": OwnerRead("laplace.work.project_work", "state", "p,r", "tasks", by_id=True,
                      form="J"),
    "obligation": OwnerRead("laplace.research.concepts", "logical_plan", "p,r=root",
                            "obligations", by_id=True, form="J"),
    "relation": OwnerRead("laplace.research.concepts", "state", "p,n=,r=root", "relations",
                          by_id=True, form="J"),
    "source-ref": OwnerRead("laplace.research.concepts", "state", "p,n=,r=root",
                            "source_support", form="J"),
    "framing": OwnerRead("laplace.pipeline.authoring", "load", "p,r", "framing", form="J"),
    "argument": OwnerRead("laplace.pipeline.authoring", "load", "p,r", "argument",
                          form="J"),
    "project": OwnerRead("laplace.work.project_work", "state", "p,r", "", form="J"),
    "pipeline": OwnerRead("laplace.manuscript.writing_pipeline", "inspect", "p,r", "", form="J"),
    "document-form": OwnerRead("laplace.manuscript.document_style", "load", "p,r=root", "", form="J"),
    "note": OwnerRead("laplace.work.history", "history", "p,pl,r", "items", by_id=True,
                      form="J", payload='{"view": "corrections"}'),
}


def _dig(value: Any, path: str) -> Any:
    if not path:
        return value
    for key in path.split("."):
        if value is None:
            return None
        # One owner read returns a tuple, not a mapping: pipeline/authoring._state_path
        # (:63-86) returns (authoring.json, source).  A digit segment indexes it, so the
        # declared path stays the owner's own shape and no wrapper is invented.
        if (key.isdigit() and isinstance(value, Sequence)
                and not isinstance(value, (str, bytes))):
            value = value[int(key)] if int(key) < len(value) else None
            continue
        value = value.get(key) if hasattr(value, "get") else None
    return value


def _select(rows: Any, ident: str, kind: str) -> Any:
    """Index a published container by this home's own id.  One selector, four key
    spellings, because the owners spell the row key four ways (`id`, `key`, `citekey`,
    `node_id`) and a fifth spelling would be a new convention."""
    if isinstance(rows, Mapping):
        if ident in rows:
            return rows[ident]
        rows = list(rows.values())
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise ValueError("home %s: the owner published no container to select from" % kind)
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        for field_name in ("id", "key", "citekey", "node_id"):
            if str(row.get(field_name) or "") == ident:
                return row
    raise ValueError("home %s:%s does not exist in this project (the owner's container "
                     "has %d rows and none is that id)" % (kind, ident, len(rows)))


def identity(home: Home | str, *, project: str = "", root: Path | None = None,
             bytes_: bytes | None = None, value: Any = None) -> Token:
    """The one read this home's token comes from --- one implementation per home kind.

    With neither ``bytes_`` nor ``value``, the home itself is read: a recipe-B home from
    disk, every other kind through its one `OWNER_READS` entry.  40 of the 58 kinds are
    obtainable this way (11 recipe-B homes whose id IS the path, read straight from disk,
    + 29 wired owner reads, one of which --- `authoring-state` --- is a recipe-B file
    whose path its owner resolves); the remaining 18 raise
    ``NotImplementedError`` naming what would close them, and a caller that holds the
    value may still mint by passing ``value=``.  Measured, not asserted: 38 of the 40
    minted on `synthetics-foundations` in a real git worktree and the other two
    (`relation`, `reference`) are wired reads whose home does not exist in that project
    --- see obtain_census.py and GRAMMAR.md §2.1.  ``MINT_STATUS`` is that partition, declared, and GRAMMAR.md
    §2.1 renders it, so a lane never has to run this module to learn which homes it can
    obtain a token for.

    ``bytes_`` or ``value`` short-circuit the read when the caller already holds the
    home's content (a writer that has just staged bytes must be able to mint the token it
    is about to own without a second disk read).
    """
    home = home if isinstance(home, Home) else Home(*str(home).split(":", 1))
    kind = HOME_KINDS[home.kind]
    if bytes_ is not None:
        return mint(home.kind, home.id, digest_bytes(bytes_))
    if value is not None:
        return mint(home.kind, home.id, digest_canonical_json(value))
    if kind.recipe == "B" and home.kind not in OWNER_READS:
        base = Path(root or ".")
        relative = home.within or home.id
        path = Path(relative) if Path(relative).is_absolute() else base / relative
        return mint(home.kind, home.id, digest_bytes(path.read_bytes()))
    spec = OWNER_READS.get(home.kind)
    if spec is None:
        raise NotImplementedError(
            "home %r cannot be obtained from the home alone: no read is wired. "
            "What would close it: %s. The read a caller uses today: %s. Owner: %s. "
            "Until then, pass value= (its canonical JSON) and the digest is minted here."
            % (home.kind, kind.closes or "undeclared --- that is a defect in this table",
               kind.read or "none published", kind.source))
    raw = read_owner(spec, home, project=project, root=root)
    if spec.form == "B":
        # The owner resolved the FILE this home is; the digest is of its exact bytes, with
        # the same function every other recipe-B home uses.
        if not isinstance(raw, (str, Path)) or not str(raw):
            raise ValueError("home %s: the owner read %s.%s resolved no file path (got %r)"
                             % (home, spec.module, spec.func, raw))
        return mint(home.kind, home.id, digest_bytes(Path(raw).read_bytes()))
    if spec.form == "J":
        if raw is None:
            raise ValueError("owner read %s.%s published no %r for %s"
                             % (spec.module, spec.func, spec.path, home))
        return mint(home.kind, home.id, digest_canonical_json(raw))
    if isinstance(raw, Mapping):              # an O row: its own published revision
        raw = raw.get("revision") or _dig(raw, "source.revision")
    if not isinstance(raw, str) or not raw:
        raise ValueError("owner read %s.%s published no %s for %s"
                         % (spec.module, spec.func, spec.path or "value", home))
    return mint(home.kind, home.id, raw)


def read_owner(spec: OwnerRead, home: Home, *, project: str = "",
               root: Path | None = None) -> Any:
    """Call one owner read with that owner's own spelling, and dig out this home's value."""
    import importlib
    module = importlib.import_module(spec.module)
    func = getattr(module, spec.func)
    call = _CALLS[spec.args]
    payload = json.loads(spec.payload) if spec.payload else None
    base = Path(root) if root is not None else None
    ident = home.within
    read = call(func, project or home.segments[0], ident, base, payload)
    raw = _dig(read, spec.path)
    if spec.by_id:
        raw = _select(raw, ident, home.kind)
    return raw


# The partition a lane reads instead of running the module.  "read" --- identity(home)
# obtains it from the home alone; "caller-value" --- the caller must supply `value=`
# because no owner publishes this home and no read is wired to its container yet.
def mint_status(kind: str) -> str:
    home = HOME_KINDS[kind]
    if home.recipe == "B":
        return "read"
    return "read" if kind in OWNER_READS else "caller-value"


# Existing technical report channel, distinct from manuscript instructions and graph rewires.
HOME_KINDS['technical-friction'] = _k('technical-friction','project + report id',
    'the existing friction/fork report and evidence-qualified supersession records','J',
    'corpus_ingest.friction_add; pipeline.friction_consumer.open_frictions',(),
    'read technical-friction@project -> current report collection/exact returned report',
    closes='Reporting creates an open technical observation only; no manuscript guidance, scientific membership or work completion authority.')

# Architecture and profile candidates are actual owners, distinct from TeX spans.
HOME_KINDS['architecture-profile'] = _k('architecture-profile','workspace architecture profile inspected from project context',
    'the current workspace structural preferences and exact field-confirmation decisions','O',
    'writing.profiles.inspect; pipeline.narrative.architecture_status',(),
    'read architecture-profile@project {family:architecture,scope:workspace}',
    closes='Preference application and explicit personal confirmation are separate; no scientific acceptance.')
HOME_KINDS['profile-candidate'] = _k('profile-candidate','producing project plus immutable PROP id/version',
    'one typed profile candidate in existing proposal/application/decision custody','J',
    'writing.profiles.inspect; writing.profiles.change',(),
    'read profile-candidate@project {view:candidate,candidate_ref}',
    closes='An exact profile candidate is not a manuscript paragraph edit or fake provider turn.')

HOME_KINDS['workflow-definition'] = _k('workflow-definition','project + immutable definition id/version',
    'the existing owner definition_revision over exact body, scope and predecessor','O',
    'pipeline.workflow_definitions.save; pipeline.workflow_definitions._view',(),
    'project {view:workflow-definitions,request:{definition_id,version}} -> edit_revision',
    closes='Copy the exact viewed owner edit_revision into expected_revision; a generic head lookup must never renew a historical draft guard.')

MINT_STATUS: dict[str, str] = {kind: mint_status(kind) for kind in HOME_KINDS}
OBTAINABLE: tuple[str, ...] = tuple(k for k, v in MINT_STATUS.items() if v == "read")
CALLER_VALUE: tuple[str, ...] = tuple(k for k, v in MINT_STATUS.items()
                                      if v == "caller-value")


# ---------------------------------------------------------------------------
# 6. The concept sets, and the request.
#
# The (verb, concept) option set is CLOSED and enumerable.  `CONCEPTS` and `VERB_CONCEPTS`
# below are generated from mapping.csv by map_verbs.py --- the same rows the §7 table
# renders --- so there is one row source and no second list to agree with.  A lane that
# needs a pair the audit never reached calls `declare_pair(verb, concept, because=...)`
# and the reason is on record; it cannot simply pass a new string, which is the door
# through which 73 operations grew 152 bare-string sub-verbs (synthesis.md §1.7).
# ---------------------------------------------------------------------------
# BEGIN GENERATED CONCEPTS (map_verbs.py from mapping.csv; do not edit by hand)
CONCEPTS: frozenset = frozenset({
    "act-ledger@project",
    "argument@plan",
    "artifact@project",
    "block@paragraph",
    "build@project",
    "change-history@project",
    "chapter@chapter",
    "claim-meaning@claim",
    "claim-position@section",
    "concept-catalogue@plan",
    "concept-network@claim",
    "concept-network@plan",
    "concept-node@claim",
    "contract@project",
    "document-form@project",
    "experiment@run",
    "export@project",
    "framing@plan",
    "guide-catalogue@project",
    "guide-document@project",
    "heading@section",
    "note@claim",
    "note@project",
    "obligation@claim",
    "pipeline@project",
    "plan-section@section",
    "plan@plan",
    "producer@run",
    "material-reference@project",
    "project-metadata@project",
    "project@project",
    "proof@claim",
    "proof@project",
    "proposal@paragraph",
    "prose@paragraph",
    "reference-candidate@evidence",
    "reference-text@evidence",
    "reference@claim",
    "reference@evidence",
    "reference@project",
    "reference@section",
    "relation@relation",
    "repository-file@paragraph",
    "repository@project",
    "result-binding@evidence",
    "result@claim",
    "result@project",
    "result@run",
    "run@run",
    "section@section",
    "source-file@paragraph",
    "source-ref@claim",
    "spine-position@plan",
    "stage@project",
    "storage@project",
    "style-calibration@project",
    "style-profile@project",
    "style-provenance@project",
    "style-state@project",
    "task@claim",
    "task@evidence",
    "task@project",
    "task@section",
    "turn@project",
    "visual-spec@run",
    "visual@project",
    "visual@run",
    "visual@section",
})
VERB_CONCEPTS: frozenset = frozenset({
    ("bind", "claim-position@section"),
    ("bind", "reference@evidence"),
    ("bind", "reference@section"),
    ("bind", "relation@relation"),
    ("bind", "result@claim"),
    ("bind", "source-ref@claim"),
    ("bind", "task@claim"),
    ("change", "argument@plan"),
    ("change", "artifact@project"),
    ("change", "block@paragraph"),
    ("change", "claim-meaning@claim"),
    ("change", "concept-node@claim"),
    ("change", "document-form@project"),
    ("change", "framing@plan"),
    ("change", "guide-catalogue@project"),
    ("change", "guide-document@project"),
    ("change", "note@claim"),
    ("change", "obligation@claim"),
    ("change", "plan-section@section"),
    ("change", "plan@plan"),
    ("change", "project-metadata@project"),
    ("change", "prose@paragraph"),
    ("change", "reference@evidence"),
    ("change", "relation@relation"),
    ("change", "result-binding@evidence"),
    ("change", "run@run"),
    ("change", "section@section"),
    ("change", "style-profile@project"),
    ("change", "style-state@project"),
    ("change", "task@evidence"),
    ("change", "turn@project"),
    ("create", "block@paragraph"),
    ("create", "chapter@chapter"),
    ("create", "concept-node@claim"),
    ("create", "heading@section"),
    ("create", "note@claim"),
    ("create", "obligation@claim"),
    ("create", "plan-section@section"),
    ("create", "plan@plan"),
    ("create", "producer@run"),
    ("create", "proposal@paragraph"),
    ("create", "reference@evidence"),
    ("create", "section@section"),
    ("create", "task@project"),
    ("create", "task@section"),
    ("create", "visual-spec@run"),
    ("delete", "block@paragraph"),
    ("delete", "claim-position@section"),
    ("delete", "note@claim"),
    ("delete", "plan-section@section"),
    ("delete", "proposal@paragraph"),
    ("delete", "relation@relation"),
    ("delete", "section@section"),
    ("delete", "spine-position@plan"),
    ("delete", "storage@project"),
    ("move", "block@paragraph"),
    ("move", "claim-position@section"),
    ("move", "concept-node@claim"),
    ("move", "plan-section@section"),
    ("move", "spine-position@plan"),
    ("place", "claim-position@section"),
    ("place", "spine-position@plan"),
    ("place", "visual@section"),
    ("read", "act-ledger@project"),
    ("read", "artifact@project"),
    ("read", "build@project"),
    ("read", "change-history@project"),
    ("read", "concept-catalogue@plan"),
    ("read", "concept-network@claim"),
    ("read", "concept-network@plan"),
    ("read", "concept-node@claim"),
    ("read", "contract@project"),
    ("read", "document-form@project"),
    ("read", "guide-document@project"),
    ("read", "note@project"),
    ("read", "pipeline@project"),
    ("read", "plan@plan"),
    ("read", "material-reference@project"),
    ("create", "material-reference@project"),
    ("change", "material-reference@project"),
    ("delete", "material-reference@project"),
    ("read", "project-metadata@project"),
    ("read", "project@project"),
    ("read", "proof@claim"),
    ("read", "proof@project"),
    ("read", "reference-candidate@evidence"),
    ("read", "reference-text@evidence"),
    ("read", "reference@claim"),
    ("read", "reference@evidence"),
    ("read", "reference@project"),
    ("read", "repository-file@paragraph"),
    ("read", "repository@project"),
    ("read", "result@project"),
    ("read", "run@run"),
    ("read", "source-file@paragraph"),
    ("read", "stage@project"),
    ("read", "storage@project"),
    ("read", "style-calibration@project"),
    ("read", "style-profile@project"),
    ("read", "style-provenance@project"),
    ("read", "style-state@project"),
    ("read", "task@project"),
    ("read", "turn@project"),
    ("read", "visual@project"),
    ("record", "result@run"),
    ("run", "build@project"),
    ("run", "experiment@run"),
    ("run", "export@project"),
    ("run", "plan@plan"),
    ("run", "proof@claim"),
    ("run", "reference-text@evidence"),
    ("run", "reference@project"),
    ("run", "task@project"),
    ("run", "visual@run"),
})
# END GENERATED CONCEPTS

ADDED_PAIRS: dict[tuple[str, str], str] = {}


def declare_pair(verb: str, concept: str, *, because: str) -> tuple[str, str]:
    """Add one (verb, concept) pair to the closed set, with its reason on record."""
    if verb not in VERBS:
        raise ValueError("verb must be one of %r; got %r" % (VERBS, verb))
    concept_altitude(concept)
    if concept_object(concept) not in HOME_KINDS:
        raise ValueError("the object half must be a home kind of §2; got %r"
                         % (concept_object(concept),))
    if not because.strip():
        raise ValueError("a new (verb, concept) pair carries the measurement that demands "
                         "it; `because` is empty")
    ADDED_PAIRS[(verb, concept)] = because
    return (verb, concept)


def declared_pair(verb: str, concept: str) -> bool:
    return (verb, concept) in VERB_CONCEPTS or (verb, concept) in ADDED_PAIRS


# ---------------------------------------------------------------------------
# THE ONE COLLISION between the fixed request shape and an owner's own payload key,
# and WHICH SIDE WINS THE SPELLING.  Declared here once, so four build lanes do not
# each invent a spelling for it.
#
# `logical_plan_change operation=connect` declares a top-level `target` --- the far
# endpoint of the edge --- at writing_contracts.py:607
# (``if name=="connect":properties["target"]=_STRING``).  The request's `target` is the
# home the act is about, so the payload rule below ("a payload may not restate a request
# field") refused that route its own payload entirely.  It is a LIVE shape, not a
# malformed one: 2 rows of the recorded corpus carry a top-level `target`, both
# `logical_plan_change`, and one of them applied.
#
# The REQUEST FIELD wins the name.  The six keys are the same six for all 104 declared
# pairs and are spoken by the door, the receipt, the refusal and every shim; renaming one
# of them to clear one owner's key would make the uniform half of the grammar negotiable
# per concept, which is the specialisation rule inverted.  The owner's key travels in the
# payload under the carrier declared here and the shim restores the owner's spelling AT the
# owner's door (`to_owner_payload`), so the owner's bytes never change and no second
# request shape exists.  `concept_change`'s edges are untouched: they carry their target
# inside the op object (writing_contracts.py:579), so they never collide.
#
#   key the owner spells -> (the carrier the grammar's payload spells, why)
# ---------------------------------------------------------------------------
PAYLOAD_CARRIERS: dict[str, tuple[str, str]] = {
    "by": ("owner_by", "Literal declared owner attribution; distinct from outer requested Request.by, never actual permission."),
    "target": ("edge_target",
               "logical_plan_change operation=connect, writing_contracts.py:607: the far "
               "endpoint of the edge, a node id. It collides with Request.target, the home "
               "the act is about. 2 recorded corpus rows carry it, 1 applied. The request "
               "field keeps the name; the payload carries the owner's key as `edge_target` "
               "and the shim writes `target` back at the owner's door."),
}


def carrier_for(key: str) -> str | None:
    """The carrier the grammar's payload spells for an owner key that collides, or None."""
    entry = PAYLOAD_CARRIERS.get(key)
    return entry[0] if entry else None


def owner_key_for(carrier: str) -> str | None:
    """The owner's spelling a carrier stands for, or None if it is an ordinary key."""
    for key, (name, _because) in PAYLOAD_CARRIERS.items():
        if name == carrier:
            return key
    return None


def _one_spelling(payload: Mapping[str, Any], key: str, carrier: str) -> None:
    if key in payload and carrier in payload:
        raise ValueError(
            "a payload holds ONE spelling of %r: the owner's key or its carrier %r, never "
            "both, or the door would have to choose." % (key, carrier))


def to_payload(owner_payload: Mapping[str, Any]) -> dict[str, Any]:
    """An owner's payload in the grammar's spelling: a colliding key moved to its carrier.

    The ONE function that does this, so a lane never writes the rename itself.
    """
    out = dict(owner_payload)
    for key, (carrier, _because) in PAYLOAD_CARRIERS.items():
        _one_spelling(owner_payload, key, carrier)
        if key in out:
            out[carrier] = out.pop(key)
    return out


def to_owner_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """The reverse: what the shim hands the owner, in the owner's own spelling."""
    out = dict(payload)
    for key, (carrier, _because) in PAYLOAD_CARRIERS.items():
        _one_spelling(payload, key, carrier)
        if carrier in out:
            out[key] = out.pop(carrier)
    return out


# ---------------------------------------------------------------------------
# The writer field a Request carries.  Which doors take a literal owner `by`, and why, is the
# native declaration table's census (laplace.native.declarations.by_at), not this grammar.
# ---------------------------------------------------------------------------
WRITER_FIELD = "by"

# ---------------------------------------------------------------------------
# The request.  Six keys, the same six for every verb and every concept.
# ---------------------------------------------------------------------------
for _profile_object in ('architecture-profile', 'profile-candidate'):
    for _profile_verb in ('read', 'change'):
        declare_pair(_profile_verb, _profile_object+'@project', because='M4 typed architecture/voice candidate inspection and guarded existing-owner application; no source-edit alias.')

@dataclass(frozen=True)
class Request:
    verb: str
    concept: str
    target: str                      # the home id the act is about ("" for a whole-project act)
    expected: tuple[str, ...] = ()   # tokens, in any order; require() checks all of them
    payload: Mapping[str, Any] = field(default_factory=dict)
    by: str = ""

    FIXED = ("verb", "concept", "target", "expected", "payload", "by")

    def __post_init__(self) -> None:
        if self.verb not in VERBS:
            raise ValueError("verb must be one of %r; a concept may not add one "
                             "(got %r)" % (VERBS, self.verb))
        concept_altitude(self.concept)      # validates the altitude half
        obj = concept_object(self.concept)  # ... and now the OBJECT half
        if obj not in HOME_KINDS:
            raise ValueError(
                "the object half of a concept is one of the %d home kinds of §2, so the "
                "option set stays closed; %r is not one. A lane that needs a new object "
                "adds a home kind to HOME_KINDS with the measurement that demands it."
                % (len(HOME_KINDS), obj))
        if VERB_CONCEPTS and not declared_pair(self.verb, self.concept):
            if self.concept not in CONCEPTS:
                raise ValueError(
                    "concept %r is not one of the %d concepts the audited work reaches "
                    "(generated from mapping.csv). Add it with declare_pair(verb, concept, "
                    "because=...) and the reason is on record."
                    % (self.concept, len(CONCEPTS)))
            raise ValueError(
                "(%r, %r) is not one of the %d declared pairs (plus %d a lane declared); "
                "the concept exists but no audited work does THAT verb at it. Add it with "
                "declare_pair(verb, concept, because=...)."
                % (self.verb, self.concept, len(VERB_CONCEPTS), len(ADDED_PAIRS)))
        for token in self.expected:
            parse(token)
        overlap = set(self.payload) & set(self.FIXED)
        if overlap:
            carried = {key: PAYLOAD_CARRIERS[key][0] for key in sorted(overlap)
                       if key in PAYLOAD_CARRIERS}
            raise ValueError(
                "payload may not restate a request field: %r. Specialisation lives only in "
                "the payload's own keys.%s" % (
                    sorted(overlap),
                    ("" if not carried else
                     " An owner that spells one of these itself has a declared carrier: %s. "
                     "Build the payload with grammar.to_payload(owner_payload) and let the "
                     "shim call grammar.to_owner_payload at the owner's door; do not invent "
                     "a second spelling." % (carried,))))
        for key in self.payload:
            if key in GUARD_NAMES:
                raise ValueError(
                    "payload key %r is an old guard name for home(s) %r. An identity is "
                    "presented in `expected` as a token, never as a payload field; only a "
                    "Shim may speak this name." % (key, GUARD_NAMES[key]))

    @property
    def altitude(self) -> str:
        return concept_altitude(self.concept)

    @property
    def object(self) -> str:
        return concept_object(self.concept)

    def tokens(self) -> tuple[Token, ...]:
        return tuple(parse(t) for t in self.expected)


# The carrier table is checked AT IMPORT, so a lane cannot add an entry that would
# re-open the collision it exists to close: a carrier may only stand for a key that is
# actually a request field, may not itself be a request field or an old guard name (which
# `Request` refuses in a payload), may not collide with another carrier, and carries its
# reason.  A module that fails this does not load.
for _key, (_carrier, _because) in PAYLOAD_CARRIERS.items():
    if _key not in Request.FIXED:
        raise ValueError("a carrier is declared for a key that collides with a REQUEST "
                         "field; %r is not one of %r" % (_key, Request.FIXED))
    if _carrier in Request.FIXED:
        raise ValueError("carrier %r is itself a request field, so it collides too"
                         % (_carrier,))
    if _carrier in GUARD_NAMES:
        raise ValueError("carrier %r is an old guard name for %r; an identity travels in "
                         "`expected`" % (_carrier, GUARD_NAMES.get(_carrier)))
    if not _because.strip():
        raise ValueError("carrier %r carries no reason" % (_carrier,))
if len({name for name, _ in PAYLOAD_CARRIERS.values()}) != len(PAYLOAD_CARRIERS):
    raise ValueError("two owner keys share one carrier spelling")
del _key, _carrier, _because


# ---------------------------------------------------------------------------
# 7. The receipt and the refusal.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Affected:
    home: str            # str(Home)
    before: str | None   # token, or None when the home did not exist
    after: str | None    # token, or None when the home was removed


@dataclass(frozen=True)
class Receipt:
    outcome: str                             # applied | banked | refused
    affected: tuple[Affected, ...] = ()
    receipt_id: str = ""
    banked_row: Mapping[str, str] = field(default_factory=dict)
    next: tuple[Mapping[str, Any], ...] = ()
    ok: bool = True

    OUTCOMES = ("applied", "banked", "refused")

    def __post_init__(self) -> None:
        if self.outcome not in self.OUTCOMES:
            raise ValueError("outcome must be one of %r" % (self.OUTCOMES,))
        if self.outcome == "refused" and self.ok:
            raise ValueError("a refused receipt is not ok")
        for key in ("verb", "concept", "altitude"):
            if self.banked_row and key not in self.banked_row:
                raise ValueError("banked_row must carry verb, concept and altitude "
                                 "(synthesis.md §1.7); missing %r" % (key,))

    @staticmethod
    def for_(request: Request, outcome: str, affected: Iterable[Affected] = (),
             next: Iterable[Mapping[str, Any]] = ()) -> "Receipt":
        """Build the receipt of one request.  `banked_row` is filled from the request,
        so the verb and the altitude of a completed act are on record without re-parsing
        the payload (synthesis.md §1.7, writing_tools.py:959-971 and :1000-1006)."""
        return Receipt(outcome=outcome, affected=tuple(affected),
                       receipt_id=outcome[:3].upper() + "-" + uuid.uuid4().hex[:16],
                       banked_row={"verb": request.verb, "concept": request.concept,
                                   "altitude": request.altitude,
                                   "target": request.target, "by": request.by},
                       next=tuple(next), ok=outcome != "refused")

    def response(self) -> dict[str, Any]:
        return {"ok": self.ok, "outcome": self.outcome,
                "affected": [{"home": a.home, "before": a.before, "after": a.after}
                             for a in self.affected],
                "receipt_id": self.receipt_id,
                "banked_row": dict(self.banked_row),
                "next": [dict(n) for n in self.next]}


@dataclass(frozen=True)
class Refusal:
    kind: str                               # identity-stale | unknown-home | state-not-reached | shape
    homes: tuple[Mapping[str, Any], ...] = ()   # [{home, current_token}]
    needed: Mapping[str, Any] = field(default_factory=dict)
    said: str = ""

    KINDS = ("identity-stale", "unknown-home", "state-not-reached", "shape")

    def __post_init__(self) -> None:
        if self.kind not in self.KINDS:
            raise ValueError("refusal kind must be one of %r" % (self.KINDS,))

    def response(self) -> dict[str, Any]:
        return {"ok": False, "refused": {
            "kind": self.kind,
            "homes": [dict(h) for h in self.homes],
            "needed": dict(self.needed),
            "said": self.said}}


class Refused(Exception):
    """A refusal that carries its own cure.

    ``refusal.needed`` is the resolver: a mapping of request field to the exact value
    to send.  A caller retries with ``{**request_dict, **refusal.needed}`` and sends
    nothing it had to guess.  This replaces `retry_instruction`, which reached two
    caller paths of the four (synthesis.md §1.10, writing_tools.py:1049, :1240,
    writing_provider.py:555) because it was built in the response formatter instead of
    in the comparison.
    """

    def __init__(self, refusal: Refusal) -> None:
        super().__init__(refusal.said or refusal.kind)
        self.refusal = refusal

    def response(self) -> dict[str, Any]:
        return self.refusal.response()


# ---------------------------------------------------------------------------
# 8. require(expected, homes) --- the one comparison.
# ---------------------------------------------------------------------------
def require(expected: Sequence[str | Token], homes: Sequence[str | Token]) -> None:
    """Compare every expected token against the observed homes; refuse with the cure.

    Checks ALL of them.  `bind_results` requires two homes and names only the one it
    checked first (synthesis.md §1.1); one writer paid 8 refusals learning that.  Here a
    single refusal lists every stale and every unknown home, and `needed["expected"]` is
    the complete list that would be accepted.
    """
    observed = {t.key: t for t in (parse(h) for h in homes)}
    want = [parse(e) for e in expected]
    stale, unknown = [], []
    for token in want:
        have = observed.get(token.key)
        if have is None:
            unknown.append(token)
        elif have.digest != token.digest:
            stale.append((token, have))
    if not stale and not unknown:
        return
    accepted = [str(observed[t.key]) if t.key in observed else None for t in want]
    rows: list[Mapping[str, Any]] = []
    for token, have in stale:
        rows.append({"home": str(token.home), "current_token": str(have),
                     "sent_token": str(token),
                     "read": HOME_KINDS[token.kind].read,
                     "bytes": HOME_KINDS[token.kind].bytes})
    for token in unknown:
        rows.append({"home": str(token.home), "current_token": None,
                     "sent_token": str(token),
                     "read": HOME_KINDS[token.kind].read,
                     "bytes": HOME_KINDS[token.kind].bytes})
    kind = "unknown-home" if unknown and not stale else "identity-stale"
    said = "; ".join(
        "%s moved" % str(t.home) for t, _ in stale) or "; ".join(
        "%s is not a home of this project" % str(t.home) for t in unknown)
    needed: dict[str, Any] = {}
    if all(a is not None for a in accepted):
        needed["expected"] = accepted
    else:
        needed["expected"] = [a for a in accepted if a is not None]
        needed["unresolved"] = [str(t.home) for t in unknown]
    raise Refused(Refusal(kind=kind, homes=tuple(rows), needed=needed, said=said))


# ---------------------------------------------------------------------------
# 9. The shim.  The only place an old name is ever spoken.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Shim:
    """One old operation name, rewritten into one grammar request.

    Rules, all four load-bearing:
      1. A shim REWRITES; it never implements.  It calls the same function the grammar
         request calls, so there is one code path and replay cannot diverge.
      2. A shim carries an `expiry` --- a date and the parity run that retires it.  A
         shim with no expiry is the mapping file this grammar refuses.
      3. A shim translates a refusal back: `needed` comes out of `require` keyed by
         grammar fields, and the shim renames those keys to the old guard names it
         accepts.  So an old caller still gets a resolver, not an instruction.
      4. A shim is retired when differential replay over the recorded corpus is
         byte-identical through the grammar request alone.
    """
    old_operation: str
    old_verb: str
    verb: str
    concept: str
    guard_to_home: Mapping[str, str]
    expiry: str

    _EXPIRY = re.compile(r"\b(20\d\d-\d\d-\d\d)\b")

    def __post_init__(self) -> None:
        """Rule 2 is a gate, not a docstring.  Home, Request, Receipt and Refusal all
        validate themselves; the shim is the object a lane is most likely to construct by
        hand (from mapping.csv), so it is the one that most needs the gate."""
        if not str(self.old_operation).strip() or not str(self.old_verb).strip():
            raise ValueError("a shim names the old operation and the old verb it retires")
        if self.verb not in VERBS:
            raise ValueError("a shim rewrites INTO the grammar: verb must be one of %r, "
                             "got %r" % (VERBS, self.verb))
        concept_altitude(self.concept)
        if concept_object(self.concept) not in HOME_KINDS:
            raise ValueError("a shim's concept object is a home kind of §2; got %r"
                             % (concept_object(self.concept),))
        for guard, home in dict(self.guard_to_home).items():
            for one in str(home).split("|"):
                if one not in HOME_KINDS:
                    raise ValueError(
                        "shim %s/%s maps the old guard %r to %r, which is not a home kind "
                        "(a legal value is a HOME_KINDS key, or `a|b` when one door accepts "
                        "two homes, e.g. plan|plan-file)"
                        % (self.old_operation, self.old_verb, guard, one))
        expiry = str(self.expiry or "")
        if not expiry.strip():
            raise ValueError(
                "a shim with no expiry is the mapping file this grammar refuses "
                "(%s/%s)" % (self.old_operation, self.old_verb))
        if self._EXPIRY.search(expiry) is None or "parity" not in expiry.lower():
            raise ValueError(
                "an expiry is a DATE (YYYY-MM-DD) and the parity run that retires it; "
                "%r is neither, so nothing would ever delete this shim" % (expiry,))

    def to_request(self, old_payload: Mapping[str, Any], *, target: str = "",
                   by: str = "") -> Request:
        expected: list[str] = []
        payload: dict[str, Any] = {}
        for key, value in old_payload.items():
            home_kind = self.guard_to_home.get(key)
            if home_kind is None:
                if key not in {"project", "operation", "op", "view", "mode", "action",
                               "basis", "kind"}:
                    payload[key] = value
                continue
            if isinstance(value, str) and value:
                expected.append(str(mint(home_kind, target, value)))
        return Request(verb=self.verb, concept=self.concept, target=target,
                       expected=tuple(expected), payload=to_payload(payload), by=by)

    def from_refusal(self, refusal: Refusal) -> dict[str, Any]:
        """Rename the resolver back into the old guard names this shim accepts."""
        home_to_guard = {home: guard for guard, home in self.guard_to_home.items()}
        out: dict[str, Any] = {}
        for token in (parse(t) for t in refusal.needed.get("expected", ())):
            guard = home_to_guard.get(token.kind)
            if guard:
                out[guard] = token.digest
        return out


SHIMS: dict[tuple[str, str], Shim] = {}


def register_shim(shim: Shim) -> Shim:
    SHIMS[(shim.old_operation, shim.old_verb)] = shim
    return shim


# The two shims the friction report's two sharpest instances need.  Every other old
# name is registered by the lane that owns its operation, from mapping.csv.
register_shim(Shim(
    old_operation="structure_change", old_verb="operation=bind_results",
    verb="bind", concept="result@claim",
    guard_to_home={"expected_revision": "plan",
                   "expected_concept_revision": "concept-network"},
    expiry="retire on WRITING-RECONCILIATION replay parity; review 2026-11-01"))
register_shim(Shim(
    old_operation="logical_plan_change", old_verb="operation=add_object",
    verb="create", concept="concept-node@claim",
    guard_to_home={"base_revision": "concept-network"},
    expiry="retire on WRITING-RECONCILIATION replay parity; review 2026-11-01"))

# Existing HTTP proposal reads now compose through the same native verb door.
declare_pair("read", "proposal@paragraph", because="Existing /authoring/proposals and /authoring/proposal-preview own collection/version/edit/basis reads; native navigation reuses these owners.")

# Same nine verbs, existing typed technical object/owner, no convenience operation.
for _verb in ('read','record','create'):
    declare_pair(_verb,'technical-friction@project',because='Existing corpus friction_add/open_frictions owner reports runtime capability gaps without changing manuscript guidance or parent work.')

declare_pair('change', 'workflow-definition@project', because='Native definition Save joins the existing project-scoped immutable definition owner; it neither prepares nor runs a workflow.')
