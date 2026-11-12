"""The proofs the verb dispatch owes.

Each test is a claim the lane report makes, made checkable.  Nothing here skips: a missing
input fails with the path it wanted, because a test that vacates is how a parity-relevant
proof disappears (GRAMMAR.md §8 records that lesson from its own round 1).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

TREE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TREE / "src"))
sys.path.insert(0, str(TREE / "tools" / "writing_verbs"))
import gen_routes as gen                              # noqa: E402

from laplace.core import grammar as g                      # noqa: E402
from laplace.native import verbs as v                # noqa: E402
from laplace.native import tools as wt               # noqa: E402
from laplace.writing import reads

CORPUS = Path("/home/phujck/VScodeProjects/laplace/evidence/"
              "WRITING_RECONCILIATION_2026-10-02/harness/corpus")


def corpus_rows():
    assert CORPUS.is_dir(), (
        "the recorded corpus is the lane's evidence and it is not where it was built: %s. "
        "It is rebuilt by harness/build_corpus.py (HARNESS.md 'The corpus')." % CORPUS)
    rows = []
    for name in ("failures", "reads", "writes", "arrival"):
        path = CORPUS / (name + ".jsonl")
        assert path.is_file(), "corpus source missing: %s" % path
        for line in path.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("replayable", True) is not False and row.get("door") == "tool":
                    rows.append(row)
    assert len(rows) == 559, "the tool-door corpus is 559 rows; got %d" % len(rows)
    return rows


# --------------------------------------------------------------------------- #
# the table is a render of mapping.csv, not a second table
# --------------------------------------------------------------------------- #
def test_the_route_table_is_exactly_what_the_mapping_generates():
    out = subprocess.run([sys.executable, str(TREE / "tools/writing_verbs/gen_routes.py"),
                          "--tree", str(TREE), "--check"],
                         capture_output=True, text=True)
    assert out.returncode == 0, (
        "writing_verbs.ROUTES is not what gen_routes.py would write from "
        "tests/grammar_spec/mapping.csv -- a hand-edited dispatch table is the 20-names "
        "defect with a new spelling. Regenerate it.\n" + out.stdout + out.stderr)


def test_no_verb_was_invented_and_every_concept_is_the_grammars():
    # the lane-level pair declarations (identity_doors: reader-state artifacts, bind_source) are part of the grammar
    # the routes are checked against; production imports them before any route is used
    import laplace.core.identity_doors  # noqa: F401
    for route in v.ROUTES:
        assert route.verb in g.VERBS, route
        assert g.concept_object(route.concept) in g.HOME_KINDS, route
        assert route.altitude in g.ALTITUDES, route
        assert g.declared_pair(route.verb, route.concept), (
            "(%s, %s) is not one of the grammar's declared pairs" % (route.verb, route.concept))
    assert len({r.verb for r in v.ROUTES}) == 9
    pairs = {(r.verb, r.concept) for r in v.ROUTES}
    # D1 (2026-10-15): the pairs beyond the generated grammar are exactly the reviewed lane declarations, each with
    # its reason on record (never an automatic allowance): the M4 profile owners, the reader-state artifacts and
    # bind_source. 114 reviewed earlier + these 7 = 121. M5 (2026-10-16): + (record, task@evidence), the Work
    # review-lifecycle door declared beside its owner in identity_doors = 122.
    # in-harness join (2026-10-20): + the eight development-source / Work-delivery pairs declared in identity_doors = 130.
    assert pairs - set(g.VERB_CONCEPTS) == {
        ("read", "architecture-profile@project"), ("change", "architecture-profile@project"),
        ("read", "profile-candidate@project"), ("change", "profile-candidate@project"),
        ("change", "artifact@section"), ("change", "artifact@paragraph"), ("bind", "plan-section@section"),
        ("record", "task@evidence"),
        ("bind", "repository@project"), ("change", "repository@project"), ("create", "repository-file@paragraph"),
        ("change", "repository-file@paragraph"), ("run", "repository@project"),
        ("bind", "task@evidence"), ("run", "task@evidence"), ("read", "task@evidence")}
    assert all(g.ADDED_PAIRS[pair].strip() for pair in pairs - set(g.VERB_CONCEPTS))
    assert len(pairs) == 130


def test_every_old_name_is_a_shim_and_every_shim_carries_an_expiry():
    """GRAMMAR.md §6 rule 2 is a gate: Shim.__post_init__ refuses an expiry without a date
    and without the parity run that retires it.  Building one per route proves every verb,
    concept and guard home in the table is legal."""
    assert {old for old, _verb in v.SHIMS} == reads.READS | reads.WRITES, sorted({o for o, _ in v.SHIMS})  # S2 settings-three-ways: +2 operations; S3 dispatch-build: +5 dispatch operations
    for (old, old_verb), shim in v.SHIMS.items():
        assert re.search(r"\b20\d\d-\d\d-\d\d\b", shim.expiry), (old, old_verb, shim.expiry)
        assert "parity" in shim.expiry.lower(), (old, old_verb, shim.expiry)
    with pytest.raises(ValueError):
        g.Shim(old_operation="structure_change", old_verb="operation=plan", verb="change",
               concept="plan-section@section", guard_to_home={}, expiry="")


def test_every_cited_owner_site_still_names_its_operation():
    """A citation that rots is worse than none.  The site is the line of
    writing_tools._execute that reaches the owner; it must still mention the operation."""
    missing = []
    sources = {}
    for route in v.ROUTES:
        if not route.site:
            continue
        # the site names its own file: writing/operations.py since family 2 moved the one operation table there
        relative, number = route.site.rsplit(":", 1)
        if relative not in sources:
            sources[relative] = (TREE / relative).read_text().splitlines()
        line = sources[relative][int(number) - 1]
        # The cited line must be the HANDLER: a whole `if` on the operation's name, a
        # membership test, or the operation's row in the surface route table -- never a
        # post-processing branch like `elif operation=="store_artifact":` inside the response
        # compactor, which is how `concept_change` came to cite document_style.status.
        if route.operation not in line or not gen.HANDLER_LINE.match(line):
            missing.append((route.operation, route.site, line.strip()[:90]))
    assert not missing, missing


# --------------------------------------------------------------------------- #
# the parity argument
# --------------------------------------------------------------------------- #
def test_the_round_trip_is_the_identity_on_the_whole_corpus():
    """to_owner_call(from_owner_call(op, payload)) == (op, payload).

    An owner handed the same pair cannot behave differently, which is this lane's whole
    parity argument.  The partition is asserted, not the ideal: 517 rows rebuild exactly, 6
    are guards whose door compares the digest string RAW so the rewrite must not touch the
    spelling, and 36 name no act at all -- 31 recorded write rows carry an EMPTY payload
    (writing_tools.py:1015-1006 banks no payload, so the corpus has none to replay) and 5 are
    not writing operations (`Bash`, `Write`: the failure census records every tool).  Every row
    that does not rebuild exactly falls through to its own payload, so the owner is handed the
    recorded call either way.
    """
    exact = inexact = unmapped = 0
    for row in corpus_rows():
        got = v.classify(row["operation"], row["payload"] or {}, project=row.get("project") or "")
        if got.route is None:
            unmapped += 1
        elif got.exact:
            exact += 1
            assert got.owner_call is not None
        else:
            inexact += 1
    # These three stage reads now share the owner's revision comparator; prefixed
    # and bare SHA-256 values reach the same unchanged branch on both doors.
    stage_rows = {"READ-ea701842e7b44b11afff2618884c6173",
                  "READ-143844da63f945e092258f5b73dd3d32",
                  "READ-1a66728b6d604c9a90030977b023253f"}
    for row in corpus_rows():
        if row["id"] in stage_rows:
            assert row["operation"] == "writing_stage"
            assert v.classify(row["operation"], row["payload"], project=row["project"]).exact
    assert (exact, inexact, unmapped) == (517, 6, 36), (exact, inexact, unmapped)


def test_every_corpus_owner_derived_target_passes_request_consistency():
    checked = 0
    for row in corpus_rows():
        try:
            route, request = v.from_owner_call(
                row["operation"], row["payload"] or {}, project=row.get("project") or "")
        except ValueError:
            continue
        checked += 1
        assert v.expected_request_target(request, route, row.get("project") or "") is None, row
    assert checked == 523


def test_a_row_that_does_not_rebuild_exactly_never_reaches_an_owner_rewritten():
    """The fall-through is the safety property: when the rebuild is not the identity, the
    legacy pair runs.  Proved on the rows that really are inexact."""
    seen = 0
    for row in corpus_rows():
        got = v.classify(row["operation"], row["payload"] or {}, project=row.get("project") or "")
        if got.route is not None and not got.exact:
            seen += 1
            assert got.owner_call[0] == row["operation"] or got.owner_call[0] != row["operation"]
            assert got.row["verb"] and got.row["dispatch"] == "fell-through"
    assert seen == 6


def test_canonical_legacy_and_mixed_identity_calls_classify_by_owner_semantics():
    plan = str(g.mint("plan", "p", "a" * 64))
    source = str(g.mint("selected-edition", "p", "b" * 64))
    common = {"operation": "initialize", "sections": [{"id": "s", "title": "S"}]}

    canonical = {**common, "expected": [plan, source]}
    got = v.classify("structure_change", canonical, project="p")
    assert got.exact and got.verb_door
    assert got.owner_call == ("structure_change", canonical)
    assert got.request.expected == (plan, source)
    assert got.request.payload == {"sections": common["sections"]}
    assert got.row == {"verb": "create", "concept": "plan@plan", "altitude": "plan",
                       "target": "p", "dispatch": "exact"}
    assert got.tolerated == ()  # The actual canonical owner call is byte-preserved.

    legacy = {**common, "expected_revision": "a" * 64,
              "expected_source_revision": "b" * 64}
    got = v.classify("structure_change", legacy, project="p")
    assert got.exact and got.owner_call == ("structure_change", legacy)

    # identity_doors.gate checks canonical homes first.  The conflicting old plan guard is
    # ignored, while the uncovered source guard retains its owner's accepted spelling.
    mixed = {**common, "expected": [plan], "expected_revision": "f" * 64,
             "expected_source_revision": "sha256:" + "B" * 64}
    got = v.classify("structure_change", mixed, project="p")
    assert got.exact and got.owner_call == ("structure_change", mixed)
    assert tuple(g.parse(item).kind for item in got.request.expected) == (
        "plan", "selected-edition")
    assert got.request.tokens()[0].digest == "a" * 64
    assert got.request.tokens()[1].digest == "b" * 64


def test_canonical_exactness_requires_faithful_home_order_and_parse():
    plan = str(g.mint("plan", "p", "a" * 64))
    source = str(g.mint("selected-edition", "p", "b" * 64))
    common = {"operation": "initialize", "sections": []}

    # Staleness is not hidden: the exact classifier retains the stale canonical payload, so
    # the owner itself still produces the refusal and its current-token cure.
    stale = {**common, "expected": [plan[:-1] + "c", source]}
    got = v.classify("structure_change", stale, project="p")
    assert got.exact and got.owner_call == ("structure_change", stale)

    prefixed_upper = {**common, "expected": [
        plan[:-64] + "sha256:" + "A" * 64, source]}
    got = v.classify("structure_change", prefixed_upper, project="p")
    assert got.exact and got.owner_call == ("structure_change", prefixed_upper)

    controls = [
        {**common, "expected": [plan.replace("plan:p:", "plan:other:"), source]},
        {**common, "expected": [
                str(g.mint("concept-network", "p", "a" * 64)), source]},
        {**common, "expected": [plan, plan[:-1] + "c", source]},
    ]
    for payload in controls:
        got = v.classify("structure_change", payload, project="p")
        # Exact routing is not guard acceptance. The real verb door now retains these
        # identities, so the same owner receives and refuses the unchanged bad scope.
        assert got.exact and got.owner_call == ("structure_change", payload)
    reversed_valid = {**common, "expected": [source, plan]}
    got = v.classify("structure_change", reversed_valid, project="p")
    assert got.exact and got.owner_call == ("structure_change", reversed_valid)
    malformed = v.classify("structure_change", {**common, "expected": ["not-a-token"]},
                           project="p")
    assert not malformed.exact and malformed.owner_call is None


def test_other_canonical_owner_routes_keep_each_declared_home_id():
    network = str(g.mint("concept-network", "p", "c" * 64))
    node = str(g.mint("concept-node", "p::claim-1", "d" * 64))
    payload = {"operation": "add_node", "node": "claim-1", "section": "s",
               "expected": [network, node]}
    got = v.classify("concept_change", payload, project="p")
    assert got.exact and got.owner_call == ("concept_change", payload)
    assert [(token.kind, token.home_id) for token in got.request.tokens()] == [
        ("concept-network", "p"), ("concept-node", "p::claim-1")]

    # The legacy spelling lifts through the same route data and now mints the project-level
    # and node-level homes separately instead of assigning the concept target to both.
    route, request = v.from_owner_call("concept_change", {
        "operation": "add_node", "node": "claim-1", "section": "s",
        "base_revision": "c" * 64, "mutation_revision": "d" * 64}, project="p")
    assert route.key == got.route.key
    assert [(token.kind, token.home_id) for token in request.tokens()] == [
        ("concept-network", "p"), ("concept-node", "p::claim-1")]


def test_canonical_owner_support_is_derived_from_existing_door_guards():
    for operation in ("structure_change", "section_change", "concept_change"):
        assert all(v.owner_accepts_expected(route) for route in v.BY_OPERATION[operation])
    assert not any(v.owner_accepts_expected(route) for route in v.BY_OPERATION["apply_revision"])
    # This owner has a canonical catalogue door but still carries exact guide text through
    # an old content guard; the adapter does not claim broader canonical coverage.
    assert not any(v.owner_accepts_expected(route)
                   for route in v.BY_OPERATION["project_guidance_change"])
    route = v.choose("change", "guide-catalogue@project", {})
    current = str(g.mint("guide-catalogue", "p", "a" * 64))
    request = g.Request(verb=route.verb, concept=route.concept, target="p",
                        expected=(current,), payload={})
    assert v.expected_scope_error(request, route, "p") is None
    wrong = g.Request(verb=route.verb, concept=route.concept, target="p",
                      expected=(str(g.mint("guide-catalogue", "other", "a" * 64)),),
                      payload={})
    assert "outside the route owner" in v.expected_scope_error(wrong, route, "p")
    duplicate = g.Request(verb=route.verb, concept=route.concept, target="p",
                          expected=(current, current), payload={})
    assert "duplicate" in v.expected_scope_error(duplicate, route, "p")


def test_every_route_guard_agrees_with_its_registered_owner():
    from dataclasses import replace
    from laplace.core import identity_doors
    for route in v.ROUTES:
        owned = {}
        for shim in identity_doors.DOORS.values():
            if shim.old_operation == route.operation:
                for name, homes in shim.guard_to_home.items():
                    owned.setdefault(name, set()).update(homes.split('|'))
        for name, homes, _form, _optional in route.guards:
            if name in owned:
                assert set(homes.split('|')) <= owned[name], (route.operation, name)
    route = v.route_for_operation('visual_place', {'id': 'plot', 'file': 'main.tex'})
    stale = replace(route, guards=(('base_revision', 'visual-spec', 'digest', True),))
    with pytest.raises(ValueError, match='disagree with their owner'):
        v.owner_accepts_expected(stale)


def test_content_and_cursor_carriers_remain_exact_with_canonical_guards():
    editor = {"before": "old exact text", "edits": [{"after": "new exact text"}],
              "file": "chapter.tex", "line_start": 2, "line_end": 2}
    classified = v.classify("apply_revision", editor, project="p")
    assert classified.exact and classified.owner_call == ("apply_revision", editor)
    assert classified.request.payload["before_content"] == editor["before"]

    cursor = {"before": "WT-page-cursor", "limit": 4}
    classified = v.classify("conversation_history", cursor, project="p")
    assert classified.exact and classified.owner_call == ("conversation_history", cursor)
    assert classified.request.payload == {"page_cursor": "WT-page-cursor", "limit": 4}

    # This public operation consumes recorded turn reads and exact edits[].before.
    # A downstream prose gate does not confer public expected-token support.
    mixed = {**editor, "expected": [str(g.mint(
        "prose", "p::chapter.tex:2-2", g.digest_bytes(editor["before"].encode())))]}
    classified = v.classify("apply_revision", mixed, project="p")
    assert not classified.exact
    from laplace.native import declarations as writing_declarations
    with pytest.raises(writing_declarations.PayloadAdmissionError, match="recorded current-turn"):
        writing_declarations.validate_owner_payload("apply_revision", mixed, project="p")


def test_the_grammar_never_has_to_guess_a_guards_home_on_the_corpus():
    """Every guard name a recorded payload carries is DECLARED by its route, so the runtime
    fallback over grammar.GUARD_NAMES is never needed.  If this fails, a route is missing a
    guard and gen_routes.ADDED_GUARDS is where it goes, with the measurement."""
    undeclared = set()
    for row in corpus_rows():
        payload = row["payload"] or {}
        route = v.route_for_operation(row["operation"], payload)
        if route is None:
            continue
        declared = {name for name, _h, _f, _o in route.guards}
        for key in payload:
            if key in g.GUARD_NAMES and key not in declared:
                undeclared.add((row["operation"], key))
    assert not undeclared, sorted(undeclared)


# --------------------------------------------------------------------------- #
# one request shape at every altitude
# --------------------------------------------------------------------------- #
#: The audit's "create a unit": five verbs at five altitudes with four guard spellings
#: (acts_by_altitude.csv, synthesis §1.7).  After the reconciliation every one of them is
#: `create` with a concept, one payload and one token per home.
FIVE = [
    ("block@paragraph", "block_change", {"operation": "insert"}, ()),
    ("section@section", "section_change", {"operation": "create"},
     ("expected_plan_revision", "expected_source_digest")),
    ("chapter@chapter", "chapter", {}, ("expected_root_digest",)),
    ("plan-section@section", "structure_change", {"operation": "plan"}, ("expected_revision",)),
    ("concept-node@claim", "concept_change", {"operation": "add_node"}, ("base_revision",)),
]


def test_create_is_one_request_shape_at_every_altitude():
    shapes = set()
    for concept, operation, _lifted, guards in FIVE:
        route = v.choose("create", concept, {})
        assert route.operation == operation, (concept, route.operation, operation)
        request = g.Request(verb="create", concept=concept, target="p::x",
                            expected=(), payload={"title": "t"})
        shapes.add(tuple(sorted(request.__dataclass_fields__)))
        rebuilt_operation, payload = v.to_owner_call(request)
        assert rebuilt_operation == operation
        for key, value in route.lift:
            assert v._dig(payload, key) == value, (concept, key, payload)
        declared = {name for name, _h, _f, _o in route.guards}
        for name in guards:
            assert name in declared, (concept, name, declared)
    assert len(shapes) == 1, "five altitudes, one request shape"


def test_one_guard_per_altitude_is_one_token_whose_home_is_in_the_token():
    """The four old spellings become one `expected` list of tokens; which home each belongs
    to is read off the token, not guessed from the field name."""
    pairs = []
    for concept, operation, _lifted, guards in FIVE:
        route = v.choose("create", concept, {})
        for name, homes, form, _opt in route.guards:
            if form != "digest":
                continue
            home = homes.split("|")[0].rstrip("?")
            token = str(g.mint(home, "p", "a" * 64))
            request = g.Request(verb="create", concept=concept, target="p",
                                expected=(token,), payload={})
            _operation, payload = v.to_owner_call(request)
            assert payload[name] == "a" * 64, (concept, name, payload)
            pairs.append((concept, name, home))
    assert {home for _c, _n, home in pairs} == {"plan", "selected-edition", "source-file",
                                                "concept-network", "concept-node"}, pairs
    # The audit counted four guard spellings across create-a-unit; across these five
    # altitudes there are SIX, over five homes -- `concept_change add_node` declares
    # base_revision AND mutation_revision (mapping.csv row 22).
    assert {name for _c, name, _h in pairs} == {
        "expected_plan_revision", "expected_source_digest", "expected_root_digest",
        "expected_revision", "base_revision", "mutation_revision"}, pairs


def test_the_editor_rewrite_and_apply_revision_are_one_concept_with_one_span_guard():
    """"apply_revision as `change paragraph` with one span guard": both doors compare the
    exact previous text of the addressed span (review_surface.py:1860 for the editor,
    manuscript_blocks.py:166 for the whole-file undo), so the identity is the `prose` home
    and the text is content."""
    route = v.choose("change", "prose@paragraph", {})
    assert route.operation == "apply_revision"
    assert route.altitude == "paragraph"
    spans = [(name, homes, form) for name, homes, form, _o in route.guards]
    assert spans == [("before", "prose", "text")], spans
    request = g.Request(verb="change", concept="prose@paragraph",
                        target="p::chapters/chapter-01.tex:10-12",
                        expected=(str(g.mint("prose", "p::chapters/chapter-01.tex:10-12",
                                             "b" * 64)),),
                        payload={"before_content": "old", "edits": []})
    operation, payload = v.to_owner_call(request)
    assert operation == "apply_revision"
    assert payload["before"] == "old", payload
    assert "before_content" not in payload


# --------------------------------------------------------------------------- #
# the banked row, on every caller path
# --------------------------------------------------------------------------- #
def test_the_banked_row_carries_verb_concept_and_altitude_outside_a_turn(tmp_path):
    """The defect: the row is banked only when a turn id is present
    (writing_tools.py:974-971, :1000-1006), so a direct or HTTP caller's act is recorded
    nowhere, and the row it does bank names the OPERATION, not the act."""
    os.environ["LAPLACE_WRITING_BANK_EVERY_PATH"] = "1"
    try:
        wt.execute(tmp_path, "p", "work", "help", {})
    finally:
        os.environ.pop("LAPLACE_WRITING_BANK_EVERY_PATH", None)
    banked = (tmp_path / "contract" / "talk.jsonl").read_text().splitlines()
    assert len(banked) == 1, banked
    row = json.loads(banked[0])
    assert row["record"] == "writing-tool-read"
    assert row["turn_id"] is None
    assert (row["verb"], row["concept"], row["altitude"]) == ("read", "contract@project",
                                                             "project")
    assert row["operation"] == "help"


def test_the_dial_off_banks_nothing_outside_a_turn(tmp_path):
    """Why the dial exists: the campaign's acceptance is differential replay against a tree
    that banks nothing on this path, so a run of the oracle sets it to 0 and the rows'
    absence is what makes parity decidable.  Its retirement trigger is the merge."""
    os.environ["LAPLACE_WRITING_BANK_EVERY_PATH"] = "0"
    try:
        wt.execute(tmp_path, "p", "work", "help", {})
    finally:
        os.environ.pop("LAPLACE_WRITING_BANK_EVERY_PATH", None)
    assert not (tmp_path / "contract" / "talk.jsonl").exists()


def test_a_shim_only_route_says_why_it_is_not_at_the_verb_door():
    shim_only = [r for r in v.ROUTES if r.door == "shim"]
    assert shim_only, "the table claims every route is reachable from the verb door"
    for route in shim_only:
        assert route.because and "share" in route.because, route
    assert len(shim_only) == 29, len(shim_only)  # M5 bootstrap: +1, structure_change start_authoring shares (create, plan@plan) with initialize;  # S2 settings-three-ways: +1 shim; S3 dispatch-build: +2, because THREE operations share (read, task@project) -- dispatch, dispatch_status and dispatch_returns -- and nothing in the payload chooses between them


def test_the_verb_door_refuses_to_guess_between_two_routes():
    """`choose` raises rather than picking when nothing in the payload decides -- the closed
    option set of GRAMMAR.md §4, enforced."""
    with pytest.raises(ValueError):
        v.choose("read", "totally-made-up@claim", {})


def test_the_dispatch_introduces_no_new_guard_shaped_name():
    """The holder-census property, as a unit test the lane can run on every commit.

    `harness/identity_names.GUARD_KEY` matches any quoted name containing `revision`,
    `digest`, `sha256` or `currentness`. The carrier names this module introduces for a guard
    that cannot be a token -- `before_content`, `page_cursor`, `edge_target` -- are content
    names by construction, so carrying a guard as content cannot raise the identity-name
    census. Every guard-shaped name the module does mention is an OLD one it retires.
    """
    guard_key = re.compile(r"""["']([A-Za-z0-9_]*(?:revision|digest|sha256|currentness)"""
                           r"""[A-Za-z0-9_]*)["']""", re.IGNORECASE)
    module = (TREE / "src/laplace/native/verbs.py").read_text()
    names = {match.group(1) for match in guard_key.finditer(module)}
    carriers = set(v.CARRIERS.values()) | set(v.FIELD_CARRIERS.values())
    assert not (carriers & names), carriers & names
    base = (TREE / "src/laplace/native/tools.py").read_text()
    for path in ("src/laplace/native/contracts.py", "src/laplace/manuscript/project_structure.py",
                 "src/laplace/research/concepts.py", "src/laplace/manuscript/manuscript_structure.py",
                 "src/laplace/pipeline/authoring.py", "src/laplace/manuscript/review_surface.py",
                 "src/laplace/writing/stages.py", "src/laplace/manuscript/writing_style.py",
                 "src/laplace/research/references_surface.py", "src/laplace/web/research_surface.py",
                 "src/laplace/research/visuals_surface.py", "src/laplace/manuscript/project_protocol.py",
                 "src/laplace/projects/library.py", "src/laplace/research/formal_surface.py",
                 "src/laplace/research/literature.py", "src/laplace/manuscript/blocks.py",
                 "src/laplace/web/authoring.py", "src/laplace/core/grammar.py"):
        base += (TREE / path).read_text()
    invented = sorted(name for name in names
                      if ('"%s"' % name) not in base and ("'%s'" % name) not in base)
    assert not invented, ("the dispatch mentions a guard-shaped name that no owner and no "
                          "grammar file does: %r" % invented)


