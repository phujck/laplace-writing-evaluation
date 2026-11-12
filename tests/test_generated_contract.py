"""The contract is emitted by the check, and these are the checks.

Six properties, each one a thing that was a sentence in the old contract:

1. Every deployed operation is declared, exactly once, and the declaration names a
   line in `src/laplace/writing/operations.py` (the one operation table) that still routes it.
2. No precondition the audit found stated is lost: every clause of every string in
   the base commit's contract table is carried by some rule, output, error or extra,
   or is listed as replaced-by-generation with its reason.
3. No literal example survives, and the generated example validates against the
   schema it is generated from, for all 73 operations and every variant.
4. `help` carries the live token of every home a door guards, or names the read
   that would obtain it.  No rule names a field without naming its home.
5. Contract views hold no stored entries; authored rules retain text and owner checks
   independently of length. Context size is measured separately.
6. The duplicate and the fallback are gone: `help {operation}` serves no
   `requested_payload_contract`, no `owner_contract`, and a bare `help` serves the
   generated index rather than the whole catalogue of summaries.
"""
from __future__ import annotations

import ast
import json
import re
import textwrap
from pathlib import Path

import jsonschema
import pytest

from laplace.core import grammar as g
from laplace.native import declarations as d
from laplace.native import tools as writing_tools
from laplace.writing import reads
from laplace.native.declarations import DECLARATIONS, HTTP_DECLARATIONS, clauses
from laplace.writing.schemas import SCHEMAS
from laplace.core import checkout

TREE = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).resolve().parent / "grammar_spec" / "head_contract_prose.json"
DEPLOYED = sorted(reads.READS | reads.WRITES)


def served_input(action):
    """The input a served help names: inline, or (D2 help sections) its exact `input` section read."""
    if "input" in action:
        return action["input"]
    assert "input" in action["sections"]["chars"] and "input_summary" in action, "a moved input is named and summarised"
    return d.help_payload(action["operation"], permitted=action["permitted"], section="input")["value"]

#: The one thing the migration deleted instead of carrying, with the reason.  A
#: hand-written example is not a precondition: it is a value, and two of them named
#: objects that exist in no project (`"id": "REQUEST-example"` in task_status,
#: `"expected_source_digest": "sha256:current"` in section_change).  They are replaced
#: by `writing_declarations.generated_example`, whose output test 3 validates.
REPLACED_BY_GENERATION = ("example", "examples")


def head_contracts() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["contracts"]


#: Operations declared AFTER the fixture's own base commit (``payload["base"]``), so they
#: have no entry in the old hand-written contract table to have migrated from -- adding one
#: to the fixture would claim it existed at that historical commit, which is false.  Added by
#: S2 settings-three-ways (2026-10-05): the tool door's own settings read/change, the same
#: act the HTTP settings door already made, declared straight (no migration, nothing to
#: carry from a legacy contract string).
# S3 dispatch-build (2026-10-06): the five in-app dispatch operations, declared straight for
# the same reason -- the fixture's base commit had no dispatch door to migrate a contract from.
POST_MIGRATION_OPERATIONS = ("app_settings", "material_references", "material_reference_change", "session_settings", "session_settings_change",
                             "dispatch_plan", "dispatch", "dispatch_launch", "dispatch_continue",
                             "dispatch_status", "dispatch_returns", "storage", "storage_prune", "materials",
                             # the architecture/voice profile owners (laplace.manuscript.profiles), declared straight:
                             # the base commit had no profile door
                             "profile", "profile_change",
                             # M5 (2026-10-16): the Work review lifecycle (project_work_review); the base had no phase door
                             "work_review",
                             # in-harness join (2026-10-20): the development-source grant and the Work recipient delivery
                             "development_source", "work_delivery", "workflow_definition_change")


# ---------------------------------------------------------------------------
# 1. every operation declared, once, beside a handler that still routes it
# ---------------------------------------------------------------------------
def test_every_deployed_operation_is_declared_exactly_once():
    assert sorted(DECLARATIONS) == DEPLOYED
    # S2 settings-three-ways (2026-10-05): 73 migrated + 2 (session_settings,
    # session_settings_change) -- the tool door's own settings verb, declared the same way,
    # with no legacy contract to migrate (they postdate head_contracts()'s base commit).
    # S3 dispatch-build (2026-10-06): + the five dispatch operations, for the same reason.
    # M5 (2026-10-16): + work_review, the Work review-lifecycle door (project_work_review), for the same reason.
    # in-harness join (2026-10-20): + development_source and work_delivery, declared the same way (no legacy contract).
    assert len(DECLARATIONS) == 93  # Includes explicit failed-review continuation through its existing owner.


def test_a_second_declaration_of_one_operation_is_refused():
    with pytest.raises(ValueError, match="already declared"):
        d.declare("source", payload={})


def test_a_declaration_may_not_state_the_act_the_route_table_states():
    """The one table, as a refusal and not a convention.

    `verb`, `concept`, `also` and `handler` are read from `writing_verbs` --- the generated
    route table --- so a declaration that states one is refused BY NAME.  Before this
    synthesis both tables carried all four and agreed; the merge made them disagree inside
    one commit (`structure_change`: route `writing_tools.py:408`, declaration `:423`).
    """
    for key, value in (("verb", "read"), ("concept", "prose@paragraph"),
                       ("also", (("read", "prose@paragraph"),)),
                       ("handler", "src/laplace/writing/operations.py:1")):
        with pytest.raises(ValueError, match="a declaration does not state"):
            d.declare("not_a_real_operation", payload={}, **{key: value})


def test_every_declaration_names_a_line_that_still_routes_its_operation():
    """The declaration's `handler` is checked against the dispatch, not trusted.

    "Beside its handler" cannot mean physical adjacency in a dispatch that is one
    900-line chain, so it means this: the declaration cites the line, and the line
    must still mention the operation.  `writing_tools.py` is read as text and the
    cited line must contain the operation's own name.
    """
    lines = (TREE / "src/laplace/writing/operations.py").read_text(encoding="utf-8").splitlines()
    wrong = []
    for operation, declaration in sorted(DECLARATIONS.items()):
        assert declaration.handler, operation
        path, _, number = declaration.handler.rpartition(":")
        assert path == "src/laplace/writing/operations.py", (operation, declaration.handler)
        line = lines[int(number) - 1]
        if operation not in line:
            wrong.append((operation, declaration.handler, line.strip()[:90]))
    assert not wrong, "declaration cites a line that no longer routes it: %r" % (wrong,)


def test_a_handler_cannot_be_typed_and_a_bad_anchor_is_refused():
    """The handler is RESOLVED from the door's own text, so there is no typed line to be
    wrong.  Three gates, all measured on this merge: a declaration cannot carry a typed
    `handler` at all (33 of the 73 typed ones were wrong or stale once two lanes had
    edited `writing_tools.py`); an anchor that is not `<path>:<text>` is refused; and an
    anchor that matches more than one line is refused --- which actually fired, on
    `scanner.py`'s header prefix test, a line that occurs twice.  A fourth: an
    operation the door does not dispatch has no handler to resolve.  The whole-system
    merge took `verb` and `concept` out of the dataclass too --- they are read through
    the route table on every access (`Declaration.acts`, and `.verb`/`.concept` off it)
    --- so these
    probes name a real operation and pass neither."""
    with pytest.raises(TypeError):
        d.Declaration(operation="x", payload={},
                      handler="src/laplace/writing/operations.py:1")
    with pytest.raises(ValueError, match="handler_anchor is"):
        d.Declaration(operation="section_change", payload={},
                      handler_anchor="writing_tools.py")
    with pytest.raises(ValueError, match="occurs 0 times"):
        d.Declaration(operation="section_change", payload={},
                      handler_anchor="src/laplace/writing/operations.py:no such line anywhere")
    with pytest.raises(ValueError, match="nothing in src/laplace/writing/operations.py "
                                         "dispatches it"):
        d.dispatch_site("no_such_operation")


def test_the_two_handler_resolvers_agree():
    """Two syntheses, two ways to find the line that runs an operation, one answer.

    The contract x dispatch branch generated a `site` column into the route table
    (`writing_verbs.site_for`); the identity x contract branch read the door's own text
    (`writing_declarations.dispatch_site`).  The merge kept ONE as `Declaration.handler` --- the
    text reader, because it is the only one that answers for the HTTP declarations too --- and
    this proof is what stops the other from drifting away unnoticed while nothing imports it.
    """
    from laplace.native import verbs as writing_verbs
    disagree = []
    for operation in sorted(DECLARATIONS):
        try:
            table = writing_verbs.site_for(operation)
        except ValueError:
            continue                      # no row with a site: the table is silent, not wrong
        text = d.dispatch_site(operation)
        if table != text:
            disagree.append((operation, table, text))
    assert not disagree, (
        "the route table and the door's own text name different dispatch lines: %r" % (disagree,))


def test_every_resolved_handler_is_a_dispatch_and_not_a_guard():
    """The round-2 judgement's deficiency 2: ten declarations cited
    `writing_tools.py:213`, the unknown-KEY validation set, and the gate could not catch it
    because it only asked that the operation's NAME appear in the cited line.  Now the line
    is resolved, and a validation set cannot be the answer: the resolved line must compare
    the operation or route it."""
    text = (TREE / "src/laplace/writing/operations.py").read_text(encoding="utf-8").split("\n")
    guards = {number for number, line in enumerate(text, 1)
              if "set(payload)" in line or "CONTRACTS[operation]" in line}
    bad = []
    for operation, declaration in sorted(DECLARATIONS.items()):
        path, _, number = declaration.handler.rpartition(":")
        assert path == "src/laplace/writing/operations.py", (operation, declaration.handler)
        line = text[int(number) - 1]
        dispatches = (("operation ==" in line or "operation==" in line
                       or "operation in {" in line or '": (' in line)
                      and operation in line)
        if int(number) in guards or not dispatches:
            bad.append((operation, declaration.handler, line.strip()[:90]))
    assert not bad, "a handler resolved to something that is not a dispatch: %r" % (bad,)


# ---------------------------------------------------------------------------
# 1b. an identity rule is a MEASUREMENT, not a keyword match
# ---------------------------------------------------------------------------
# An identity rule is attributed three ways, in this order, and nothing else passes:
#
#   1. the audit's verb matrix gives that (operation, field) pair that home;
#   2. the GRAMMAR's home declares the guard AND cites the door that compares it --- the
#      same disjunction `test_grammar.py::test_every_declared_guard_names_the_door_that_
#      compares_it` uses, which covers `apply_revision before -> prose` (the matrix records
#      apply_revision with no guard at all, mapping.csv rows 1-2) and
#      `block_change expected_source_digest -> block` (the matrix attributes that name to
#      `source-file`, the whole file, while the `block` home declares it with its own doors;
#      a block operation guards the BLOCK's bytes, and the matrix row is the one that
#      should move);
#   3. one of the TWO pairs below, which are the grammar's own gap, each with the line that
#      compares it, so a lane cannot invent a home by adding a sentence.
GRAMMAR_OWES_A_ROW = {
    ("visual_place", "expected_source_revision"): (
        "selected-edition", "src/laplace/visuals_surface.py:349",
        "the matrix has no guard for visual_place (mapping.csv rows 142-143 carry `-`), and "
        "`selected-edition` declares the name but cites no door for it; GRAMMAR.md section "
        "2.1 names this line and project_structure.py:777 in prose as the two doors that "
        "compare it, so the home owes a `guard_doors` entry"),
    ("visual_place", "base_revision"): (
        "source-file", "src/laplace/visuals_surface.py:376",
        "the grammar gives `base_revision` to `authoring-state` and `concept-network` only, "
        "and `source-file` is not asked for under that name anywhere in section 2. Measured "
        "here: visuals_surface.py:342 calls it 'the exact selected file digest' and :376 "
        "reads it off the payload, so the TARGET FILE's bytes are what this door compares"),
}


def _audited_guard_homes():
    """(operation, guard) -> {home}, from the installed mapping: the campaign's row source."""
    import csv as _csv
    out = {}
    with (TREE / "tests/grammar_spec/mapping.csv").open(encoding="utf-8-sig") as handle:
        for row in _csv.DictReader(handle):
            operation = str(row.get("operation") or "").split()[0]
            guards = [n for n in str(row.get("old_guards") or "").split("/")
                      if n and n != "-"]
            homes = [h for h in str(row.get("homes") or "").split("/") if h and h != "-"]
            for guard, home in zip(guards, homes):
                for one in home.rstrip("?").split("|"):
                    one = one.strip().rstrip("?")
                    if one and not one.startswith("NONE"):
                        out.setdefault((operation, guard), set()).add(one)
    return out


