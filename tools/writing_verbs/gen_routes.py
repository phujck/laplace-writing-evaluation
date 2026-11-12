#!/usr/bin/env python3
"""Generate ``src/laplace/writing_verbs.ROUTES`` from the grammar packet's mapping.csv.

Row source: ``tests/grammar_spec/mapping.csv`` (installed by GRAMMAR.md §8 into the
worktree, so an edit in the grammar packet shows up as a diff here and not as a silently
changed result underneath the lane).  The owner call and its file:line are read out of
``src/laplace/writing/operations.py`` itself, so a citation in the shipped table cannot rot
without the regeneration test failing.

Usage:  scripts/laplace-python tools/writing_verbs/gen_routes.py --tree . [--check]
"""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import re
import runpy
import sys
import subprocess
from pathlib import Path

_anchors = runpy.run_path(str(Path(__file__).with_name("reanchor_http_routes.py")))
resolve_site, scoped_nodes = _anchors["resolve_site"], _anchors["scoped_nodes"]

# The payload key that distinguishes two routes sharing one (verb, concept), keyed by
# (verb, concept, the selector value that names the old sub-verb).  Each entry carries the
# measurement that shows it; an undeclared collision is NOT guessed -- the route stays
# reachable through its old name and is marked `door="shim"` with its reason, and `choose`
# raises `Ambiguous` rather than picking.
WHEN: dict[tuple[str, str, str], tuple[tuple[str, str], ...]] = {
    ("run", "task@project", "dispatch_continue"): (("packet", ""),),
    # Prepared Work is the existing task act qualified by an inspected source
    # selection and exact plan-section IDs; neither ordinary task creation nor
    # dispatch-plan creation accepts that input pair.
    ("create", "task@project", "prepare_work"): (("expected_selection", ""), ("section_ids", "")),
    # manuscript_structure.change normalises nine audited sub-verbs to five real ones at
    # src/laplace/manuscript/manuscript_structure.py:1043-1044.  What is left to choose at one verb is
    # create against restore and delete against undo-create, and both reversals carry the
    # receipt the owner hands back (writing_contracts.py:71, :76).
    ("create", "section@section", "restore"): (("receipt_id", ""),),
    ("delete", "section@section", "undo-create"): (("receipt_id", ""),),
    # block_change: "insert uses a line boundary; use insert-at-caret for paragraph
    # splitting" -- writing_contracts.py:88, enforced at manuscript_blocks.py:187, :196.
    ("create", "block@paragraph", "insert-at-caret"): (("destination.paragraph", ""),),
}

#: A selector key that is a PROJECTION or PARAMETER of the ask, not the name of the act.
#: These stay in the payload: GRAMMAR.md §4 puts specialisation in the concept's payload
#: schema, and `view=summary` against `view=audit` is two projections of one home, not two
#: verbs.  `operation=` and `op.kind=` are the opposite -- they name the act, which the
#: verb and the concept now name, so they are lifted out.
KEEP_SELECTOR = {"family", "scope", "view", "mode", "action", "basis", "status", "kind"}

#: The guards whose door compares through ``revision_identity.revision_matches``
#: (src/laplace/revision_identity.py:9-23), which accepts the owner's ``sha256:``-prefixed
#: spelling and the bare one as the same value.  The grammar's token normalises to the bare
#: spelling (GRAMMAR.md §1), so for these guards -- and only these -- the rebuilt owner call
#: is the same call by the owner's own comparator.  Every other guard is compared raw by its
#: door, so the rewrite must not change its spelling, and a row that spelled it with the
#: prefix falls through to its own payload instead.
SPELLING_TOLERANT = {
    ('writing_stage', 'known_revision'): 'src/laplace/writing/stages.py:81',
    ("structure_change", "expected_revision"): "src/laplace/manuscript/project_structure.py:766",
    ("structure_change", "expected_source_revision"): "src/laplace/manuscript/project_structure.py:777",
    ("structure_change", "expected_concept_revision"): "src/laplace/manuscript/project_structure.py:853",
    ("concept_change", "base_revision"): "src/laplace/research/concepts.py:846",
    ("concept_change", "mutation_revision"): "src/laplace/research/concepts.py:1041",
    ("logical_plan_change", "base_revision"): "src/laplace/research/concepts.py:1041",
    ("proof_check", "concept_revision"): "src/laplace/pipeline/formal_verification.py:267",
    ("proof_check", "source_revision"): "src/laplace/pipeline/formal_verification.py:269",
    ("visual_create", "expected_revision"): "src/laplace/pipeline/visual_production.py:139",
    ("literature_bind", "claim_revision"): "src/laplace/research/literature.py:395",
    ("propose_revision", "content_revision"): "src/laplace/manuscript/proposal_basis.py:219",
}

#: Guards the audit's verb matrix does not attribute to an operation, but which that
#: operation's payloads really carry (measured on the recorded corpus; the count is in the
#: lane report).  The home is the grammar's own census entry for the name.
ADDED_GUARDS = {
    # None means the current owner's registered home, not a second authored mapping.
    "visual_place": (("base_revision", None, "digest", True),
                     ("expected_source_revision", None, "digest", True)),
    "visual_create": (("expected_revision", "visual-spec", "digest", True),),
    # The ONE span guard of the content tree.  apply_revision and the editor's rewrite door
    # compare the same thing -- the exact previous text of the addressed span
    # (src/laplace/manuscript/review_surface.py:1860) -- and the audit's matrix attributes `before` to
    # neither, which is why "change a paragraph" had no declared identity at all.
    "apply_revision": (("before", "prose", "text", True),),
}