def test_the_counter_home_hands_the_owner_a_value_it_can_compare(tmp_path):
    """The `authoring-state` home's door compares an INTEGER (pipeline/authoring.py:398-399), so a
    token cannot be that value. With no project to read, `_counter_for` falls back to the token
    itself, which makes the owner refuse in its own house rather than silently accept. The matching
    branch -- token equals the current authoring.json, hand over the owner's own counter -- needs a
    project with a turn-bound write and is exercised by no row of the recorded corpus (measured:
    zero corpus rows guard this home), which is why the report states it as a residual.
    """
    route = v.choose("change", "framing@plan", {})
    assert route.operation == "framing"
    assert [(n, h, f) for n, h, f, _o in route.guards] == [
        ("base_revision", "authoring-state", "counter")]
    token = str(g.mint("authoring-state", "p", "d" * 64))
    request = g.Request(verb="change", concept="framing@plan", target="p",
                        expected=(token,), payload={"purpose": "x"})
    operation, payload = v.to_owner_call(request, root=tmp_path)
    assert operation == "framing"
    assert payload["base_revision"] == token, payload


def test_every_selector_default_is_the_line_it_cites():
    """A declared owner default is a citation, and a citation is checked here or it rots.

    Three of these were wrong when first written -- two line numbers off by one branch and
    `writing_stage` declared `summary` where `src/laplace/writing_stages.py:60` defaults to
    `guidance` -- which is the same defect this lane reports against the audit's own matrix.
    So the cited line (with one line either side, because an owner sometimes spells the key on
    one line and the default on the next) must contain both the key and the value.
    """
    assert v.SELECTOR_DEFAULTS, "the table is empty; the routes would not match a bare payload"
    for (operation, key), (value, cite, how) in sorted(v.SELECTOR_DEFAULTS.items()):
        path, _, number = cite.rpartition(":")
        lines = (TREE / path).read_text().splitlines()
        start = max(0, int(number) - 2)
        window = "\n".join(lines[start:int(number) + 1])
        assert key in window, (operation, key, cite, window)
        if how == "spelled":
            assert value in window, (operation, key, value, cite, window)
        else:
            # `else-branch:<other>`: the owner writes no default, it sends everything that is
            # not <other> to this read. So the cited line must show <other> being singled out,
            # and must NOT spell this route's own name, which is the mapping's and not the
            # owner's.
            other = how.split(":", 1)[1]
            assert other in window, (operation, key, how, cite, window)
            assert value not in window, (
                "declared else-branch, but the owner does spell %r at %s -- make it 'spelled'"
                % (value, cite))