def test_every_identity_rule_is_a_guard_this_door_really_compares():
    """The migration assigned a home by KEYWORD, and the synthesis measured the cost.

    Every precondition clause containing the English word "before" became
    `Rule('identity', field='before', home='source-file')` and every clause containing
    "revision" became `field='revision', home='authoring-state'`.  Twenty rules, including
    `visual_place`'s "omitted means before \\end{document}" --- rendered to a caller as an
    identity guard served by `source {files:[path]} -> sources[0].sha256`.  That is a field
    named with the WRONG home, which is the defect this whole campaign exists to end, in
    the cure's own output.

    So an identity rule now has to be attributed: the audit's verb matrix gives that
    (operation, field) pair that home, or the pair is one of the three above with the line
    that compares it.  A sentence that merely contains the word is an `order`, `scope` or
    `shape` rule with no home and no invented citation.
    """
    audited = _audited_guard_homes()
    assert len(audited) > 20, len(audited)
    unattributed = []
    for operation, declaration in sorted(DECLARATIONS.items()):
        for rule in declaration.rules:
            if rule.kind != "identity":
                continue
            key = (operation, rule.field)
            if rule.home in audited.get(key, set()):
                continue
            home = g.HOME_KINDS[rule.home]
            cites = [door for door in home.guard_doors
                     if door.split("=", 1)[0] == rule.field]
            if rule.field in home.guards_today and cites:
                continue
            allowed = GRAMMAR_OWES_A_ROW.get(key)
            if allowed and allowed[0] == rule.home:
                continue
            unattributed.append((operation, rule.field, rule.home,
                                 sorted(audited.get(key, ())), rule.says[:60]))
    assert not unattributed, (
        "an identity rule claims a home nothing attributes to that door: %r" % (unattributed,))


def test_the_two_guards_the_grammar_owes_a_row_cite_a_door_that_compares_them():
    """The allowance is not a hole: each of the two names a line, and the line is read.

    Checked at the campaign base, because a lane may have CURED the hand comparison the
    citation names --- which is exactly what happened to `review_surface.py:1860`, whose
    `current != before` the identity lane replaced with `identity_doors.gate`.  The claim
    being checked is about the tree the citation is a coordinate in.
    """
    import subprocess
    for (operation, field), (home, door, why) in sorted(
            GRAMMAR_OWES_A_ROW.items()):
        assert home in g.HOME_KINDS, (operation, home)
        assert len(why) > 60, (operation, field)
        rel, _, number = door.rpartition(":")
        done = subprocess.run(["git", "-C", str(TREE), "show", "706a8204:%s" % rel],
                              capture_output=True)
        assert done.returncode == 0, (door, done.stderr[:200])
        lines = done.stdout.decode("utf-8", "replace").split("\n")
        window = "\n".join(lines[max(0, int(number) - 3):int(number) + 2])
        assert field in window or "!=" in window or "==" in window, (operation, field, window)


def test_the_two_lanes_agree_wherever_both_name_a_home():
    """One syntax, checked: the gate's shim table and the contract's rules are two
    renderings of one fact --- which door compares which field against which home --- and a
    synthesis that merged them without comparing them would ship both.

    Measured before the reconciliation: 16 pairs declared in both forms, 14 agreeing, and
    two disagreeing --- `section_change expected_plan_revision` (the shim carried
    `plan|plan-file`, the declaration carried `plan` alone, and the door accepts either) and
    `research_record expected_revision` (the declaration carried a second home, `plan`, from
    a keyword).  Both are cured; this is the check that keeps them cured.
    """
    from laplace.core import identity_doors
    doors = {}
    for key, shim in identity_doors.DOORS.items():
        for field, home in shim.guard_to_home.items():
            doors.setdefault((key.split()[0], field), set()).update(home.split("|"))
    rules = {}
    for operation, declaration in DECLARATIONS.items():
        for rule in declaration.rules:
            if rule.kind == "identity" and rule.home:
                rules.setdefault((operation, rule.field), set()).add(rule.home)
    shared = sorted(set(doors) & set(rules))
    assert len(shared) >= 16, shared
    disagree = [(key, sorted(doors[key]), sorted(rules[key]))
                for key in shared if doors[key] != rules[key]]
    assert not disagree, (
        "the gate and the contract name different homes for the same guard: %r" % (disagree,))


# ---------------------------------------------------------------------------
# 2. no precondition is lost
# ---------------------------------------------------------------------------
def _carried_says(operation: str, section: str, index: int) -> list[str]:
    return [rule.says for rule in DECLARATIONS[operation].rules
            if tuple(rule.carries) == (operation, section, index)]


def test_the_pinned_fixture_is_the_base_commit_the_migration_read():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert re.fullmatch(r"[0-9a-f]{40}", payload["base"]), payload["base"]
    # Every operation the fixture's base commit held is still deployed and declared
    # (migration fidelity); DEPLOYED may ALSO hold operations the base commit never had --
    # POST_MIGRATION_OPERATIONS names them, each with its own carries-nothing declaration --
    # and the fixture must not be made to claim those existed back then.
    assert sorted(payload["contracts"]) == sorted(set(DEPLOYED) - set(POST_MIGRATION_OPERATIONS))
    assert set(POST_MIGRATION_OPERATIONS) <= set(DEPLOYED) - set(payload["contracts"])
    # each post-migration operation has its own current owner contract: a declaration, and its generated example
    # admitted by the composed owner schema that admission uses (not the raw declaration payload)
    from jsonschema import Draft202012Validator
    for operation in POST_MIGRATION_OPERATIONS:
        assert operation in d.DECLARATIONS, operation
        example = d.generated_example(operation)
        assert not list(Draft202012Validator(d.owner_input_schema(operation)).iter_errors(example)), (operation, example)


#: THE REVIEWED CARRY LEDGER (D1, 2026-10-15; readiness proved_causes.carry_differences). Every difference between the
#: pinned base contract table and the current declarations, named exactly with its replacement. A difference not in this
#: ledger, or a ledger row whose old or new text no longer matches, fails by name. Nothing here is a loose count.
REVIEWED_SUMMARY_CHANGES = {'author_history': ('Read bounded author comments/applied edits, or view=activity for who changed what and when '
                    'across the project.',
                    'Read bounded author comments/applied edits, project activity, or view=source for one exact '
                    'archived source through its historical owner.'),
 'build': ('Build the selected manuscript source with its configured TeX toolchain.',
           'Build the selected manuscript source or exact current derived build_target. action:cancel requires the '
           'exact returned build_job; it stops that job independently of later input/selection changes. Coalesced '
           'requests share one job. Cancelling blocks a new launch until cleanup; completion and cancellation '
           'serialize, and already-terminal cancellation is a no-op.'),
 'build_status': ('Read the selected manuscript build status and freshness.',
                  'Read the selected manuscript or issued derived build status, or build_job exact addressed '
                  'lifecycle independent of later plan/selection changes. running/cancelling remain active until the '
                  'worker/process tree is gone; cancelled and error are not fresh. Stale or missing job identities '
                  'refuse rather than adopting the newest job.'),
 'document': ('Read selected document build and presentation status.',
              'Read the selected document, exact editable source and dependency handles, template identity and '
              'current build without source bodies or history.'),
 'help': ('Read the exact contract for one deployed operation.',
          "Read the exact contract for one deployed operation; concept areas|journeys|controls reads the workspace's "
          'own help declarations (laplace.help-areas/1) that the human help layer renders.'),
 'project': ('Read project purpose, form, tasks and open work.',
             'Read shared bounded work summary, exact task diagnosis, declared campaign graph, genuine work '
             'namespaces or existing external workflows.'),
 'references': ('Search attached project references.',
                'Search the configured reference library metadata with a required nonempty q; use '
                "references_attached {} for this project's attached bibliography associations."),
 'references_attached': ("Read this project's attached bibliography associations.",
                         "Read this project's attached bibliography associations, or citekey to inspect its exact "
                         'selected bibliography entry. Entry metadata does not establish that the external source '
                         'was read.'),
 'section_change': ('Create, convert, undo, delete or restore a source heading and its reader-plan occurrence.',
                    'Create a new heading (optionally converting one whole prose paragraph), undo, delete or restore '
                    'a heading. To edit an existing heading title, read source then apply_revision.'),
 'structure': ('Read a compact reader-plan/logical-identity overview, or select exact sections/files/concepts for '
               'bounded dependencies, evidence and source correspondence.',
               'Read the actual source outline (view:outline), intended reader plan (view:summary) or selected '
               'bindings/support (view:detail). Argument/evidence uses logical_plan. Full alone supplies the '
               'composite plan-state mutation guard.'),
 'structure_change': ('Change canonical reader order through initialize, plan, spine, reconcile or bind_results.',
                      'Change reader-plan sections, narrative spine, authored reader transitions/paragraph plans, '
                      'exact source bindings or concept-result bindings through existing guarded owners. Read '
                      'selected detail and use its original edit_action; no ordinal ID inference or automatic review '
                      'acceptance.'),
 'style': ('Save document presentation settings and start a separate preview.',
           'Prepare exact saved-source or existing TeX-draft template candidate; use its returned build action and '
           'reviewed preview_ref before Apply. Recover only an addressed durable application/intent without '
           'replaying source.'),
 'task': ('Create one scoped project task.',
          'Create or guard an edit to one scoped project task; omitted semantics are preserved.'),
 'task_status': ('Update an existing project task.',
                 'Change exact work standing with consumed scope, standing and prerequisite acceptance guards.'),
 'visuals': ('Read visual specs, per-spec revisions, drawing freshness and separate evidence currentness.',
             'Read visual specs, per-spec revisions, drawing freshness and separate evidence currentness: {} is the '
             'whole catalogue, {view:index} the bounded identity list, {id} or {ids:[..8]} the exact figures.')}
REVIEWED_CLAUSE_REPLACEMENTS = {('author_history', 'preconditions:3', 'follow returned activity IDs with view record.'): 'Read one exact returned '
                                                                                          'activity ID for recorded '
                                                                                          'comparisons and current '
                                                                                          'hash identity checks.',
 ('export_pdf', 'preconditions:1', 'style-preview explicitly exports the current generated style preview'): 'style-preview '
                                                                                                            'export '
                                                                                                            'requires '
                                                                                                            'exact '
                                                                                                            'candidate_ref '
                                                                                                            'and '
                                                                                                            'reviewed '
                                                                                                            'preview_ref; '
                                                                                                            'no '
                                                                                                            'latest '
                                                                                                            'lookup',
 ('section_change', 'summary', 'Conversion uses an exact current paragraph and preserves its TeX.'): 'Conversion '
                                                                                                     'replaces one '
                                                                                                     'whole prose '
                                                                                                     'paragraph with '
                                                                                                     'a NEW heading '
                                                                                                     'and preserves '
                                                                                                     'its TeX; it '
                                                                                                     'cannot rename '
                                                                                                     'an existing '
                                                                                                     'heading. '
                                                                                                     'create/convert '
                                                                                                     'require kind, '
                                                                                                     'title and '
                                                                                                     'source_file '
                                                                                                     '(or file). The '
                                                                                                     'plan guard is '
                                                                                                     'required only '
                                                                                                     'when a reader '
                                                                                                     'plan exists.',
 ('structure_change', 'preconditions:1', 'operation is a string and plan/spine actions belong in op'): 'operation is '
                                                                                                       'a string; '
                                                                                                       'plan takes '
                                                                                                       'op or '
                                                                                                       'bounded '
                                                                                                       'ordered ops, '
                                                                                                       'spine takes '
                                                                                                       'op; '
                                                                                                       'bind_source '
                                                                                                       'uses the '
                                                                                                       'returned '
                                                                                                       'clearing_action '
                                                                                                       'and '
                                                                                                       'inspected '
                                                                                                       'occurrence '
                                                                                                       'guards; '
                                                                                                       'prepare_work '
                                                                                                       'uses its '
                                                                                                       'returned '
                                                                                                       'plan/selection '
                                                                                                       'guards and '
                                                                                                       'exact '
                                                                                                       'section_ids',
 ('structure_change', 'summary', 'use section_change for source edits.'): 'Use section_change for source heading '
                                                                          'edits. paragraph_plan source split/join '
                                                                          'and logical split/combine use their exact '
                                                                          'returned owner actions. Logical changes '
                                                                          'mint owner-issued unused IDs and require '
                                                                          'every occurrence and attachment '
                                                                          'disposition; old reviews remain '
                                                                          'historical, and metadata recovery never '
                                                                          'replays source.'}