def owner_guard_homes(tree: Path) -> dict:
    """Read the target tree's actual owner registry, isolated from import caches."""
    code = """import sys,json
sys.path.insert(0,sys.argv[1])
from laplace.core.identity_doors import DOORS
rows={}
for shim in DOORS.values():
    for name,homes in shim.guard_to_home.items():
        key=shim.old_operation+'/'+name
        rows.setdefault(key,set()).update(homes.split('|'))
print(json.dumps({key:'|'.join(sorted(value)) for key,value in rows.items()}))
"""
    return json.loads(subprocess.check_output(
        [sys.executable, "-c", code, str(tree / "src")], text=True))

#: What the OWNER does when a kept selector key is absent, with the line that does it.  A
#: route whose kept value is the owner's default also matches a payload that omits the key,
#: so a caller that does not spell the default still gets the right concept in its row.
DEFAULTS = {
    ("profile", "view"): ("summary", "src/laplace/manuscript/profiles.py:221", "spelled"),
    # (value, the line that applies it, HOW). `spelled` means the cited line writes the default
    # itself; `else-branch:<other>` means the owner has no default and sends everything that is
    # not <other> to this read, so the mapping's name for that read is the default by
    # construction. Each one was read in the owner, and
    # `test_every_selector_default_is_the_line_it_cites` checks the cited line still says so.
    # Three were wrong on the first pass -- two line numbers off by one branch, and
    # `writing_stage` declared "summary" where src/laplace/writing/stages.py:60 defaults to
    # "guidance" -- which is the same defect this lane reports against the audit's own matrix.
    ("repository", "action"): ("list", "src/laplace/projects/writing_sources.py:282", "spelled"),
    ("pipeline", "view"): ("summary", "src/laplace/writing/operations.py:237", "spelled"),
    ("writing_stage", "view"): ("guidance", "src/laplace/writing/stages.py:60", "spelled"),
    # research family R1 (2026-10-19): the native door calls the catalogue owner's state_read directly, and that
    # owner's own `view == 'result'` branch is the else-branch; everything else is the default read.
    ("research", "view"): ("summary", "src/laplace/research/research_catalogue.py:554", "else-branch:result"),
    ("writing_style", "view"): ("summary", "src/laplace/manuscript/writing_style.py:250", "spelled"),
    ("author_history", "view"): ("corrections", "src/laplace/writing/operations.py:342", "spelled"),
    ("logical_plan", "view"): ("attention", "src/laplace/writing/operations.py:418", "else-branch:catalog"),
    ("export_pdf", "mode"): ("selected-source", "src/laplace/writing/operations.py:205", "spelled"),
    # NOT here, because the owner REQUIRES the key and refuses without it: experiment_run's
    # `mode` ("producer_id and explicit mode ('smoke' or 'full') are required", a recorded
    # refusal in the corpus) and writing_style_profile_change's `basis`
    # (src/laplace/manuscript/writing_style.py:438 lists it as required, :373 is the refusal). A payload
    # without them names no route, falls through, and the owner refuses as it always did.
}

#: Old spellings the OWNER itself normalises, cited.  The rewrite canonicalises them; the
#: round trip is then not byte-exact for a row that used the alias, so that row's live call
#: falls through to its own payload and the count is reported rather than hidden.
ALIASES = {
    ("section_change", "create-section"): ("create", "src/laplace/manuscript/manuscript_structure.py:change"),
    ("section_change", "delete-section"): ("delete", "src/laplace/manuscript/manuscript_structure.py:change"),
    ("section_change", "restore-section"): ("restore", "src/laplace/manuscript/manuscript_structure.py:change"),
}

#: The unsplit ancestor the mapping keeps for a row the grammar splits by a payload enum.
#: GRAMMAR.md §3 splits note_status by the enum its door enforces
#: (writing_contracts.py:439, pipeline/authoring.py:1191-1192), so the ancestor would
#: shadow `status=open`.
DROP_ANCESTOR = {("note_status", "note_status")}

GUARD_FORM = {
    # pipeline/authoring.py:398-399 compares an INTEGER counter, not a digest.
    "authoring-state": "counter",
}
#: `before` is TEXT at every home that compares it (review_surface.py:1860 compares the
#: span, manuscript_blocks.py:166 the whole file), and a pagination cursor at
#: conversation_history (writing_contracts.py:386).
# Payload owner annotations decide each carrier's form, never its field name alone.
def owner_guard_form(operation, field, forms=None):
    if forms is not None:return forms.get(operation+'/'+field)
    from laplace.writing.schemas import declared_guard_form
    return declared_guard_form(operation,field)


def owner_guard_forms(tree:Path):
    """Use the target tree's typed owner declarations, isolated from import caches."""
    code="""import sys,json
sys.path.insert(0,sys.argv[1])
from laplace.writing.schemas import FIELD_VALUE_SEMANTICS,declared_guard_form
pairs={(op,path.split('.')[-1]) for op,path in FIELD_VALUE_SEMANTICS}
print(json.dumps({op+'/'+name:declared_guard_form(op,name) for op,name in pairs}))
"""
    return json.loads(subprocess.check_output([sys.executable,'-c',code,str(tree/'src')],text=True))