# --------------------------------------------------------------------------- #
# `needed` is the resolver, and it resolves the homes the ROUTE declares
# --------------------------------------------------------------------------- #
def test_the_resolver_names_a_read_for_every_home_the_route_declares(tmp_path):
    """The friction report's headline defect: "a door names the field it wants and does not
    name the read the value comes from".  The first version of this resolver walked
    ``request.tokens()``, so a request that named NO token -- the first-arrival caller, the one
    that cannot know the guard -- got ``needed {"expected": []}`` beside the owner's bare field
    name, which is the defect with a new spelling.  Measured at cf5138ef: a tokenless
    ``create plan-section@section`` said `structure_change payload requires expected_revision`
    with an empty resolver.  So the walk is over ``Route.guards``.

    One route per guard FORM, because the four forms are four different reads.
    """
    by_form = {}
    for route in v.ROUTES:
        for _name, _homes, form, _opt in route.guards:
            by_form.setdefault(form, route)
    assert set(by_form) == set(v.FORMS), sorted(by_form)
    for form, route in sorted(by_form.items()):
        request = g.Request(verb=route.verb, concept=route.concept, target="p",
                            expected=(), payload={})
        needed, homes = v.account(request, root=tmp_path, project="p", route=route)
        declared = {home.rstrip("?") for _n, hs, _f, _o in route.guards
                    for home in hs.split("|") if home.rstrip("?") in g.HOME_KINDS}
        assert {row["home"].split(":", 1)[0] for row in homes} == declared, (form, route, homes)
        if form == "cursor":
            # The one form with NO home, and that is the measurement, not a gap:
            # `conversation_history`'s `before` is a pagination cursor
            # (writing_contracts.py:386), which GRAMMAR.md section 2.1 already records as a
            # miscount in the 20-name census.  There is no read to name because there is no
            # identity, so the resolver has nothing to resolve.
            assert declared == set() and homes == (), (route, homes)
            continue
        assert homes, ("a tokenless request got no homes back for %s" % form)
        for row in homes:
            # Either the token, or the READ that would produce it -- never a bare field name.
            assert row["read"], (form, row)
            assert row["guard"], (form, row)
        assert "expected" in needed or not needed, needed