REVIEWED_EFFECT_CHANGES = {'build': (('asynchronous selected-source build',),
           ('asynchronous exact selected or declared derived source build',
            'cancel only the exact issued build job and reap its owned process tree')),
 'style': (('presentation settings', 'preview'),
           ('immutable template candidate or exact guarded source application; preview never saves settings',))}


def test_no_precondition_the_audit_found_stated_is_lost():
    """Every clause of every string in the base contract table is carried somewhere.

    This is the check behind the claim.  The base commit's own table is pinned in
    tests/grammar_spec/head_contract_prose.json (written by the migration from
    `git show <base>:src/laplace/native/contracts.py`, so it is the audited text and
    not a re-reading of it), and each clause of each string must appear as a rule's
    `says`, in `outputs`/`recoverable_errors`/`errors`, or under its own extra key.
    """
    missing: list[tuple] = []
    reviewed: set[tuple] = set()
    for operation, contract in sorted(head_contracts().items()):
        declaration = DECLARATIONS[operation]
        summary = clauses(contract.get("summary") or "")
        if summary:
            if operation in REVIEWED_SUMMARY_CHANGES:
                old, now = REVIEWED_SUMMARY_CHANGES[operation]
                assert summary[0] == old and declaration.does == now, operation
                if operation == "references":
                    assert "configured reference library" in declaration.does and "references_attached" in declaration.does
                elif operation == "structure":
                    assert "view:summary" in declaration.does
            else:
                assert declaration.does == summary[0], operation
            carried = _carried_says(operation, "summary", 0)
            for clause in summary[1:]:
                if clause not in carried:
                    missing.append((operation, "summary", clause))
                    reviewed.add((operation, "summary", clause))
        for index, text in enumerate(contract.get("preconditions") or []):
            if operation == "structure" and index == 0:
                # The old start-with-rich-overview recipe is purposefully replaced
                # by owner-issued shallow navigation; legacy continuation remains.
                assert declaration.derived["navigation_reads"] == "laplace.manuscript.project_structure:navigation_reads"
                assert any("view:summary" in rule.says for rule in declaration.rules)
                assert any("legacy overview retains reader_plan.next_read" in rule.says.lower() for rule in declaration.rules)
                continue
            carried = _carried_says(operation, "preconditions", index)
            for clause in clauses(text):
                if clause not in carried:
                    missing.append((operation, "preconditions:%d" % index, clause))
                    reviewed.add((operation, "preconditions:%d" % index, clause))
        for key, held in (("outputs", declaration.outputs),
                          ("recoverable_errors", declaration.recoverable),
                          ("errors", declaration.errors)):
            for text in contract.get(key) or []:
                for clause in clauses(text):
                    if clause not in held:
                        missing.append((operation, key, clause))
        if operation in REVIEWED_EFFECT_CHANGES:
            assert (tuple(contract.get("effects") or ()), declaration.effects) == REVIEWED_EFFECT_CHANGES[operation], operation
        else:
            assert tuple(contract.get("effects") or ()) == declaration.effects, operation
        for key in ("next_steps", "recovery", "scope_rules", "source_locator_recipe"):
            if key not in contract:
                continue
            extra = declaration.extras.get(key)
            assert extra is not None, (operation, key)
            value = contract[key]
            if isinstance(value, str):
                for clause in clauses(value):
                    if clause not in extra:
                        missing.append((operation, key, clause))
            elif isinstance(value, list) and all(isinstance(item, str) for item in value):
                for item in value:
                    for clause in clauses(item):
                        if clause not in extra:
                            missing.append((operation, key, clause))
            else:
                assert extra == value, (operation, key)
    # the only clauses carried nowhere verbatim are the reviewed ones, and each has its named replacement rule
    assert set(missing) == set(REVIEWED_CLAUSE_REPLACEMENTS), "%d unreviewed clauses carried nowhere: %r" % (
        len(set(missing) - set(REVIEWED_CLAUSE_REPLACEMENTS)), sorted(set(missing) - set(REVIEWED_CLAUSE_REPLACEMENTS))[:6])
    for (operation, _where, _clause), replacement in REVIEWED_CLAUSE_REPLACEMENTS.items():
        assert replacement in [rule.says for rule in DECLARATIONS[operation].rules], (operation, replacement[:60])


def test_the_only_thing_deleted_rather_than_carried_is_the_hand_written_example():
    """Whatever the base table held that no declaration carries is named, not silent.

    The fixture holds every key of every base entry, `example` and `examples` included,
    so this compares against the whole thing rather than against a copy from which the
    examples had already been dropped.
    """
    carried_sections = {"summary", "preconditions", "outputs", "recoverable_errors",
                        "errors", "effects", "next_steps", "recovery", "scope_rules",
                        "source_locator_recipe", "input"}
    dropped = set()
    examples = 0
    for contract in head_contracts().values():
        dropped |= set(contract) - carried_sections
        examples += int("example" in contract) + len(contract.get("examples") or {})
    assert dropped == set(REPLACED_BY_GENERATION), dropped
    assert examples == 93, examples        # 72 `example` + 21 named `examples` entries


def _historical_schema_without_live_value_annotations(value):
    """Preserve pinned migration evidence; later typed meaning is tested separately."""
    if isinstance(value,list):return [_historical_schema_without_live_value_annotations(item) for item in value]
    if not isinstance(value,dict):return value
    annotated='x-laplace-value-form' in value
    return {key:_historical_schema_without_live_value_annotations(item) for key,item in value.items()
            if not key.startswith('x-laplace-value-') and not (annotated and key=='description')}


#: THE REVIEWED POST-MIGRATION SCHEMA CHANGES (D1, 2026-10-15). For each operation whose current input differs from the
#: pinned base table: the EXACT JSON paths that differ (any other difference fails), the owner that defines the change and
#: why it is not a weakened guard. Every path the base had and this ledger does not name compares verbatim.
REVIEWED_SCHEMA_CHANGES = {'apply_revision': {'owner': 'laplace.manuscript.proposal_preflight.source_anchor_contract',
                    'paths': ('$.anyOf[0].properties.edits.items.properties.source_anchor.properties.schema_version:added',
                              '$.anyOf[0].properties.edits.items.properties.source_anchor.required:removed',
                              '$.anyOf[1].properties.proposal.properties.edits.items.properties.source_anchor.properties.schema_version:added',
                              '$.anyOf[1].properties.proposal.properties.edits.items.properties.source_anchor.required:removed'),
                    'why': 'source_anchor became versioned (schema_version laplace.source-anchor/1|2); the removed '
                           'required was the empty list, so nothing became optional'},
 'author_history': {'owner': 'laplace.work.history (activity_contract, historical source protocol)',
                    'paths': ('$.allOf:changed',
                              '$.properties.expected_content_revision:added',
                              '$.properties.kind:added',
                              '$.properties.version_id:added',
                              '$.properties.view.enum:changed'),
                    'why': 'view=source reads one exact archived source (version_id, kind, '
                           'expected_content_revision) through its historical owner; activity filters are its own '
                           'allOf branch'},
 'block_change': {'owner': 'laplace.manuscript.blocks block variants',
                  'paths': ('$.additionalProperties:removed',
                            '$.oneOf:added',
                            '$.properties:removed',
                            '$.required:removed',
                            '$.type:removed'),
                  'why': 'the editor block door became exact composed variants (oneOf); placement-bound edits '
                         'require edits/operation/placement and the identity field expected'},
 'build': {'owner': 'laplace.manuscript.build_targets / build_jobs',
           'paths': ('$.allOf:added',
                     '$.properties.action:added',
                     '$.properties.build_job:added',
                     '$.properties.build_target:added',
                     '$.properties.prepare:added'),
           'why': 'derived build_target and exact build_job cancel (action:cancel) are additive; selected-source '
                  'build unchanged; prepare {edition, definition_revision} is the publication-edition wrapper '
                  'preparation (writing.publication_editions)'},
 'build_status': {'owner': 'laplace.manuscript.build_targets / build_jobs',
                  'paths': ('$.allOf:added', '$.properties.build_job:added', '$.properties.build_target:added'),
                  'why': 'exact build_job and derived build_target status reads are additive'},
 'document': {'owner': 'laplace.manuscript.document',
              'paths': ('$.additionalProperties:removed',
                        '$.oneOf:added',
                        '$.properties:removed',
                        '$.required:removed',
                        '$.type:removed'),
              'why': 'manuscript or declared derived target_kind; a separate view branch reads template candidates'},
 'export_pdf': {'owner': 'laplace.manuscript.document_templates',
                'paths': ('$.allOf:added', '$.properties.candidate_ref:added', '$.properties.preview_ref:added'),
                'why': 'style-preview export requires the exact candidate_ref and reviewed preview_ref (no latest '
                       'lookup)'},
 'logical_plan': {'owner': 'laplace.research.concepts logical plan paging',
                  'paths': ('$.properties.accepted_as_of:added',
                            '$.properties.accepted_limit:added',
                            '$.properties.accepted_offset:added'),
                  'why': 'accepted-object paging (accepted_offset/limit/as_of) is additive'},
 'project_metadata_change': {'owner': 'laplace.projects.library actor binding',
                             'paths': ('$.properties.by:added', '$.properties.publication_editions:added'),
                             'why': 'explicit actor `by` is additive; expected_revision and title stay required; '
                                    'optional publication_editions declares named PDF editions on the same guarded row'},
 'propose_revision': {'owner': 'laplace.manuscript.proposal_preflight.source_anchor_contract',
                      'paths': ('$.properties.edits.items.properties.source_anchor.properties.schema_version:added',
                                '$.properties.edits.items.properties.source_anchor.required:removed'),
                      'why': 'same versioned source_anchor as apply_revision; removed required was the empty list'},
 'read_artifact': {'owner': 'laplace.projects.artifacts',
                   'paths': ('$.oneOf[0].properties.expected_sha256:added',
                             '$.oneOf[0].properties.pointer:added',
                             '$.oneOf[1].properties.expected_sha256:added',
                             '$.oneOf[1].properties.pointer:added'),
                   'why': 'JSON-record pointer reads with expected_sha256 pins are additive on both selector '
                          'branches'},
 'references_attached': {'owner': 'laplace.research.references_surface attached entry',
                         'paths': ('$.properties.citekey:added',),
                         'why': 'citekey reads one exact selected bibliography entry; the empty read is unchanged'},
 'research_producer': {'owner': 'laplace.web.research_surface.producer contract',
                       'paths': ('$.additionalProperties:removed',
                                 '$.anyOf:added',
                                 '$.properties:removed',
                                 '$.required:removed',
                                 '$.type:removed'),
                       'why': 'dependencies is an optional declared input list (omission records no dependency '
                              'coverage, described in the schema); the {producer} envelope is an alternative shape '
                              'of the same producer'},
 'research_record': {'owner': 'laplace.web.research_surface record',
                     'paths': ('$.additionalProperties:removed',
                               '$.anyOf:added',
                               '$.description:added',
                               '$.properties:removed',
                               '$.required:removed',
                               '$.type:removed'),
                     'why': 'scope fields are additive; the flat {id, kind} record is an alternative shape of the '
                            'same record'},
 'section_change': {'owner': 'laplace.manuscript.manuscript_structure._check_plan_guard',
                    'paths': ('$.allOf:added',
                              '$.properties.after_line.minimum:added',
                              '$.properties.expected_plan_revision.description:added',
                              '$.properties.file:added',
                              '$.properties.title.maxLength:added',
                              '$.properties.title.minLength:added',
                              '$.required:changed'),
                    'why': 'expected_plan_revision is required by the owner whenever a reader plan exists (gate with '
                           'required=[expected_plan_revision]); create/convert require kind/title/file by allOf; '
                           'title/after_line bounds tightened'},
 'style': {'owner': 'laplace.manuscript.document_templates',
           'paths': ('$.additionalProperties:removed',
                     '$.oneOf:added',
                     '$.properties:removed',
                     '$.required:removed',
                     '$.type:removed'),
           'why': 'the retired settings/preview save became the guarded template candidate flow: prepare (guards, '
                  'reason), apply (candidate_ref, preview_ref), recover (candidate_ref)'},
 'task': {'owner': 'laplace.work.project_work task',
          'paths': ('$.properties.by:added', '$.properties.reader_basis:added', '$.properties.review_obligations:added'),
          'why': 'explicit actor `by`, the reader_basis anchor and the opt-in review_obligations (M5 Work review '
                 'lifecycle) are additive; title and goal stay required'},
 'writing_style_change': {'owner': 'laplace.manuscript.writing_style actor binding',
                          'paths': ('$.properties.by:added',),
                          'why': 'explicit actor `by` is additive; expected_revision and profile stay required'},
 'writing_style_profile_change': {'owner': 'laplace.manuscript.profiles actor binding',
                                  'paths': ('$.oneOf[0].properties.by:added', '$.oneOf[1].properties.by:added'),
                                  'why': 'explicit actor `by` is additive on both branches'}}