CURSOR = {("conversation_history", "before")}


def parse_selector(operation_cell: str, old_verb: str) -> tuple[str, tuple[tuple[str, str], ...]]:
    """`structure_change operation=plan` + `op.kind=add-section` -> base op + two pairs."""
    selector: list[tuple[str, str]] = []
    base = operation_cell.strip()
    if " " in base:
        base, _, carried = base.partition(" ")
        for part in carried.split():
            key, _, value = part.partition("=")
            selector.append((key.strip(), value.strip()))
    verb = old_verb.strip()
    if "=" in verb:
        key, _, value = verb.partition("=")
        selector.append((key.strip(), value.strip()))
    return base, tuple(selector)


def parse_guards(operation: str, guards_cell: str, homes_cell: str, forms=None):
    names = [n for n in (guards_cell or "").split("/") if n and n != "-"]
    homes = (homes_cell or "").split("/") if homes_cell and homes_cell != "-" else []
    out = []
    for index, name in enumerate(names):
        home = homes[index].strip() if index < len(homes) else ""
        if not home or home.startswith("NONE"):
            if (operation, name) in CURSOR:
                out.append((name, "", "cursor", True))
            elif owner_guard_form(operation,name,forms) in ("text","cursor"):
                out.append((name, "", owner_guard_form(operation,name,forms), True))
            continue
        optional = home.endswith("?")
        home = home.rstrip("?")
        form = owner_guard_form(operation,name,forms) or GUARD_FORM.get(home.split("|")[0], "digest")
        out.append((name, home, form, optional))
    return tuple(out)


#: A HANDLER line: a whole `if` whose only condition is the operation's name (one or more
#: alternatives).  Anchored and whole-line on purpose: `elif operation=="store_artifact":`
#: inside the response compactor and `if operation=="concept" and value.get(...)...:` inside
#: the read post-processing both LOOK like handlers to a substring search, and attributing an
#: owner to one of them ships a citation that points at the wrong code.
BRANCH = re.compile(
    r"""^\s*if\s+operation\s*==\s*["']([a-z_]+)["']"""
    r"""(?:\s+or\s+operation\s*==\s*["']([a-z_]+)["'])*\s*:\s*$""")
BRANCH_SET = re.compile(r"""^\s*if\s+operation\s+in\s+\{([^}]*)\}\s*:\s*$""")
#: What the test asserts a cited line still is.
HANDLER_LINE = re.compile(
    r"""^\s*(?:if\s+operation\s*(?:==|in)|["'][a-z_]+["']\s*:\s*\()""")
ROUTE_ROW = re.compile(r"""^\s*["']([a-z_]+)["']\s*:\s*\(([a-z_]+)\s*,\s*(.+?),\s*["'](GET|POST)["']\)""")
#: The same row, wrapped: the module on the first line and the path on the next.
ROUTE_OPEN = re.compile(r"""^\s*["\']([a-z_]+)["\']\s*:\s*\(([a-z_]+)\s*,\s*$""")
# Artifact operations now have explicit adapters into writing.artifacts. No
# deployed operation needs a membership exception; validation guards refuse it.
MEMBERSHIP_DISPATCH = {}
RETURN = re.compile(r"^\s*return\s+(.+)$")


#: operation -> HOW its dispatch line was found: `branch` (its own `if operation ==`),
#: `routes-table` (a row of the surface `routes` table), `membership` (an `operation in {...}`
#: line, which is usually a VALIDATION guard and not a dispatch) or `branch-answers-in-place`.
#: Emitted into the generated block so a test can refuse a `membership` citation: ten
#: declarations shipped `handler='src/laplace/native/tools.py:301'`, the unknown-field
#: validation set, as the line that routes them.
SITE_HOW: dict[str, str] = {}

#: The HTTP door's rows are not retired by the tool door's replay, so they carry their own
#: condition.  Parity for them is the eight HTTP rows of the arrival source.
HTTP_EXPIRY = ("not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and "
               "the browser delivery gate stop covering it; review 2026-11-01")