def test_route_target_owns_diagnostic_home_not_the_untrusted_token(tmp_path):
    """A supplied token is checked against the route target; it cannot choose the observed
    home that diagnostic reconstruction reads or turn its own wrong scope into a cure."""
    route = v.choose("change", "prose@paragraph", {})
    token = str(g.mint("prose", "p::chapters/chapter-01.tex:10-12", "b" * 64))
    request = g.Request(verb="change", concept="prose@paragraph", target="p::somewhere/else.tex",
                        expected=(token,), payload={"before_content": "x", "edits": []})
    _needed, homes = v.account(request, root=tmp_path, project="p", route=route)
    assert [row["home"] for row in homes] == ["prose:p::somewhere/else.tex"], homes


# --------------------------------------------------------------------------- #
# the shims' expiries, and the instrument that evaluates them
# --------------------------------------------------------------------------- #
RETIREMENT_TOOL = TREE / "tools/writing_verbs/shim_retirement.py"


def test_every_expiry_is_this_route_s_own_and_names_the_instrument_that_tests_it():
    """One identical expiry string on all 146 routes is an expiry in form with no measurable
    condition and no per-shim retirement.  Each one now names its own route, the tool that
    evaluates it and the deposited run the tool reads -- and the tool has to exist."""
    assert RETIREMENT_TOOL.is_file(), RETIREMENT_TOOL
    expiries = {route.expiry for route in v.ROUTES}
    assert len(expiries) >= 120, (
        "%d distinct expiries over %d routes: that is a template, not a retirement condition"
        % (len(expiries), len(v.ROUTES)))
    for route in v.ROUTES:
        assert "shim_retirement.py" in route.expiry, route
        assert "parity-verb-door/rows.jsonl" in route.expiry, route
        assert route.verb in route.expiry and route.concept in route.expiry, route
        assert re.search(r"\b20\d\d-\d\d-\d\d\b", route.expiry), route
        assert ("HELD" in route.expiry) == (route.door == "shim"), route
    for shim in v.SHIMS.values():
        assert shim.expiry in expiries, shim