def _schema_paths(base, current, path="$"):
    """Every JSON path at which `current` differs from the pinned `base` schema: added, removed or changed."""
    out = []
    if isinstance(base, dict) and isinstance(current, dict):
        for key in sorted(set(base) | set(current), key=str):
            here = path + "." + str(key)
            if key not in base:
                out.append(here + ":added")
            elif key not in current:
                out.append(here + ":removed")
            else:
                out += _schema_paths(base[key], current[key], here)
    elif (isinstance(base, list) and isinstance(current, list) and len(base) == len(current)
          and all(isinstance(item, dict) for item in base + current)):
        for index, (left, right) in enumerate(zip(base, current)):
            out += _schema_paths(left, right, "%s[%d]" % (path, index))
    elif base != current:
        out.append(path + ":changed")
    return tuple(out)


def test_every_input_schema_moved_verbatim():
    """SCHEMAS is the base table's `input`, key for key, for all 73 operations."""
    for operation, contract in sorted(head_contracts().items()):
        expected = contract.get("input") or {}
        if operation == "literature_bind":
            expected = {**expected, "required": [*expected["required"], "claim_revision"]}
        if operation == "reference_text":
            expected = {**expected, "properties": {**expected["properties"],
                "query": {"type":"string","minLength":1,"maxLength":256},
                "expected_source_revision": {"type":"string"}}}
        if operation == "reference_fetch":
            expected = {**expected, "properties": {**expected["properties"], "candidate_id": {"type":"string"}}}
        if operation == "literature_scope":
            expected = {**expected, "properties": {**expected["properties"], "as_of": {"type":"string"}}}
        if operation == "visuals":
            # Bounded visuals reads (2026-10-14): the historical empty selector stays the
            # catalogue; index paging and exact id/ids detail are additive selectors.
            expected = {**expected, "properties": {**expected["properties"],
                "view": {"enum": ["catalogue", "index", "detail"]}, "id": {"type": "string", "minLength": 1},
                "ids": {"type": "array", "items": {"type": "string", "minLength": 1}, "minItems": 1, "maxItems": 8},
                "offset": {"type": "integer", "minimum": 0}, "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "cut": {"type": "string"}}}
        if operation == "author_history":
            # Preserve the migrated activity vocabulary and check the correction
            # owner's later bounded review extension independently.
            expected = {**expected, "properties": {**expected["properties"],
                "correction_category": {"enum": ["passage-comments", "project-notes", "global-notes", "applied-edits", "other", "notes"]},
                "status": {"enum": ["open", "resolved", "dismissed", "superseded", "unknown", "closed"]},
                "order": {"enum": ["oldest", "newest"]}}}
        if operation == "author_history":
            # Explicit additive metadata facets; the immutable base migration
            # remains unchanged and every original field still compares verbatim.
            expected = {**expected, "properties": {**expected["properties"],
                "turn_id": {"type":"string"}, "work_id": {"type":"string"},
                "dispatch_id": {"type":"string"}, "admitted_model": {"type":"string"},
                "resolved_model": {"type":"string"}, "role": {"type":"string"},
                "mode": {"type":"string"}, "terminal_kind": {"type":"string"},
                "projection": {"enum":["overview","sessions","trace","coverage","usage","delivery","feedback"]},
                "scope": {"enum":["project","workspace","session","turn","work"]},
                "cursor": {"type":"string"}}}
            # Activity owns its consumed filters; analytics fields in the shared
            # property vocabulary are not silently accepted in that view.
            from laplace.work.history import activity_contract
            activity=activity_contract()
            expected={**expected,'properties':{**expected['properties'],
                **{key:shape for key,shape in activity['properties'].items() if key!='view'}},
                'allOf':[{'if':{'required':['view'],'properties':{'view':{'const':'activity'}}},
                          'then':activity}]}
        if operation == "note":
            from laplace.work.feedback import target_schema, EFFECTS
            expected = {**expected, "properties": {**expected["properties"],
                "feedback_target": target_schema(), "feedback_effect": {"enum":list(EFFECTS)}}}
        if operation == "conversation_history":
            # Preserve historical migration fields while checking the published control reader extension.
            expected = {**expected, "properties": {**expected["properties"],
                "view": {"enum": ["turns", "controls"]}, "turn_id": {"type": "string"},
                "item_id": {"type": "string"}, "offset": {"type": "integer"}}}
        if operation == "task":
            expected = {**expected, "properties": {**expected["properties"],
                "parent_work_id": {"type": "string"}, "expected_work_revision": {"type":"string"},
                "anchor":{"type":"object"}, "obligation_id":{"type":"string"}}}
        if operation == "task_status":
            expected = {**expected, "required": [*expected["required"], "expected_work_scope_revision", "expected_work_status_revision"],
                "properties": {**expected["properties"], **{key:{"type":"string"} for key in
                    ("expected_work_scope_revision","expected_dependency_revision","expected_work_status_revision")}}}
            expected["properties"]["status"]={"enum":[*expected["properties"]["status"]["enum"],"withdrawn"]}
        if operation == "project":
            from laplace.work import project_work
            assert SCHEMAS[operation]==project_work.read_contract()
            continue
        if operation == "logical_plan":
            expected = {**expected, "properties": {**expected["properties"],
                "file": {"type": "string", "minLength": 1},
                "line_start": {"type": "integer", "minimum": 1},
                "line_end": {"type": "integer", "minimum": 1}},
                "dependentRequired": {"file": ["line_start", "line_end"],
                    "line_start": ["file", "line_end"], "line_end": ["file", "line_start"]}}
        if operation == "structure":
            # New explicit summary/full/detail branches retain the historical
            # physical/canonical selector contract verbatim as the legacy branch.
            assert SCHEMAS[operation]["oneOf"].count(expected) == 1, "the legacy branch is retained verbatim, once"
            continue
        observed = _schema_paths(expected, _historical_schema_without_live_value_annotations(SCHEMAS[operation]))
        assert observed == REVIEWED_SCHEMA_CHANGES.get(operation, {}).get("paths", ()), (operation, observed)
        if observed:
            # a reviewed post-migration change is real current admission: the owner's own example is admitted by
            # the composed owner schema, and every path the base table had and the ledger does not name is verbatim
            from jsonschema import Draft202012Validator
            assert not list(Draft202012Validator(d.owner_input_schema(operation)).iter_errors(d.generated_example(operation))), operation
            continue
        if not d.variants(operation):
            if operation == "references":
                # Historical migration evidence stays verbatim, while the live
                # declaration follows references_surface.handle: q is required.
                assert expected.get("required")==[]
                assert DECLARATIONS[operation].payload=={**expected,"required":["q"]}
            else:
                assert _historical_schema_without_live_value_annotations(DECLARATIONS[operation].payload) == expected, operation


def test_live_references_search_is_not_the_attached_project_collection():
    declaration=DECLARATIONS["references"]
    assert declaration.payload["required"]==["q"]
    assert "configured reference library" in declaration.does
    assert "references_attached" in declaration.does


# ---------------------------------------------------------------------------
# 3. the example is generated, and it validates
# ---------------------------------------------------------------------------
def test_no_literal_example_value_survives_as_code():
    """`"sha256:current"`, `"REQUEST-example"` and the rest are no longer VALUES.

    Docstrings are excluded on purpose: this packet's own modules quote two of these
    strings to say what was deleted and why, and a proof that forbade naming the defect
    would be a proof against writing down the reason.  What is forbidden is the string
    as a value a caller could copy.
    """
    gone = ("sha256:current", "REQUEST-example", "COPY concept.revision EXACTLY",
            "COPY logical_plan.revision EXACTLY", "chapters/method.tex")
    offending = []
    for name in ("native/contracts.py", "native/declarations.py", "native/declared.py",
                 "writing/schemas.py"):
        path = TREE / "src/laplace" / name
        tree = ast.parse(path.read_text(encoding="utf-8"))
        nodes = list(ast.walk(tree))
        docstrings = {id(node.body[0].value) for node in nodes
                      if isinstance(node, (ast.Module, ast.FunctionDef,
                                           ast.AsyncFunctionDef, ast.ClassDef))
                      and node.body and isinstance(node.body[0], ast.Expr)}
        for node in nodes:
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and id(node) not in docstrings):
                for literal in gone:
                    if literal in node.value:
                        offending.append((name, node.lineno, literal))
    assert not offending, offending
    for operation in DEPLOYED:
        example = json.dumps(d.generated_example(operation), ensure_ascii=False)
        for literal in gone:
            assert literal not in example, (operation, literal)


def test_every_generated_example_validates_against_the_schema_it_came_from():
    bad = []
    for operation in DEPLOYED:
        table = d.variants(operation)
        if table:
            choices = [(None, next(iter(table.values()))), *sorted(table.items())]
            for name, schema in choices:
                example = d.generated_example(operation, variant=name)
                try:
                    jsonschema.Draft202012Validator(schema).validate(example)
                except jsonschema.ValidationError as exc:
                    bad.append((operation, name, exc.message[:90]))
            continue
        schema = DECLARATIONS[operation].payload
        if not schema:
            continue
        example = d.generated_example(operation)
        try:
            jsonschema.Draft202012Validator(schema).validate(example)
        except jsonschema.ValidationError as exc:
            bad.append((operation, "", exc.message[:90]))
    assert not bad, bad


# ---------------------------------------------------------------------------
# 4. a field never travels without its home
# ---------------------------------------------------------------------------
def test_no_rule_names_a_field_without_naming_its_home_when_the_field_is_a_guard():
    """A guard name in a rule's `field` must come with the home it belongs to.

    This is the grammar's one sentence, enforced on this lane's own output: of the 20
    guard names the report counted over 9 values, none may appear as a bare field.
    """
    naked = [(operation, rule.field, rule.kind)
             for operation, declaration in DECLARATIONS.items()
             for rule in declaration.rules
             if rule.field in g.GUARD_NAMES and not rule.home and rule.kind != "scope"]
    assert not naked, naked


def test_help_mints_the_live_token_of_every_home_a_door_guards():
    """On a tracked project, every home whose kind `identity()` can read is minted."""
    project = "synthetics-foundations"
    assert (TREE / "registry_projects.json").is_file()
    unresolved = []
    minted = 0
    for operation in DEPLOYED:
        for row in d.expected_tokens(operation, project=project, root=TREE):
            kind = row["home_kind"]
            if row.get("token"):
                minted += 1
                assert row["token"].startswith("rev:%s:" % kind)
                g.parse(row["token"])
            elif g.MINT_STATUS[kind] == "read" and row.get("home"):
                unresolved.append((operation, kind, row.get("absent") or row.get("closes")))
    assert minted, "no home resolved on %s" % project
    # A wired read whose home this project does not contain is allowed and named;
    # an unwired one must carry the read that would close it.
    for operation, kind, why in unresolved:
        assert why, (operation, kind)


def test_live_generated_identity_examples_keep_canonical_and_legacy_forms_distinct():
    """Canonical tokens travel only in expected; legacy digest/content fields keep form."""
    from laplace.native import verbs as writing_verbs
    project = "synthetics-foundations"
    identity_operations = sorted(operation for operation, declaration in DECLARATIONS.items()
                                 if any(rule.kind == "identity" for rule in declaration.rules))
    assert identity_operations

    def values_named(value, name):
        if isinstance(value, dict):
            return ([value[name]] if name in value else []) + [item
                for child in value.values() for item in values_named(child, name)]
        if isinstance(value, list):
            return [item for child in value for item in values_named(child, name)]
        return []

    for operation in identity_operations:
        # D1 (2026-10-15): a live example is validated against the composed owner variant, or the composed owner
        # schema for a flat operation (the admission authority); the offline legacy example against the raw
        # declaration payload, its legacy branch, separately
        table = d.variants(operation) or {"": d.owner_input_schema(operation)}
        if not d.variants(operation):
            offline = d.generated_example(operation)
            jsonschema.Draft202012Validator(DECLARATIONS[operation].payload or d.owner_input_schema(operation)).validate(offline)
            d.validate_owner_payload(operation, offline, project="")
        for variant, schema in table.items():
            example = d.generated_example(operation, project=project, root=TREE,
                                          variant=variant or None)
            jsonschema.Draft202012Validator(schema).validate(example)
            route = writing_verbs.route_for_operation(operation, example)
            if route is None:
                continue
            for name, _homes, form, _optional in route.guards:
                carried = values_named(example, name)
                for value in carried:
                    assert not (isinstance(value, str) and value.startswith("rev:")), (
                        operation, variant, name, value)
                    if form == "digest" and not str(value).startswith("<"):
                        assert g._HEX.fullmatch(str(value)), (operation, variant, name, value)
                    if form in writing_verbs.CARRIERS:
                        # Live typed owner-field descriptions replace the old bare carrier
                        # placeholder; the pinned migration table remains unchanged.
                        assert (value == "<%s>" % writing_verbs.CARRIERS[form] or
                                isinstance(value,str) and value.startswith('<Exact ')), (
                            operation, variant, name, value)
            for path, value in _walk_example(example):
                if isinstance(value, str) and value.startswith("rev:"):
                    assert path.startswith("expected."), (operation, variant, path, value)
                if isinstance(value, str) and " token: read " in value:
                    pytest.fail(str((operation, variant, path, value)))


def test_identity_schema_alternative_composes_with_every_owner_constraint():
    """Canonical-vs-legacy guards add one allOf clause; owner constraints survive intact."""
    for operation in ("concept_change", "structure_change"):
        declaration = DECLARATIONS[operation]
        raw = d._VARIANTS[declaration.variants]()
        public = d.variants(operation)
        for name, owner in raw.items():
            exposed = public[name]
            assert exposed["properties"] == owner["properties"]
            assert exposed.get("additionalProperties") == owner.get("additionalProperties")
            assert exposed.get("anyOf") == owner.get("anyOf")
            owner_all = list(owner.get("allOf") or ())
            for old_clause, new_clause in zip(owner_all,exposed.get("allOf", [])):
                if old_clause == new_clause: continue
                # The six selected-node variants already accept expected at the
                # owner; their guard requires_any now exposes that exact choice.
                routes=d._variant_routes(operation,name)
                digest_fields={field for route in routes for field,_homes,form,_optional in route.guards if form=='digest'}
                assert all(branch.get('required') and set(branch['required'])<=digest_fields
                           for branch in old_clause['anyOf'])
                # each legacy branch is unchanged except that a canonical `expected` it ALSO carries must be nonempty
                assert new_clause['anyOf'][1:]==[{**branch,'properties':{**(branch.get('properties') or {}),'expected':{'minItems':1}}}
                                                for branch in old_clause['anyOf']]
                assert new_clause['anyOf'][0]=={'required':['expected'],'properties':{'expected':{'minItems':1}}}
            if len(exposed.get("allOf", [])) == len(owner_all):
                assert exposed.get("required") == owner.get("required")
                continue
            identity_clause = exposed["allOf"][-1]
            canonical = identity_clause["anyOf"][0]
            assert canonical["required"] == ["expected"]
            assert canonical["properties"]["expected"] == {"minItems": 1}
            legacy = identity_clause["anyOf"][1]["required"]
            assert set(exposed.get("required") or ()) | set(legacy) == \
                set(owner.get("required") or ())


#: the reviewed canonical-or-legacy guard alternatives (readiness D1_live_example_admission_axis, 21 named variants)
CANONICAL_GUARD_VARIANTS = frozenset({
    ("concept_change", name) for name in ("add_edge", "remove_edge", "retype_edge", "edit_node", "add_node", "set_source",
        "set_projection", "set_mathematics", "set_kind", "set_status", "set_spine", "unset_spine", "move_node")} | {
    ("structure_change", name) for name in ("initialize", "prepare_work", "section_contract", "bind_source", "plan", "spine",
        "reconcile", "bind_results", "start_authoring")})


def test_all_canonical_identity_alternatives_require_nonempty_expected():
    """SI-C1 + D1 (2026-10-15): empty canonical is invalid alone AND beside valid legacy guards (an empty canonical
    presence never authorises a write); legacy alone and nonempty canonical remain admitted."""
    changed = set()
    for operation in ("concept_change", "structure_change"):
        for variant, schema in d.variants(operation).items():
            clauses = [clause for clause in schema.get("allOf") or []
                       if any("expected" in (branch.get("required") or [])
                              for branch in clause.get("anyOf") or [])]
            if not clauses:
                continue
            changed.add((operation, variant))
            clause = clauses[-1]
            canonical = next(branch for branch in clause["anyOf"]
                             if "expected" in branch.get("required", []))
            legacy = next(branch for branch in clause["anyOf"] if branch is not canonical)
            assert canonical["properties"]["expected"]["minItems"] == 1

            example = d.generated_example(operation, variant=variant)
            # No live project means the generator selects the legacy branch. Preserve all
            # nonidentity fields, then isolate the canonical or legacy alternative.
            legacy_names = legacy["required"]
            empty_only = {key: value for key, value in example.items()
                          if key not in legacy_names}
            empty_only["expected"] = []
            assert list(jsonschema.Draft202012Validator(schema).iter_errors(empty_only))
            jsonschema.Draft202012Validator(schema).validate(example)        # legacy guards alone stay admitted
            empty_plus_legacy = {**example, "expected": []}
            assert list(jsonschema.Draft202012Validator(schema).iter_errors(empty_plus_legacy)), (operation, variant)
            # Type and item constraints remain owned by the unchanged outer property.
            for malformed in ("not-an-array", [""]):
                invalid_outer = {**example, "expected": malformed}
                assert list(jsonschema.Draft202012Validator(schema).iter_errors(invalid_outer))
    assert changed == CANONICAL_GUARD_VARIANTS, (sorted(changed - CANONICAL_GUARD_VARIANTS), sorted(CANONICAL_GUARD_VARIANTS - changed))
    from laplace.core import identity_doors
    assert "minItems" not in identity_doors.EXPECTED_FIELD


def test_unresolved_identity_examples_validate_and_name_digest_or_content_carriers(tmp_path):
    identity_operations = sorted(operation for operation, declaration in DECLARATIONS.items()
                                 if any(rule.kind == "identity" for rule in declaration.rules))
    for operation in identity_operations:
        table = d.variants(operation) or {"": DECLARATIONS[operation].payload}
        for variant, schema in table.items():
            example = d.generated_example(operation, project="absent-project", root=tmp_path,
                                          variant=variant or None,
                                          payload={"file": "explicit-target.tex"})
            jsonschema.Draft202012Validator(schema).validate(example)
            for path, value in _walk_example(example):
                if isinstance(value, str):
                    assert not value.startswith("rev:"), (operation, variant, path, value)
                    assert " token: read " not in value, (operation, variant, path, value)


def test_explicit_target_context_is_not_hidden_by_generated_placeholders(monkeypatch):
    seen = []
    original = d.expected_tokens
    def observed(operation, **kwargs):
        seen.append(dict(kwargs.get("payload") or {}))
        return original(operation, **kwargs)
    monkeypatch.setattr(d, "expected_tokens", observed)
    d.generated_example("visual_place", project="absent", root=TREE,
                        payload={"file": "real/figure-target.tex"})
    assert seen[-1]["file"] == "real/figure-target.tex"


def _walk_example(value, path=""):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk_example(child, "%s%s." % (path, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_example(child, "%s%d." % (path, index))
    else:
        yield path.rstrip("."), value


def test_every_home_without_a_live_token_names_what_would_obtain_it():
    for operation in DEPLOYED:
        for row in d.expected_tokens(operation, project="", root=TREE):
            if not row.get("token"):
                assert row.get("needs") or row.get("closes") or row.get("absent"), (
                    operation, row)


def test_rules_accept_meaningful_text_independently_of_length():
    text = "Explain the owner obligation and its recovery. " * 20
    assert d.Rule("shape", says=text).says == text
    for invalid in ("", "   ", None, 3):
        with pytest.raises(ValueError, match="nothing to say"):
            d.Rule("shape", says=invalid)


def test_an_identity_rule_without_a_real_home_is_refused():
    with pytest.raises(ValueError, match="names the home"):
        d.Rule("identity", field="expected_revision", home="not-a-home", says="x")


# ---------------------------------------------------------------------------
# 5. Contract projection and meaningful authored text
# ---------------------------------------------------------------------------
def test_contracts_is_only_a_projection_of_the_declarations():
    """The named holder of the `CONTRACTS` retirement trigger.

    `CONTRACTS` is kept because `src/laplace/writing/operations.py:215` validates unknown
    fields through it and eleven tests read it, but it is a second NAME for the
    contract, so the report carries a retirement trigger for it.  A trigger needs a
    holder: this test is it.  It asserts the name holds no state of its own --- every
    entry is rebuilt from the declaration on read --- so the day `writing_tools.py`
    validates against `SCHEMAS[operation]` directly, deleting `CONTRACTS` cannot lose
    anything, and until then nobody can quietly put a fact in it.
    """
    from laplace.native.contracts import CONTRACTS
    from laplace.native.declarations import DECLARATIONS
    from laplace.writing.schemas import SCHEMAS
    assert CONTRACTS.__class__.__dict__.get("__missing__") is not None
    assert not dict.keys(CONTRACTS), "CONTRACTS holds stored entries: %r" % (
        list(dict.keys(CONTRACTS)),)
    assert set(CONTRACTS) == set(DECLARATIONS)
    import copy
    raw_before = {operation: copy.deepcopy(DECLARATIONS[operation].payload) for operation in DECLARATIONS}
    for operation in sorted(DECLARATIONS):
        entry = CONTRACTS[operation]
        assert entry["summary"] == DECLARATIONS[operation].does
        # D1 (2026-10-15): the input is the COMPOSED owner schema, the exact authority validate_owner_payload admits
        # against, not the raw declaration payload (the raw payload is the legacy axis, tested separately)
        assert entry["input"] == d.owner_input_schema(operation), operation
        # every read is fresh: mutating one returned value leaks into neither the next read nor the declaration
        entry["input"]["__probe__"] = True
        assert "__probe__" not in CONTRACTS[operation]["input"]
        assert "__probe__" not in d.owner_input_schema(operation)
    assert {operation: DECLARATIONS[operation].payload for operation in DECLARATIONS} == raw_before, "raw payloads unchanged"
    # reading it twice must not store anything either
    assert not dict.keys(CONTRACTS)


# ---------------------------------------------------------------------------
# 6. the duplicate and the fallback are gone
# ---------------------------------------------------------------------------
def test_help_no_longer_serves_the_owner_contract_twice(tmp_path):
    response = writing_tools.execute(tmp_path, "p", "work", "help",
                                     {"operation": "structure_change"})
    assert "requested_payload_contract" not in response
    assert "owner_contract" not in response["action"]
    assert "owner_contract" not in json.dumps(response)


def test_a_bare_help_serves_the_generated_index_and_the_route_to_one_declaration(tmp_path):
    response = writing_tools.execute(tmp_path, "p", "work", "help", {})
    assert response["read_one"]["payload"]["operation"] == "<from one concept catalogue>"
    assert response["http_door"]["payload"]["door"] == "http"
    assert "catalogue" not in response
    rows = [row for concept in response["concepts"] for row in
            writing_tools.execute(tmp_path, "p", "work", "help",
                                  {"concept": concept["concept"]})["catalogue"]]
    permitted = reads.READS | reads.WRITES
    assert {row["operation"] for row in rows} == set(permitted)
    from laplace.native import verbs as writing_verbs
    reached = {(act["verb"], row["concept"]) for row in rows for act in row["acts"]}
    declared = {pair for operation in permitted for pair in writing_verbs.pairs_for(operation)}
    assert reached == declared
    for row in rows:
        assert row["does"] == d.DECLARATIONS[row["operation"]].does
    assert len({(row["operation"], row["concept"]) for row in rows}) == len(rows)
    for concept in response["concepts"]:
        selected = [row for row in rows if row["concept"] == concept["concept"]]
        assert concept["operations"] == len(selected)
        native_verbs={act["verb"] for row in selected for act in row["acts"]}
        # Additive homes must be proven by the same callable owner route, not a
        # hardcoded concept exception or a claim in the presentation catalogue.
        for home in d.native_homes('p',concept['concept']):
            navigation=home['native_request']
            selected=writing_verbs.choose(navigation['verb'],navigation['concept'],navigation['payload'])
            assert selected.operation==home['owner_read']['operation']
            assert writing_verbs.native_example(selected.operation,navigation['payload'],project='p')['native_request']==navigation
            from jsonschema import Draft202012Validator
            assert not list(Draft202012Validator(home['payload']).iter_errors(navigation['payload']))
            native_verbs.add(navigation['verb'])
        assert concept["verbs"] == sorted(native_verbs)
    for row in d.catalogue(permitted):
        exact = writing_tools.execute(tmp_path, "p", "work", "help",
                                      {"operation": row["operation"]})["action"]
        assert {key: exact[key] for key in ("operation", "verb", "concept", "does")} == {
            key: row[key] for key in ("operation", "verb", "concept", "does")}
        assert row["guards"] == list(d.DECLARATIONS[row["operation"]].homes)
        variants = d.variants(row["operation"])
        assert len(variants) == len(set(variants))
        for name, schema in variants.items():
            selected = writing_tools.execute(
                tmp_path, "p", "work", "help",
                {"operation": row["operation"], "variant": name})["action"]
            assert selected["selected_variant"] == name
            assert selected["input"] == schema
        if len(variants) == 1:
            assert served_input(exact) == next(iter(variants.values()))
        elif "variants" in exact:
            assert set(exact["variants"]) == set(variants)
        elif variants:
            assert served_input(exact)["oneOf"] == [variants[name] for name in sorted(variants)]
    row = next(r for r in rows if r["operation"] == "structure_change")
    assert row["verb"] in g.VERBS and "@" in row["concept"] and row["guards"]


def test_an_operation_with_many_variants_serves_an_index_and_the_route_to_one(tmp_path):
    response = writing_tools.execute(tmp_path, "p", "work", "help",
                                     {"operation": "concept_change"})
    action = response["action"]
    assert "input" not in action and action["variants"]
    assert action["read_one_variant"]["payload"]["operation"] == "concept_change"
    one = writing_tools.execute(tmp_path, "p", "work", "help",
                                {"operation": "concept_change", "variant": "add_node"})
    assert one["action"]["selected_variant"] == "add_node"
    assert one["action"]["input"]["properties"]["operation"]["const"] == "add_node"


def test_help_selector_schema_and_handler_are_one_shape(tmp_path):
    from laplace.native import contracts as writing_contracts
    schema = writing_contracts.exact_contract("help", permitted=True)["input"]
    validator = jsonschema.Draft202012Validator(schema)
    valid = [
        {},
        {"concept": "argument@plan"},
        {"operation": "source"},
        {"operation": "concept_change", "variant": "add_node"},
        {"door": "http"},
        {"route": "/authoring/build"},
        {"route": "/authoring/build", "method": "GET",
         "http_operation": "authoring/build-status"},
    ]
    for payload in valid:
        validator.validate(payload)
        writing_tools.execute(tmp_path, "p", "work", "help", payload)

    structurally_invalid = [
        {"concept": ""}, {"operation": []}, {"door": "bad"}, {"route": []},
        {"variant": "add_node"}, {"operation": "source", "concept": "argument@plan"},
        {"door": "http", "route": "/authoring/build"}, {"method": "GET"},
    ]
    for payload in structurally_invalid:
        assert list(validator.iter_errors(payload)), payload
        with pytest.raises(ValueError):
            writing_tools.execute(tmp_path, "p", "work", "help", payload)

    semantically_unknown = [
        {"operation": "not-an-operation"},
        {"concept": "not-a-concept"},
        {"route": "/not-a-route"},
        {"operation": "concept_change", "variant": "not-a-variant"},
        {"operation": "source", "variant": "add_node"},
        {"route": "/authoring/build", "http_operation": "not-an-http-operation"},
    ]
    for payload in semantically_unknown:
        with pytest.raises(ValueError):
            writing_tools.execute(tmp_path, "p", "work", "help", payload)
    with pytest.raises(ValueError, match="unknown variant"):
        d.help_payload("concept_change", permitted=True, variant="not-a-variant")


def test_help_runtime_honours_standard_constraints_from_the_active_declaration(
        tmp_path, monkeypatch):
    concept = d.DECLARATIONS["help"].payload["properties"]["concept"]
    monkeypatch.setitem(concept, "pattern", r"^argument@plan$")
    writing_tools.execute(tmp_path, "p", "work", "help", {"concept": "argument@plan"})
    with pytest.raises(ValueError, match="does not match"):
        writing_tools.execute(tmp_path, "p", "work", "help", {"concept": "artifact@project"})


def test_measure_help_uses_the_public_bare_projection(tmp_path):
    import subprocess
    out = tmp_path / "measured"
    done = subprocess.run([
        str(TREE / "scripts/laplace-python"), str(TREE / "tools/measure_help.py"),
        "--src", str(TREE / "src"), "--root", str(tmp_path), "--out", str(out),
        "--label", "candidate",
    ], cwd=TREE, capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    measured = json.loads((out / "candidate.json").read_text(encoding="utf-8"))
    public = writing_tools.execute(tmp_path, "", "work", "help", {})
    assert measured["bare_projection"] == "public-help-index"
    assert measured["bare_keys"] == sorted(public)
    assert measured["bare_chars"] == len(
        json.dumps(public, ensure_ascii=False, default=str))
    assert "catalogue" not in public


def test_the_undeclared_http_preconditions_are_declared(tmp_path):
    """The client header and the turn's `text` field, the two the arrival paid for."""
    response = writing_tools.execute(tmp_path, "p", "work", "help", {"door": "http"})
    routes = {row["route"]: row for row in response["routes"]}
    assert routes["*"]["header"] == "X-Laplace-Writing: 1"
    assert routes["*"]["enforced_at"] == "src/laplace/scanner.py:2185@" + d.BASE_REVISION
    turn = writing_tools.execute(tmp_path, "p", "work", "help",
                                 {"route": "/authoring/turn"})["action"]
    assert "text" in turn["input"]["properties"]
    one_of = next(rule for rule in turn["rules"] if rule["rule"] == "one-of")
    assert one_of["fields"] == ["text", "queued_work_ids"]
    # S1 B1: the refusal lives in turn admission; the citation is resolved from its own text
    # and carries the serving file's digest (COORDINATE_LAW), not the historical commit.
    assert one_of["enforced_at"] == d.cited(d.anchored_site("src/laplace/writing/turn_admission.py",
                                                            'raise ValueError("Write a message first.")'))


def test_http_help_selects_method_and_exposes_route_ambiguity(tmp_path):
    from laplace.native import contracts as writing_contracts
    help_schema=writing_contracts.exact_contract('help',permitted=True)['input']
    help_fields=help_schema['properties']
    assert {'route','method','http_operation'}<=set(help_fields)
    assert help_schema['dependentRequired']=={
        'variant':['operation'],'context':['operation'],'section':['operation'],'method':['route'],'http_operation':['route']}
    ambiguous=writing_tools.execute(tmp_path,'p','work','help',
        {'route':'/authoring/build'})['action']
    assert ambiguous['ambiguous'] is True
    assert {(row['operation'],tuple(row['methods'])) for row in ambiguous['alternatives']}=={
        ('authoring/build-status',('GET',)),('authoring/build-start',('POST',))}
    status=writing_tools.execute(tmp_path,'p','work','help',{
        'route':'/authoring/build','method':'GET',
        'http_operation':'authoring/build-status'})['action']
    assert status['verb']=='read' and status['concept']=='build@project'
    assert status['methods']==['GET'] and 'fresh' in ' '.join(status['outputs'])
    # the consumer is declared by its function anchor; its resolved line holds exactly that function
    consumer=status['consumers']['output-status'];rel,_,line=consumer.rpartition(':')
    assert rel.endswith('static_shared/workspace-output.mjs')
    assert 'async function paintBuild(){' in Path(rel).read_text().splitlines()[int(line)-1]
    for payload in ({'door':'http','method':'GET'}, {'method':''},
                    {'http_operation':'authoring/build-status'}, {'http_operation':''}):
        with pytest.raises(ValueError,match='requires route'):
            writing_tools.execute(tmp_path,'p','work','help',payload)
    with pytest.raises(ValueError,match='no declared HTTP door'):
        writing_tools.execute(tmp_path,'p','work','help',{
            'route':'/authoring/build','method':'GET',
            'http_operation':'authoring/build-start'})


def test_structure_change_http_help_inherits_owner_identity_guards(tmp_path):
    owner=d.DECLARATIONS['structure_change']
    expected={(rule.field,rule.home,rule.read or d.read_call(
        d.g.HOME_KINDS[rule.home].read)) for rule in owner.rules
        if rule.kind=='identity'}
    action=writing_tools.execute(tmp_path,'p','work','help',{
        'route':'/work/structure/change','method':'POST',
        'http_operation':'work/structure-change'})['action']
    observed={(rule.get('field'),rule.get('home'),rule.get('read'))
              for rule in action['rules'] if rule['rule']=='identity'}
    assert action['source_operation']=='structure_change'
    assert observed==expected
    assert action['header']['required']=='X-Laplace-Writing: 1'
    # D1 (2026-10-15): the wrapper is a oneOf of composed owner variants, so each branch carries its OWN plan guard:
    # expected_revision for the legacy whole-plan operations, expected_plan_revision for the bound subject edits, and
    # paragraph_plan's conditional guards (plan/narrative/reader basis, or the restructure guards and token)
    for branch in action['input']['oneOf']:
        ops=branch['properties']['operation'];ops=ops.get('enum') or [ops['const']]
        if set(ops)<={'initialize','plan','spine','reconcile','bind_results'}:
            assert 'expected_revision' in branch['required'],ops
        elif ops in (['prepare_work'],['section_contract'],['bind_source']):
            assert 'expected_plan_revision' in branch['required'],ops
        elif ops==['start_authoring']:
            # writing.project_lifecycle: the transition is guarded by the project-lifecycle home, never by a plan
            assert 'expected_project_lifecycle' in branch['required'] and 'expected_revision' not in branch['required']
        else:
            assert ops==['paragraph_plan'];rule=branch['allOf'][0]
            assert {'expected_plan_revision','expected_narrative_revision','expected_reader_basis'}<=set(rule['else']['required'])
            thens=[step['then']['required'] for step in rule['then']['allOf']]
            assert ['restructure_token','guards'] in thens and ['receipt_id','intent_artifact_id','guards'] in thens
    # the subject edits (prepare_work/section_contract/bind_source/paragraph_plan) added the plan identity home
    # start_authoring (writing.project_lifecycle) adds the project-lifecycle home
    assert {rule[0] for rule in observed}=={
        'expected_revision','expected_plan_revision','expected_source_revision','expected_concept_revision','expected_project_lifecycle'}


def test_required_interface_contracts_resolve_real_owner_and_consumer_lines():
    required={'authoring/events','authoring/interrupt','authoring/steer',
              'authoring/session','authoring/session-turn',
              'authoring/proposals','authoring/proposal-preview','work/structure',
              'work/structure-change','walk/doc','authoring/build-status',
              'authoring/build-start','projection/pdf'}
    assert required<=set(d.HTTP_DECLARATIONS)
    for name in required:
        declaration=d.HTTP_DECLARATIONS[name]
        assert declaration.methods and declaration.resolved_consumers()
        assert declaration.resolved_responses()
        for site in [declaration.handler,*declaration.resolved_consumers().values(),
                     *declaration.resolved_responses().values()]:
            path,_,line=site.rpartition(':')
            source=(TREE/path).read_text().splitlines()
            assert source[int(line)-1].strip(),(name,site)


def test_required_interface_failure_shapes_come_from_real_handlers(tmp_path,monkeypatch):
    from laplace.web import authoring as authoring_surface, project_work_surface
    from laplace.manuscript import projection_viewer
    monkeypatch.setattr(checkout, 'repo_root',lambda:tmp_path)
    status,ctype,body=authoring_surface.handle(
        '/authoring/session',{'id':['missing']},'GET',b'')
    assert status==409 and ctype.startswith('application/json')
    assert json.loads(body)['error']=='Unknown writing session.'
    status,ctype,body=authoring_surface.handle(
        '/authoring/interrupt',{},'POST',json.dumps({'turn_id':'missing'}).encode())
    assert status==409 and json.loads(body)['error']=='There is no active provider turn in this project.'
    status,ctype,body=project_work_surface.handle(
        '/work/structure',{},'GET',repo_root=tmp_path)
    assert status==422 and json.loads(body)['error']=='project is required'
    status,ctype,body=projection_viewer.handle(
        '/projection/pdf',{'file':['/outside.pdf']},'GET',b'')
    assert status==403 and 'repo root' in json.loads(body)['error']


def test_every_declared_http_door_cites_lines_that_exist():
    """The resolved handler is a coordinate in this tree. A literal door coordinate names the campaign base
    (the coordinate law, d.COORDINATE_LAW): it is checked in this tree while its file is still here, and at
    d.BASE_REVISION once the file has moved (the physical-home move of 2026-10-21 moved scanner.py and others)."""
    import subprocess                                             # noqa: PLC0415
    for name, declaration in sorted(HTTP_DECLARATIONS.items()):
        for citation in [declaration.handler, declaration.header_door] + \
                [rule.door for rule in declaration.rules]:
            if not citation:
                continue
            path, _, number = citation.rpartition(":")
            if citation == declaration.handler or (TREE / path).is_file():
                source = (TREE / path).read_text(encoding="utf-8").splitlines()
            else:
                source = subprocess.run(["git", "-C", str(TREE), "show", "%s:%s" % (d.BASE_REVISION, path)],
                                        capture_output=True, text=True, check=True).stdout.splitlines()
            assert 0 < int(number) <= len(source), (name, citation)


def test_the_operating_brief_references_the_declarations_instead_of_copying_them():
    from laplace.writing import operating as writing_operating
    contract = writing_operating.tool_contract()
    payload_contracts = contract["operation_payload_contracts"]
    assert payload_contracts["exact_actions_digest"] == contract["exact_actions_digest"]
    assert set(d.exact_action_digests()) == set(DEPLOYED)
    assert payload_contracts["read_one"]["operation"] == "help"
    # the four owner schemas the brief used to ship on every turn are not in it
    text = json.dumps(payload_contracts)
    assert "properties" not in text and len(text) < 700, len(text)


#: the two in-harness-join operations (2026-10-20), measured apart from the accepted operation set below
JOIN_OPERATIONS = ("development_source", "work_delivery", "workflow_definition_change")


def test_the_help_total_is_smaller_than_the_measured_baseline():
    """220,767 characters for the 73 operations at the base commit, by the instrument
    that reproduces the published help_sizes.csv `json_chars` column exactly.

    The ACCEPTED operation set keeps that cap exactly (measured 220,656 at the causal correction, 2026-10-20: 111
    characters of headroom). The two in-harness-join operations hold Root's APPROVED separate allocation
    (evidence/WRITING_JOINS_2026-10-04/codex-continuation/source-state-development-help-budget-decision-20261020.json,
    independently verified): at most 2,900 characters each and 5,400 combined, total envelope at most 226,167; no
    per-call cap, default context payload or accepted operation is widened by it."""
    from laplace.writing import operating as writing_operating
    contract = writing_operating.tool_contract()
    permitted = set(contract["role_permissions"]["work"])
    sizes = {}
    for operation in DEPLOYED:
        action = d.help_payload(operation, permitted=operation in permitted)
        sizes[operation] = len(json.dumps({"schema_version": writing_operating.VERSION,
                                           "digest": contract["digest"],
                                           "requested_operation": operation, "action": action},
                                          ensure_ascii=False, default=str))
    accepted = sum(size for operation, size in sizes.items() if operation not in JOIN_OPERATIONS)
    assert accepted < 220767, accepted
    # Root's approved allocation for the two join operations: each <= 2,900, combined <= 5,400, total <= 226,167
    joined = {operation: sizes[operation] for operation in JOIN_OPERATIONS}
    assert all(size <= 2900 for size in joined.values()) and sum(joined.values()) <= 5400, joined
    assert accepted + sum(joined.values()) <= 226167, accepted + sum(joined.values())
    # Exact help is requested on demand. The context measurement report pins totals,
    # native registration and public help sizes to the candidate, without treating
    # historical clause length or a branch-specific moving cap as semantic acceptance.


# ---------------------------------------------------------------------------
# 7. the one red this packet leaves, bounded
# ---------------------------------------------------------------------------
#: `test_grammar.py::test_the_cited_lines_are_the_lines_they_claim` fails in this
#: worktree, and it is right to.  The grammar lane cites `writing_contracts.py` at five
#: lines; this packet shrank that file from 632 lines to 128, so five citations point
#: past its end.  GRAMMAR.md section 8 forbids editing the installed `grammar.py`, so the
#: citations are NOT corrected here --- they are measured, resolved to their new
#: addresses by tools/citation_migration.py, and handed to the synthesis lane.  This test
#: holds the set closed: a SIXTH stale citation, or one with no new address, fails.
# EIGHT, not five.  The round-3 grammar module the synthesis installed cites three more
# lines of the base `writing_contracts.py` than the round-2 one the two lanes had:
# `:579` (concept_change carries an edge's target inside the op object), `:604` (the `by`
# added to every logical_plan_change variant) and `:607` (`connect`'s top-level `target`,
# the one owner key that collides with a request field).  All three are in
# `exact_contract`'s `if operation == ...` blocks rather than in the CONTRACTS dict, which
# is why `_operation_of` had to learn that second shape.
KNOWN_STALE_CITATIONS = (
    "src/laplace/writing_contracts.py:314",
    "src/laplace/writing_contracts.py:386",
    "src/laplace/writing_contracts.py:433",
    "src/laplace/writing_contracts.py:439",
    "src/laplace/writing_contracts.py:550",
    # EIGHT, not five.  The generated-contract lane's own table listed these three as
    # resolved and `exists_today`, but 579, 604 and 607 are past the end of the 128-line
    # file too, and all three resolved to `export_pdf`'s declaration because
    # `_operation_of` reads upwards for the nearest contract entry and they are CODE after
    # the dict, not entries in it.  The contract x dispatch synthesis resolved them by hand
    # (tools/citation_migration.CODE_SITES) and keeps them in the closed set.
    "src/laplace/writing_contracts.py:579",
    "src/laplace/writing_contracts.py:604",
    "src/laplace/writing_contracts.py:607",
)


def test_the_stale_grammar_citations_are_exactly_the_five_with_a_new_address():
    # IN THE TREE, not in the live evidence directory.  The first version read the
    # generated-contract lane's own deposit by absolute path, so this proof measured
    # another tree's line numbers: on this merge it resolved
    # `src/laplace/writing_declared.py:1025` to `    'structure_change',` because deleting
    # 73 typed handlers moved every line below them.  GRAMMAR.md section 8 names this
    # exact mistake ("the installed test read ... from the live evidence tree").
    migration = TREE / "tests/citation_migration.json"
    assert migration.is_file(), (
        "%s is missing. Regenerate it in this tree with\n"
        "    scripts/laplace-python tools/citation_migration.py --out <dir>\n"
        "and copy citation_migration.json here. A skip would let the table go stale "
        "silently, which is what it exists to prevent." % (migration,))
    payload = json.loads(migration.read_text(encoding="utf-8"))
    stale = tuple(row["cited"] for row in payload["rows"] if not row["exists_today"])
    assert stale == KNOWN_STALE_CITATIONS, stale
    for row in payload["rows"]:
        if not row["exists_today"]:
            assert row["now"], row
            path, _, number = row["now"].rpartition(":")
            lines = (TREE / path).read_text(encoding="utf-8").split("\n")
            assert 0 < int(number) <= len(lines), row
            # NOT just "the number is inside the file".  That is what this test
            # asserted first, and it passed while `note` resolved to
            # `writing_schemas.py:31` --- `literature_bind`, matched by an
            # unanchored search for `'note':` on its nested `evidence.note`
            # property, eleven lines above the real schema.  A table the synthesis
            # lane APPLIES has to be wrong-able: the line must hold the fact the
            # row's own `why` names.
            live = lines[int(number) - 1]
            holds = row["now_holds"]
            assert holds and row["now_fact"], row
            # ANCHORED.  `holds in live` is not enough and this is the whole point:
            # `'note':` IS inside line 31, `literature_bind`, as its nested
            # `evidence.note` property --- the very line the unanchored search
            # returned.  The resolved line must BEGIN with the top-level key, and the
            # fact it names must be the fact the row's own `why` names.
            assert live.startswith(holds), (row, live[:120])
            assert row["now_fact"] in row["why"], row
            assert row["now_line"] == live, (row["now_line"][:80], live[:80])


# ----------------------------------------------------- the citation law, measured not asserted
def _door_citations():
    """`tools/door_citations.py` loaded by path: the measurement lives in the tool a reader
    can run, and this proof is the gate on it, so there is one implementation of the sweep."""
    import importlib.util                                         # noqa: PLC0415
    path = TREE / "tools" / "door_citations.py"
    assert path.is_file(), "the door-citation sweep is part of this tree, not of a report"
    spec = importlib.util.spec_from_file_location("door_citations", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.measure(d.BASE_REVISION)


def _tool(name: str):
    """Any instrument in `tools/`, loaded by path, so a proof and a reader run one copy."""
    import importlib.util                                         # noqa: PLC0415
    path = TREE / "tools" / name
    assert path.is_file(), "%s is part of this tree, not of a report" % name
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_two_rule_counts_reconcile():
    """Two instruments in this tree print a thing called `rule_instances` and print different
    numbers --- 316 from `tools/whole_figures.py`, 317 from `tools/door_citations.py` --- and
    a report that quotes one without the other leaves a reader to re-derive the difference.
    They count different sets, and the difference is exact arithmetic, held here: every rule
    that carries a typed coordinate (tool AND http declarations), plus each declaration's
    `turn_door` and each HTTP declaration's `header_door`, which are declaration fields rather
    than `Rule` rows and are why a `turn_bound` kind appears in one instrument's tally and not
    in the other's `rule_kinds`."""
    figures = _tool("whole_figures.py").figures()
    sweep = _door_citations()["summary"]
    assert figures["rule_instances"] == sum(figures["rule_kinds"].values())
    assert (figures["rule_instances_with_a_typed_coordinate"]
            + figures["turn_doors"] + figures["header_doors"]
            == sweep["rule_instances"]), (figures, sweep["rule_instances"])
    assert (figures["rule_instances"] + figures["rule_instances_http_declarations"]
            == figures["rule_instances_with_a_typed_coordinate"]
            + figures["rule_instances_without_a_typed_coordinate"])
    assert "turn_bound" not in figures["rule_kinds"]      # the kind that is not a Rule kind


def test_the_identity_door_expiry_figure_is_the_count_the_tree_holds():
    """`tools/whole_figures.py` published `identity_doors_with_an_expiry: 0` because it
    iterated the `DOORS` dict BY KEY and asked a `str` for an `expiry`, while every shim row
    carried `identity_doors.EXPIRY` (src/laplace/identity_doors.py:57).  The figure was wrong
    and the tree was right, and nothing held the two together.  This does: the instrument's
    count must equal the count the module holds, and no row may be missing an expiry ---
    which is what `Shim.__post_init__` and `test_identity_doors.py` already refuse at the
    other end, so a published zero can no longer survive a green suite."""
    from laplace.core import identity_doors                            # noqa: PLC0415
    figures = _tool("whole_figures.py").figures()
    rows = list(identity_doors.DOORS.values())
    assert rows, "the shim table is empty; this proof would vacate"
    assert figures["identity_doors_declared"] == len(rows), figures["identity_doors_declared"]
    assert figures["identity_doors_with_an_expiry"] == sum(1 for row in rows if row.expiry)
    assert figures["identity_doors_with_an_expiry"] == len(rows), (
        "the instrument reports %d of %d rows with an expiry; a shim with none is what "
        "grammar.Shim.__post_init__ refuses"
        % (figures["identity_doors_with_an_expiry"], len(rows)))
    assert figures["identity_door_expiry"] == identity_doors.EXPIRY


def test_the_acts_block_is_a_shim_with_an_evaluable_expiry():
    """The acts block is the second shim this module ships, and it spent this whole campaign
    without a trigger while the cap comment above claimed it had one.  It is held to the same
    bar as `BASE_REVISION_EXPIRY`: a date, the word `parity`, and the NAME OF THE INSTRUMENT
    that decides it --- and then the instrument is run here, so the trigger is evaluated and
    not only read.  `caller_doors_publishing_the_whole_mapping` is 0 today; the day some door
    publishes the whole (verb, concept) table this proof goes red and 11,743 characters of
    help are given back, which is what makes it an expiry rather than a wish."""
    assert re.search(r"20\d\d-\d\d-\d\d", d.ACTS_BLOCK_EXPIRY), d.ACTS_BLOCK_EXPIRY
    assert "parity" in d.ACTS_BLOCK_EXPIRY.lower(), d.ACTS_BLOCK_EXPIRY
    assert "acts_block_expiry" in d.ACTS_BLOCK_EXPIRY, (
        "the trigger must name the instrument that decides it, not a feeling")
    report = _tool("acts_block_expiry.py").measure()
    assert report["expiry"] == d.ACTS_BLOCK_EXPIRY
    # the block is actually in the responses it is priced against: whole in the complete rendering, and served by
    # default at a smaller cost since D2 (long act lists are one exact `section: acts` read away)
    assert report["acts_block_full_chars"] > 10000, report["acts_block_full_chars"]
    assert 0 < report["acts_block_chars"] < report["acts_block_full_chars"], report
    for operation in sorted(DECLARATIONS):
        assert d.help_payload(operation, permitted=True)["acts"], operation
    # and the condition that retires it is still false, measured
    assert report["caller_doors_publishing_the_whole_mapping"] == 0, (
        "a caller can now read the whole mapping from %r, so the per-operation acts block "
        "is retirable: delete it and give back %d characters (d.ACTS_BLOCK_EXPIRY)"
        % (report["doors_that_publish_it"], report["acts_block_chars"]))
    assert report["mapping_file_is_readable_by_a_caller"] is False, (
        "mapping.csv has left tests/; the block's reason for existing is gone")
    assert 0 < report["closest_door"]["pairs"] < report["closest_door"]["of"]
    # AND THE NUMBER IS NOWHERE TYPED EXCEPT AS THIS NUMBER.  Three shipped files quote the
    # closest door's count in prose; until the closing read of 2026-10-02 all three said 73
    # --- the catalogue's ROW count --- while this instrument printed 67, the distinct pairs,
    # and nothing compared them.  Every `<n> of <the live pair count>` in the three is now
    # asserted equal to what the tool prints, so prose cannot drift from the instrument that
    # decides the shim.  The SECOND number is read from the instrument, not typed here either
    # (S2 settings-three-ways, 2026-10-05: it moved 104 -> 105 the same day this test would
    # otherwise have had to be hand-edited to match it -- the live value is the one thing
    # this proof must not itself hardcode).
    quoted = {}
    live_pairs = str(report["distinct_verb_concept_pairs"])
    for rel in ("src/laplace/native/declarations.py", "tools/acts_block_expiry.py"):
        text = (TREE / rel).read_text(encoding="utf-8")
        # This is the catalogue-pair figure, not every N-of-M in the file.
        # The independent source-coordinate census can have the same denominator.
        paragraph = re.search(r"closest[^\n]*(?:\n[^\n]*){0,2}", text)
        found = re.findall(r"(\d+) of (?:the )?(" + re.escape(live_pairs) + r")\b",
                           paragraph.group(0) if paragraph else "")
        assert found, (
            "%s no longer quotes the closest door's count. If the number was deleted rather "
            "than fixed, drop the file from this list; a quoted number with nothing asserting "
            "it is the defect." % rel)
        quoted[rel] = found
        for pairs, of in found:
            assert int(of) == report["distinct_verb_concept_pairs"], (rel, of)
            assert int(pairs) == report["closest_door"]["pairs"], (
                "%s types %s of %s, tools/acts_block_expiry.py prints %d of %d. The number "
                "comes from the instrument or it is deleted."
                % (rel, pairs, of, report["closest_door"]["pairs"],
                   report["closest_door"]["of"]))
    assert len(quoted) == 2, quoted


def test_every_typed_door_is_an_attributable_coordinate_in_the_campaign_base():
    """`Rule.door` is typed, and this campaign moves lines.  Two things are therefore
    measured rather than asserted: that every coordinate is in range at the base it names,
    and that every IDENTITY coordinate is attributable there --- the base line names the
    field, or the grammar's own home mints the value at that line.  Residual 4's number
    (coordinates whose line holds other code in the tree that ships them) is printed by the
    same sweep, which is why `help` renders a typed coordinate with the commit it is in."""
    report = _door_citations()
    summary = report["summary"]
    assert summary["coordinates_out_of_range_at_base"] == []
    assert summary["coordinates_invalid_at_declared_source"] == []
    assert report["identity_instances_unattributable_at_base"] == [], (
        "an identity rule's door neither names its field at the base nor is the line the "
        "grammar's home mints the value at: %r"
        % ([(row["operation"], row["field"], row["door"])
            for row in report["identity_instances_unattributable_at_base"]],))
    # the drift the law exists for, measured here so the report's figure cannot go stale
    assert summary["coordinates_whose_line_holds_other_code_in_the_shipped_tree"] > 0, (
        "if this is zero the typed coordinates no longer drift and `cited()` can be retired "
        "(residual 4)")
    assert summary["distinct_door_coordinates"] >= 70
    # Current figures have one owner. Source explains provenance and points to
    # the executable census; it must not reintroduce mutable numeric copies.
    source = (TREE / "src/laplace/native/declarations.py").read_text(encoding="utf-8")
    assert "Current coordinate coverage and drift are measured by tools/door_citations.py" in source
    assert not re.search(r"costs \(\d+ of \d+ coordinates|on this merged tree, \d+ of|WHOLE-SYSTEM figures",source)


def test_a_rendered_coordinate_always_says_which_tree_it_is_a_coordinate_in(tmp_path):
    """A caller is never sent to a line in the tree they are holding.  Every typed
    coordinate `help` renders carries `@<base>`; `handler`, which is resolved from the door's
    own text at render time, carries none, and `line_numbers` says which is which."""
    marked = 0
    for operation in sorted(DECLARATIONS):
        value = d.help_payload(operation, permitted=True)
        assert value["line_numbers"] == d.COORDINATE_LAW
        assert d.BASE_REVISION in value["line_numbers"]
        assert "@" not in value["handler"], "a resolved handler names THIS tree"
        for found in re.findall(r'"?enforced_at"?: ?"([^"]+)"', json.dumps(value)):
            assert (found.endswith("@" + d.BASE_REVISION)
                    or re.search(r"@sha256:[0-9a-f]{64}$", found)), (operation, found)
            marked += 1
    assert marked >= 60, marked         # measured: 60 of the 73 declare at least one rule
    for route in sorted(row["route"] for row in d.http_catalogue()):
        value = d.http_help(route)
        assert value["line_numbers"] == d.COORDINATE_LAW
        for found in re.findall(r'"enforced_at": ?"([^"]+)"', json.dumps(value)):
            assert (found.endswith("@" + d.BASE_REVISION)
                    or re.search(r"@sha256:[0-9a-f]{64}$", found)), (route, found)


def test_the_base_revision_is_one_constant_with_one_expiry():
    """Three files name the campaign base, and the THIRD is the one that ships.  The
    previous round checked the two installed spec files and skipped `writing_declarations.py`
    itself, which is the module that renders the marker into every response --- a shim in
    production with no expiry, which is exactly what `tests/test_grammar.py:400` calls the
    mapping file this grammar refuses.  All three are checked here: the grammar's own expiry
    form is a trigger and a date, and `BASE_REVISION_EXPIRY`'s trigger is a number
    `tools/door_citations.py` prints, so it can be evaluated and not only read."""
    suite = (TREE / "tests" / "test_grammar.py").read_text(encoding="utf-8")
    census = (TREE / "tests" / "grammar_spec" / "by_census.py").read_text(encoding="utf-8")
    assert re.search(r"20\d\d-\d\d-\d\d", d.BASE_REVISION_EXPIRY), d.BASE_REVISION_EXPIRY
    assert "parity" in d.BASE_REVISION_EXPIRY.lower(), d.BASE_REVISION_EXPIRY
    assert "door_citations" in d.BASE_REVISION_EXPIRY, (
        "the trigger must name the instrument that decides it, not a feeling")
    for text, name in ((suite, "tests/test_grammar.py"),
                       (census, "tests/grammar_spec/by_census.py")):
        assert 'CAMPAIGN_BASE = "%s"' % d.BASE_REVISION in text, name
        expiry = re.search(r'CAMPAIGN_BASE_EXPIRY = \(?\s*"(.+?)"\s*\)?\n', text, re.S)
        assert expiry, "%s names the base with no expiry on the mechanism" % name
        whole = re.search(r"CAMPAIGN_BASE_EXPIRY = (.+?)\n(?=[A-Z_]|\n)", text, re.S).group(1)
        assert re.search(r"20\d\d-\d\d-\d\d", whole), name      # a review date
        assert "parity" in whole.lower(), name                  # and the run that retires it


EXAMPLE_START = "# RUNNABLE EXAMPLE"
EXAMPLE_END = "# END RUNNABLE EXAMPLE"


def runnable_example(text: str) -> str:
    """The docstring's example as source: the lines between the markers, dedented, and
    nothing else done to them.  The previous version of this proof rewrote `declare(` into
    `d.Declaration(operation=` and substituted the `says="..."` placeholder before
    executing, so the docstring's claim that the call was "executable as written, and it was
    run" was true of the rewrite and false of the text a lane copies."""
    after = text.split(EXAMPLE_START, 1)[1].split("\n", 1)[1]
    return textwrap.dedent(after.split(EXAMPLE_END, 1)[0])


def test_the_module_docstring_example_runs_verbatim():
    """The docstring is the one place a lane reads before writing a declaration, so what it
    shows is compiled here EXACTLY as it stands, in a namespace that holds nothing --- its
    own two import lines have to work, which is the other half of what was wrong: `SCHEMAS`
    was not importable from this module at all.  Round 3's version showed the deleted
    `handler` keyword; the version before this one showed a `declare` call that raises
    `ValueError: already declared` in every process that has imported the module."""
    text = d.__doc__
    assert "handler=" not in text, (
        "the docstring names the deleted keyword; a lane following it writes a TypeError")
    assert text.count(EXAMPLE_START) == 1 and text.count(EXAMPLE_END) == 1, (
        "one marked example, so there is one text and it is the one that runs")
    source = runnable_example(text)
    assert "Declaration(" in source and "SCHEMAS[" in source, source
    namespace: dict = {}
    exec(compile(source, "<writing_declarations docstring>", "exec"), namespace)  # noqa: S102
    built = namespace["declaration"]
    # The verb is NOT in the example and cannot be: `declare` refuses a declaration that
    # states its act, so what the example builds must agree with the route table.
    from laplace.native import verbs as writing_verbs
    assert built.operation == "section_change"
    assert built.acts == writing_verbs.pairs_for("section_change")
    assert built.verb in g.VERBS and built.concept in {c for _, c in built.acts}
    assert built.handler == d.dispatch_site("section_change")     # resolved, never typed
    assert built.rules[0].rendered()["enforced_at"].endswith("@" + d.BASE_REVISION)
    with pytest.raises(TypeError):
        d.Declaration(operation="section_change", verb="create", concept="heading@section",
                      payload=SCHEMAS["section_change"],
                      handler="src/laplace/writing/operations.py:230")


def test_deployed_contract_text_retains_nonempty_owner_semantics():
    for operation, declaration in d.DECLARATIONS.items():
        assert isinstance(declaration.does, str) and declaration.does.strip(), operation
        for rule in declaration.rules:
            assert isinstance(rule.says, str) and rule.says.strip(), operation