def owner_sites(tools: Path) -> dict[str, tuple[str, int]]:
    """operation -> (the owner call _execute makes, its line in writing/operations.py).

    Three passes, in this order, because the priority is load-bearing: a single-operation
    branch is the handler; the ``routes`` table is the handler for the 35 surface operations;
    and an ``operation in {...}`` membership test is usually a VALIDATION guard, not a
    handler -- taking it first attributed `concept_change` to `document_style.status` at
    writing_tools.py:573, which is the `if operation in {...}` line that forbids a review
    mode.  So a set branch is only used when nothing better names the operation.
    """
    lines = tools.read_text().splitlines()

    # SCOPED TO `_execute`, measured on the whole-system merge.  Unscoped, pass 1 answered
    # `literature_discover` with writing_tools.py:942, which is `if operation ==
    # "literature_discover":` inside `read_output_digest` -- a digest branch over a result
    # already produced, not the dispatch.  Its dispatch is the routes-table row at :599, which
    # pass 2 would have found.  The same class as the `:324` attribution this docstring already
    # records, and the same class as the one `writing_declarations.dispatch_site` had on
    # `store_artifact` (:958, inside `_compact_write_response`).  Only `_execute` dispatches,
    # so only `_execute` is read.  `tools/handler_resolvers.py` compares the two resolvers.
    # S1 B8: the region is `_execute` and its contiguous `_execute_<family>` dispatchers,
    # exactly writing_declarations._dispatch_span.
    span_first = span_last = 0
    for number, line in enumerate(lines, 1):
        if line.startswith("def _execute("):
            span_first = number
        elif span_first and line[:1] not in ("", " ", "\t", "#") and not line.startswith("def _execute_"):
            span_last = number - 1
            break
    if not span_last:
        span_last = len(lines)
    lines = [line if span_first <= number <= span_last else ""
             for number, line in enumerate(lines, 1)]

    def owner_after(number: int) -> str:
        for ahead in lines[number:number + 25]:
            got = RETURN.match(ahead)
            if got:
                return got.group(1).strip()[:120]
        return ""

    found: dict[str, tuple[str, int]] = {}
    for number, line in enumerate(lines, 1):              # 1. one operation, one branch
        match = BRANCH.match(line)
        if not match:
            continue
        owner = owner_after(number)
        for name in re.findall(r"""["']([a-z_]+)["']""", line):
            if name not in found and owner:
                found[name] = (owner, number)
                SITE_HOW[name] = "branch"
    for number, line in enumerate(lines, 1):              # 2. the surface route table
        # Joined with the next line when the row is wrapped: `concept` and `logical_plan`
        # choose their path with a conditional and spill onto a second line, so a one-line
        # regex found neither, `logical_plan` shipped `site=''`, and a declaration could
        # derive no handler from it at all (`ValueError: the table names no dispatch line
        # for 'logical_plan'`, the first run of this synthesis).
        joined = line
        if ROUTE_OPEN.match(line) and not ROUTE_ROW.match(line):
            joined = line.rstrip() + " " + "".join(lines[number:number + 1]).strip()
        got = ROUTE_ROW.match(joined)
        if got and got.group(1) not in found:
            module, route, method = got.group(2), got.group(3).strip(), got.group(4)
            found[got.group(1)] = (("%s.handle(%s, %s)" % (module, route, method))[:120], number)
            SITE_HOW[got.group(1)] = "routes-table"
    for number, line in enumerate(lines, 1):              # 3. last: a membership test
        match = BRANCH_SET.match(line)
        if not match:
            continue
        for name in re.findall(r"""["']([a-z_]+)["']""", match.group(1)):
            if name in found:
                continue
            owner = owner_after(number)
            if owner:
                found[name] = (owner, number)
                SITE_HOW[name] = "membership"
    for number, line in enumerate(lines, 1):              # 4. a branch with no `return`
        # `source` is the one: its branch at writing_tools.py:264 builds its answer in place
        # and falls out of the block, so pass 1 found no owner call for it and the route
        # table shipped `site=''` --- a declaration cannot derive a handler from that.  The
        # branch line IS the dispatch, so it is the citation, and `how` says what it is.
        match = BRANCH.match(line)
        if not match:
            continue
        for name in re.findall(r"""["']([a-z_]+)["']""", line):
            if name not in found:
                found[name] = ("operations._execute (answers in place)", number)
                SITE_HOW[name] = "branch-answers-in-place"
    # The moved artifact owner declares its exact adapter and implementation.
    # Runtime help uses this same resolver; no guard substring can impersonate
    # the dispatch, and missing/ambiguous/delegation drift refuses generation.
    from laplace.projects.artifacts import declaration_sites
    declared = declaration_sites(tools.read_text(),
                                 (tools.parents[1] / "projects" / "artifacts.py").read_text())   # the artifact owner (projects/)
    for operation, row in declared.items():
        found[operation] = (row["owner"], int(row["handler"].rsplit(":", 1)[1]))
        SITE_HOW[operation] = row["how"]
    return found


# Declaration values/how remain authored. Citation lines are derived from these
# precise owner scopes, never from a nearby text window or the old line number.
_DEFAULT_FUNCTIONS = {"repository":"_validate_payload", "writing_stage":"inspect",
                      "writing_style":"inspect", "profile":"inspect", "research":"state_read"}


def _payload_get(node, key, default=None):
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "payload"
            and node.func.attr == "get" and len(node.args) == (1 if default is None else 2)
            and isinstance(node.args[0], ast.Constant) and node.args[0].value == key
            and (default is None or isinstance(node.args[1], ast.Constant)
                 and node.args[1].value == default))


def _comparison(node, name, value):
    return (isinstance(node, ast.Compare) and len(node.ops) == 1
            and isinstance(node.ops[0], ast.Eq) and len(node.comparators) == 1
            and isinstance(node.left, ast.Name) and node.left.id == name
            and isinstance(node.comparators[0], ast.Constant) and node.comparators[0].value == value)