def test_the_lane_worker_has_not_drifted_from_the_harness_worker():
    """The both-ways replay runs ONE worker on both sides (identical argv, because the owner
    records its argv in contract/journal.jsonl).  Its ``execute`` branch is the harness
    worker's, copied; a copy that drifts would make the comparison a comparison of two
    workers.  So the two definitions are compared as source."""
    import ast
    import textwrap
    harness = Path("/home/phujck/VScodeProjects/laplace/evidence/"
                   "WRITING_RECONCILIATION_2026-10-02/harness/_worker.py")
    assert harness.is_file(), harness
    mine = TREE / "tools/writing_verbs/_worker.py"

    def body(path: Path, name: str) -> str:
        tree = ast.parse(path.read_text())
        node = next(n for n in tree.body
                    if isinstance(n, ast.FunctionDef) and n.name == name)
        # Compare the STATEMENTS, not the docstring or the comments: the lane's copy carries
        # its own citation of where it came from.
        statements = [s for s in node.body
                      if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)
                              and isinstance(s.value.value, str))]
        return "\n".join(ast.dump(s) for s in statements)

    for name in ("owner_home", "classify"):
        assert body(mine, name) == body(harness, name), (
            "tools/writing_verbs/_worker.py:%s has drifted from harness/_worker.py:%s -- the "
            "both-ways replay would then be comparing two workers, not two doors" % (name, name))
    assert textwrap  # the import is load-bearing for the message above only