def check_defaults(tree: Path) -> dict:
    """Resolve exact owner default anchors; refuse drift rather than guessing a cite."""
    parsed = {}
    resolved = {}
    for (operation, key), (value, cite, how) in sorted(DEFAULTS.items()):
        where = cite.rpartition(":")[0]
        if where not in parsed:
            parsed[where] = ast.parse((tree / where).read_text(encoding="utf-8"))
        function = _DEFAULT_FUNCTIONS.get(operation, "_execute")
        functions = [node for node in parsed[where].body
                     if isinstance(node, ast.FunctionDef) and node.name == function]
        if len(functions) != 1:
            raise AssertionError(f"{operation}: missing/ambiguous owner function {where}:{function}")
        owner = functions[0]
        # S1 B8: `_execute` dispatches through its `_execute_<family>` functions; the branch
        # (or routes table) is sought in exactly that region and must still be unique there.
        region = [owner]
        if function == "_execute":
            body = parsed[where].body
            for node in body[body.index(owner) + 1:]:
                if not (isinstance(node, ast.FunctionDef) and node.name.startswith("_execute_")):
                    break
                region.append(node)
        scope = owner
        if function == "_execute" and how == "spelled":
            branches = [(family, node) for family in region for node in family.body if isinstance(node, ast.If)
                        and _comparison(node.test, "operation", operation)]
            if len(branches) != 1:
                raise AssertionError(f"{operation}: missing/ambiguous operation branch")
            owner, scope = branches[0]
        matches = []
        if how.startswith("else-branch:"):
            # Only the actual routes assignment and this operation's tuple can
            # justify an implicit read; equal comparisons elsewhere are irrelevant.
            routes = [node.value for family in region for node in family.body if isinstance(node, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == "routes" for t in node.targets)
                      and isinstance(node.value, ast.Dict)]
            entries = [v for route in routes for k,v in zip(route.keys,route.values)
                       if isinstance(k, ast.Constant) and k.value == operation]
            if len(entries) == 1:
                other = how.split(":", 1)[1]
                for node in ast.walk(entries[0]):
                    test = node.test if isinstance(node, ast.IfExp) else None
                    if (isinstance(test, ast.Compare) and len(test.ops) == 1
                            and isinstance(test.ops[0], ast.Eq) and _payload_get(test.left,key)
                            and len(test.comparators) == 1 and isinstance(test.comparators[0],ast.Constant)
                            and test.comparators[0].value == other):
                        matches.append(test)
            elif function != "_execute":
                # an owner function's OWN else-branch: its one `<key> == <other>` test on the selector it received
                other = how.split(":", 1)[1]
                for node in ast.walk(owner):
                    test = node.test if isinstance(node, ast.If) else None
                    if (isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq)
                            and isinstance(test.left, ast.Name) and test.left.id == key
                            and len(test.comparators) == 1 and isinstance(test.comparators[0], ast.Constant)
                            and test.comparators[0].value == other):
                        matches.append(test)
        elif operation == "author_history":
            # This owner admits omitted/empty view and falls through to its
            # correction-history owner. A mentions-corrections string is no proof.
            fallback = [node for node in scope.body if isinstance(node, ast.Return)
                        and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute)
                        and isinstance(node.value.func.value, ast.Name)
                        and node.value.func.value.id == "authoring" and node.value.func.attr == "history"]
            if len(fallback) == 1:
                for node in scope.body:
                    test = node.test if isinstance(node, ast.If) else None
                    if (isinstance(test, ast.Compare) and len(test.ops) == 1
                            and isinstance(test.ops[0],ast.NotIn) and _payload_get(test.left,key)
                            and len(test.comparators) == 1 and isinstance(test.comparators[0], ast.Tuple)):
                        constants = [item.value for item in test.comparators[0].elts
                                     if isinstance(item,ast.Constant)]
                        if all(item in constants for item in (None,"",value)):
                            matches.append(test)
        else:
            for node in scoped_nodes(scope):
                if _payload_get(node,key,value):matches.append(node)
                elif (isinstance(node,ast.BoolOp) and isinstance(node.op,ast.Or)
                      and len(node.values)==2 and _payload_get(node.values[0],key)
                      and isinstance(node.values[1],ast.Constant) and node.values[1].value==value):
                    matches.append(node)
        if len(matches) != 1:
            raise AssertionError(f"{operation}: missing/ambiguous or changed {key}={value} ({how}) in {where}:{function}")
        resolved[(operation,key)] = (value, f"{where}:{matches[0].lineno}", how)
    return resolved


def check_aliases(tree: Path, declarations=None) -> dict:
    """Verify authored aliases at their unique scoped owner normalization."""
    declarations = ALIASES if declarations is None else declarations
    parsed, resolved = {}, {}
    for key, (canonical, anchor) in declarations.items():
        relative, function = anchor.rsplit(':', 1)
        if relative not in parsed:
            parsed[relative] = ast.parse((tree / relative).read_text())
        scopes = [node for node in parsed[relative].body if isinstance(node, ast.FunctionDef) and node.name == function]
        if len(scopes) != 1:
            raise AssertionError('missing/ambiguous alias owner: ' + anchor)
        matches = []
        for node in scopes[0].body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name) or node.targets[0].id != 'operation':
                continue
            value = node.value
            if not (isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)
                    and value.func.attr == 'get' and isinstance(value.func.value, ast.Dict)
                    and len(value.args) == 2 and not value.keywords
                    and all(isinstance(arg, ast.Name) and arg.id == 'operation' for arg in value.args)):
                continue
            pairs = [(k.value, v.value) for k, v in zip(value.func.value.keys, value.func.value.values)
                     if isinstance(k, ast.Constant) and isinstance(v, ast.Constant)]
            if len(pairs) != len(value.func.value.keys):
                raise AssertionError('alias normalization is not a closed literal: ' + repr(key))
            matches.extend(node.lineno for alias, target in pairs if alias == key[1] and target == canonical)
            if any(alias == key[1] and target != canonical for alias, target in pairs):
                raise AssertionError('changed alias normalization: ' + repr(key))
        if len(matches) != 1:
            raise AssertionError('missing/ambiguous alias normalization: ' + repr(key))
        resolved[key] = (canonical, f'{relative}:{matches[0]}')
    return resolved


def build(tree: Path):
    check_defaults(tree)
    aliases = check_aliases(tree)
    owner_homes = owner_guard_homes(tree)
    forms = owner_guard_forms(tree)
    mapping = tree / "tests" / "grammar_spec" / "mapping.csv"
    rows = list(csv.DictReader(mapping.read_text().splitlines()))
    sites = owner_sites(tree / "src" / "laplace" / "writing" / "operations.py")
    seen: set = set()
    routes = []
    split_parents = {r["operation"].strip() for r in rows if r["level"].strip() == "status"}
    for row in rows:
        operation_cell = row["operation"].strip()
        old_verb = row["old_verb"].strip()
        if (operation_cell, old_verb) in DROP_ANCESTOR and operation_cell in split_parents:
            continue
        base, selector = parse_selector(operation_cell, old_verb)
        verb, concept = row["verb"].strip(), row["concept"].strip()
        guards = parse_guards(base, row["old_guards"].strip(), row["homes"].strip(), forms)
        known = {name for name, _h, _f, _o in guards}
        guards = guards + tuple(
            (name, homes if homes is not None else owner_homes[base + '/' + name], form, optional)
            for name, homes, form, optional in ADDED_GUARDS.get(base, ()) if name not in known)
        owner, line = sites.get(base, ("", 0))
        alias_of = ""
        canonical = []
        for key, value in selector:
            if (base, value) in ALIASES and key not in KEEP_SELECTOR:
                target, where = aliases[(base, value)]
                alias_of = value + " -> " + target + " at " + where
                canonical.append((key, target))
            else:
                canonical.append((key, value))
        selector = tuple(canonical)
        keep = tuple((k, v) for k, v in selector if k in KEEP_SELECTOR)
        lift = tuple((k, v) for k, v in selector if k not in KEEP_SELECTOR)
        key = (verb, concept, selector, base)
        if key in seen:
            continue
        seen.add(key)
        tail = selector[-1][1] if selector else base
        routes.append(dict(verb=verb, concept=concept, operation=base, selector=selector,
                           guards=guards, owner=owner, keep=keep, lift=lift,
                           alias_of=alias_of,
                           site=("src/laplace/writing/operations.py:%d" % line) if line else "",
                           when=WHEN.get((verb, concept, tail), ())))
    # A (verb, concept) with more than one route needs the verb door to choose.  Where no
    # WHEN rule and no kept selector distinguishes them, the route stays reachable through
    # its old name only, with the reason recorded, and the pair's canonical route is the
    # one whose old name IS the operation (fewest lifted selector pairs, then alphabetical).
    by_pair: dict[tuple[str, str], list[dict]] = {}
    for route in routes:
        by_pair.setdefault((route["verb"], route["concept"]), []).append(route)
    for pair, rows_of in by_pair.items():
        for route in rows_of:
            route["door"] = "both"
        if len(rows_of) == 1:
            continue
        undecided = [r for r in rows_of if not r["when"] and not r["keep"]]
        if len(undecided) <= 1:
            continue
        undecided.sort(key=lambda r: (len(r["lift"]), r["operation"], r["lift"]))
        for route in undecided[1:]:
            route["door"] = "shim"
            route["because"] = (
                "%d routes share (%s, %s) and nothing in the payload chooses between them; "
                "reachable through its old name %s%s until a payload key is declared"
                % (len(rows_of), pair[0], pair[1], route["operation"],
                   "".join(" " + k + "=" + v for k, v in route["lift"])))
    # THE PRIMARY ACT of each operation: what `help` answers when it is asked what the
    # operation IS, and what the declaration's `verb`/`concept` are now that it states
    # neither.  In mapping.csv's own row order, because alphabetical is not an answer: it
    # made `structure_change` (26 routes) "bind claim-position@section", one of its 18 plan
    # sub-verbs.  The rule, in order: the route that needs no selector at all; else the
    # route every one of whose selector values is the owner's own default (DEFAULTS, each
    # citing the line that applies it); else the operation's FIRST row in mapping.csv, which
    # is the audit's own first-listed sub-verb.  The other acts are not lost --- they are the
    # declaration's `also` and `help`'s `acts`, the whole list, from these same rows.
    primary: dict[str, tuple[str, str, str]] = {}
    for route in routes:                                  # mapping.csv order
        operation = route["operation"]
        if operation in primary:
            continue
        how = "no-selector"
        default = next((r for r in routes if r["operation"] == operation and not r["selector"]),
                       None)
        if default is None:
            how = "owner-default"
            default = next((r for r in routes if r["operation"] == operation and r["selector"]
                            and all(DEFAULTS.get((operation, k), (None,))[0] == v
                                    for k, v in r["selector"])), None)
        if default is None:
            # The owner REQUIRES its discriminator, so the operation has no default act and
            # this one is the mapping's first row.  `help` says so in `act.chosen`, and the
            # whole list is in `acts`: a headline pair invented for such an operation would
            # be a claim the code does not make.
            how = "first-row-of-mapping.csv (the owner requires its discriminator)"
            default = route
        primary[operation] = (default["verb"], default["concept"], how)
    return routes, mapping, primary


#: The date every expiry carries.  One date, because one wave retires them; the CONDITION is
#: per route, which is the part that was missing.
REVIEW = "2026-11-01"