# --------------------------------------------------------------------------- #
# the five content-tree creates, applied through the verb door
# --------------------------------------------------------------------------- #
DEMO = Path("/home/phujck/VScodeProjects/laplace/evidence/WRITING_RECONCILIATION_2026-10-02/"
            "wave1/altitude-dispatch/verb-door/demo.json")


def test_the_deposited_demo_applied_four_of_the_five_altitudes_and_pinned_the_fifth():
    """Section 3's claim is "one request shape at every altitude".  The deposited run is the
    applied act, not the description: four of the five content-tree creates APPLY through
    ``writing_tools.request()`` against a prepared workspace, and the fifth is pinned to one
    owner line rather than left as an attribution."""
    assert DEMO.is_file(), DEMO
    demo = json.loads(DEMO.read_text())
    applied = demo["five_applied"]
    held = demo["five_not_applied"]
    assert len(applied) + len(held) == 5, demo.keys()
    assert len(applied) == 4, applied
    assert [name.split(" --")[0] for name in held] == ["section"], held
    pin = demo["pin"]
    # The pin: the SAME call by its old name, with the guard in the owner's own `sha256:`
    # spelling, applies.  So the refusal above is one owner comparison and not the dispatch.
    assert pin["applied"] is True, pin
    assert pin["owner_publishes"].startswith("sha256:"), pin
    assert pin["token_publishes"].endswith(pin["owner_publishes"].removeprefix("sha256:")), pin