#: The deposited instrument that evaluates the condition.  `grammar.Shim.__post_init__` demands
#: a date and the word "parity"; what it cannot demand is that the condition be TESTABLE, and
#: one identical string on all 146 routes was an expiry in form with no measurable condition.
#: This one names the route, the run and the tool that reads the run.
RETIREMENT_TOOL = "tools/writing_verbs/shim_retirement.py"
RETIREMENT_RUN = ("evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/"
                  "parity-verb-door/rows.jsonl")


def expiry_for(row: dict) -> str:
    """This route's own retirement condition, as a sentence a reader can act on."""
    spelling = row["operation"] + "".join(" " + k + "=" + v for k, v in row["lift"])
    if row["door"] == "shim":
        return ("HELD, not retirable by this wave: %s. Retire when a payload key chooses "
                "between the routes sharing (%s, %s) AND %s reports PARITY for `%s %s` from "
                "%s; review %s"
                % (row["because"], row["verb"], row["concept"], RETIREMENT_TOOL,
                   row["verb"], row["concept"], RETIREMENT_RUN, REVIEW))
    return ("retire `%s` when %s reports RETIRABLE for `%s %s` -- i.e. when a recorded row of "
            "that route replayed through writing_tools.request() with byte PARITY against the "
            "old name in %s; review %s"
            % (spelling, RETIREMENT_TOOL, row["verb"], row["concept"], RETIREMENT_RUN, REVIEW))


def http_rows(tree: Path, tool_routes=()) -> list[dict]:
    """The HTTP door's rows of the ONE table, from tools/writing_verbs/http_routes.csv.

    The five HTTP declarations used to carry their own `verb=`, `concept=` and `handler=`,
    which is the same second copy of the table one door further out --- and one of them was
    already wrong: `authoring/providers` cited `authoring_surface.py:2619`, which holds
    `elif method == "POST" and path == "/authoring/turn":`, the TURN route.  So each row
    here declares what its cited line must hold and this generator refuses to emit a row
    whose citation does not hold it.
    """
    path = tree / "tools" / "writing_verbs" / "http_routes.csv"
    rows = []
    sources = {}
    for row in csv.DictReader(path.read_text(encoding="utf-8").splitlines()):
        site = resolve_site(tree, row, sources)
        method = row.get("method", "").strip().upper()
        assert method in {"GET", "POST"}, ("HTTP method must be GET or POST", row)
        source_operation = row.get("source_operation", "").strip()
        explicit = (row["verb"].strip(), row["concept"].strip())
        assert not (source_operation and any(explicit)), (
            "an HTTP row either derives its acts from a tool operation or states one act", row)
        if source_operation:
            pairs = []
            for route in tool_routes:
                pair = (route["verb"], route["concept"])
                if route["operation"] == source_operation and pair not in pairs:
                    pairs.append(pair)
            assert pairs, ("HTTP source_operation has no generated tool routes", source_operation)
        else:
            assert all(explicit), ("an HTTP row needs verb and concept", row)
            pairs = [explicit]
        for verb, concept in pairs:
            rows.append({"verb": verb, "concept": concept,
                         "operation": row["name"].strip(), "route": row["route"].strip(),
                         "method": method, "source_operation": source_operation,
                         "site": site, "owner": row["owner"].strip(),
                         "because": row["because"].strip()})
    return rows


def render(routes, mapping: Path, http=(), tree: Path | None = None,
           primary=None) -> str:
    out = ["ROUTES: tuple[Route, ...] = ("]
    for row in sorted(routes, key=lambda r: (r["verb"], r["concept"], r["operation"],
                                             r["selector"])):
        out.append("    Route(verb=%r, concept=%r, operation=%r,"
                   % (row["verb"], row["concept"], row["operation"]))
        out.append("          selector=%r," % (row["selector"],))
        out.append("          lift=%r," % (row["lift"],))
        if row["guards"]:
            out.append("          guards=%r," % (row["guards"],))
        if row["when"]:
            out.append("          when=%r," % (row["when"],))
        if row["door"] != "both":
            out.append("          door=%r, because=%r," % (row["door"], row["because"]))
        if row["alias_of"]:
            out.append("          alias_of=%r," % (row["alias_of"],))
        out.append("          expiry=%r," % (expiry_for(row),))
        out.append("          owner=%r," % (row["owner"],))
        out.append("          site=%r)," % (row["site"],))
    out.append(")")
    # Digested over LF-NORMALISED lines, not over the raw bytes.  The grammar packet's
    # mapping.csv carries CRLF line endings; this repository has core.autocrlf=input, so the
    # bytes in the worktree and the bytes in the committed blob can differ by 156 CR bytes
    # while the 156 rows are identical.  A raw-byte digest therefore recorded a provenance
    # that was true of the builder's working file and false of a fresh checkout, and
    # `--check` failed on the artifact the judge consumes while passing for the builder
    # (measured: working file sha256 36f0fd51..., committed blob sha256 a596903a...).  The
    # digest a provenance line owes is a digest of the ROWS, so it is taken over the lines.
    digest = hashlib.sha256("\n".join(mapping.read_text().splitlines()).encode()).hexdigest()
    out.append("HTTP_ROUTES: tuple[Route, ...] = (")
    for row in sorted(http, key=lambda r: (r["route"] != "*", r["route"], r["method"], r["operation"])):
        out.append("    Route(verb=%r, concept=%r, operation=%r,"
                   % (row["verb"], row["concept"], row["operation"]))
        out.append("          door='http', route=%r, method=%r, source_operation=%r, because=%r,"
                   % (row["route"], row["method"], row["source_operation"], row["because"]))
        if row['operation']=='authoring/proposal-preview':out.append("          when=(('id', ''),),")
        if row['operation']=='projection/source':out.append("          when=(('view', 'source'), ('corpus', ''), ('file', '')),")
        if row['operation']=='authoring/proposal-decision':out.append("          when=(('decision', ''),),")
        out.append("          expiry=%r," % (HTTP_EXPIRY,))
        out.append("          owner=%r," % (row["owner"],))
        out.append("          site=%r)," % (row["site"],))
    out.append(")")
    out.append("KEEP_SELECTOR = %r" % (sorted(KEEP_SELECTOR),))
    out.append("SELECTOR_ALIASES = {")
    for (op, alias), (canonical, where) in sorted((check_aliases(tree) if tree is not None else ALIASES).items()):
        out.append("    (%r, %r): (%r, %r)," % (op, alias, canonical, where))
    out.append("}")
    out.append("SPELLING_TOLERANT = {")
    for (op, guard), cite in sorted(SPELLING_TOLERANT.items()):
        out.append("    (%r, %r): %r," % (op, guard, cite))
    out.append("}")
    out.append("SELECTOR_DEFAULTS = {")
    for (op, key), entry in sorted((check_defaults(tree) if tree is not None else DEFAULTS).items()):
        out.append("    (%r, %r): %r," % (op, key, entry))
    out.append("}")
    http_digest = ""
    if tree is not None:
        http_digest = hashlib.sha256("\n".join(
            (tree / "tools" / "writing_verbs" / "http_routes.csv")
            .read_text(encoding="utf-8").splitlines()).encode()).hexdigest()
    out.append("GENERATED_FROM = %r" % ("tests/grammar_spec/mapping.csv lf-lines sha256:"
                                       + digest))
    out.append("HTTP_GENERATED_FROM = %r"
               % ("tools/writing_verbs/http_routes.csv lf-lines sha256:" + http_digest))
    out.append("SITE_HOW = %r" % (SITE_HOW,))
    out.append("PRIMARY_ACT = {")
    for operation, pair in sorted((primary or {}).items()):
        out.append("    %r: %r," % (operation, pair))
    # ONE ROW PER OPERATION, and the FIRST in the csv's own order (WRITING-CONSOLIDATION-W1,
    # the synthesis). A dict literal silently keeps the LAST duplicate key, so emitting a row
    # per HTTP ROW made `review/adjudicate-comment`'s primary act `note@chapter` --- the third
    # of its three altitudes --- while `http_act` reads `HTTP_BY_NAME`, which is built with
    # `setdefault` and therefore answers `note@paragraph`. Two answers to one question, from
    # one generated table, with two of the three rows dead text in the file. The csv's order IS
    # the answer, so this picks the same first row `HTTP_BY_NAME` does.
    http_primary: dict[str, tuple[str, str, str]] = {}
    for row in http:                                      # http_routes.csv order
        http_primary.setdefault(row["operation"],
                                (row["verb"], row["concept"], "http-route"))
    for operation in sorted(http_primary):
        out.append("    %r: %r," % (operation, http_primary[operation]))
    out.append("}")
    return "\n".join(out)


BEGIN = "# BEGIN ROUTES (generated by gen_routes.py from mapping.csv; do not edit by hand)"
END = "# END ROUTES"


def splice(tree: Path, body: str) -> bool:
    path = tree / "src" / "laplace" / "native" / "verbs.py"
    text = path.read_text()
    head, marker, rest = text.partition(BEGIN)
    assert marker, "the generated block's BEGIN marker is gone"
    _old, marker2, tail = rest.partition(END)
    assert marker2, "the generated block's END marker is gone"
    new = (head + BEGIN + "\n# " + "-" * 73 + "\n" + body + "\n# " + "-" * 73 + "\n"
           + END + tail)
    if new == text:
        return False
    path.write_text(new)
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", default=".")
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the shipped table is not what this run would write")
    args = ap.parse_args()
    tree = Path(args.tree).resolve()
    routes, mapping, primary = build(tree)
    body = render(routes, mapping, http=http_rows(tree, routes), tree=tree,
                  primary=primary)
    if args.check:
        text = (tree / "src" / "laplace" / "native" / "verbs.py").read_text()
        ok = body in text
        print("ROUTES up to date:", ok)
        return 0 if ok else 1
    changed = splice(tree, body)
    pairs = {(r["verb"], r["concept"]) for r in routes}
    print(json.dumps({"routes": len(routes), "pairs": len(pairs),
                      "verbs": len({r["verb"] for r in routes}),
                      "concepts": len({r["concept"] for r in routes}),
                      "altitudes": sorted({r["concept"].split("@")[1] for r in routes}),
                      "operations": len({r["operation"] for r in routes}),
                      "without_owner_site": sorted({r["operation"] for r in routes if not r["site"]}),
                      "guarded_routes": sum(1 for r in routes if r["guards"]),
                      "collisions": sorted({"%s %s" % p for p in pairs
                                            if sum(1 for r in routes
                                                   if (r["verb"], r["concept"]) == p) > 1}),
                      "changed": changed}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
