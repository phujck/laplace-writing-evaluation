"""One-time migration: today's hand-written contracts become declarations.

Run once, from the worktree root, with the tree's own runtime:

    scripts/laplace-python tools/migrate_declarations.py

It reads the contract table as it stands in the git blob at ``--base`` (HEAD by
default), so the migration's input is pinned to a commit and cannot drift while
the module it writes is being edited, and it writes three files:

  src/laplace/writing/schemas.py    the 73 input schemas, verbatim data
  src/laplace/native/declared.py   the 73 declarations
  tests/grammar_spec/head_contract_prose.json
                                    every prose string the audit found stated,
                                    keyed by (operation, section, index), so a
                                    test can prove none of them was lost

Every clause of every precondition, summary, output and recoverable error in the
base blob becomes a typed ``Rule`` whose ``carries`` names the exact string it
came from.  A clause is split at sentence and semicolon boundaries and refused
above 160 characters, which is the holder census's definition of contract prose
(harness/holder_census.py counts string literals of 160+ characters in
writing_contracts.py, by line).  The cap is the gate: a rule that cannot be said
in 160 characters is a rule whose structure has not been found yet.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "src"))

from laplace.core import grammar as g                                      # noqa: E402
from laplace.writing import reads

MAPPING = Path("/home/phujck/VScodeProjects/laplace/evidence/"
               "WRITING_RECONCILIATION_2026-10-02/grammar/mapping.csv")
#: The commit this lane's worktree started from --- where the hand-written contract
#: table still lives.  NOT `HEAD`: after the first commit of this packet, HEAD's
#: writing_contracts.py is a projection of the declarations.
CAMPAIGN_BASE = "706a82047ae90ce79956cb25a4831973f61eec85"
SAYS_CAP = 160
GENERIC_NAMES = {"revision"}

# Operations whose input schema is built from the owner's own published contract
# rather than written here.  exact_contract already did this; the builder moves
# to writing_declarations and the declaration names it.
VARIANT_BUILDERS = {
    "structure_change": "structure_change",
    "concept_change": "concept_change",
    "logical_plan_change": "logical_plan_change",
    "concept_tree": "concept_tree",
    "repository": "repository",
    "visual_create": "visual_create",
}
# Operations whose help carries an owner protocol block (not prose: the owner
# publishes it).
PROTOCOL = {"research_producer": "producer_execution_contract",
            "experiment_run": "producer_execution_contract"}

TURN_BOUND = {
    # writing_tools.py line that refuses without the current turn
    "apply_revision": "src/laplace/writing_tools.py:226",
    "propose_revision": "src/laplace/writing_tools.py:239",
    "proposal_supersede": "src/laplace/writing_tools.py:254",
    "conversation_history": "src/laplace/writing_tools.py:295",
}

# Keys the old table used for a handful of operations and that are data, not a summary:
# they are carried under their own names so no consumer loses them.
EXTRA_KEYS = ("next_steps", "recovery", "scope_rules", "source_locator_recipe")

STATE_WORDS = ("COMPLETE", "RUNNING", "REFUSED", "FAILED", "UNKNOWN",
               "CANCEL_REQUESTED", "MIRROR_PENDING", "UNTRACKED", "STALE",
               "INCOMPLETE", "CURRENT", "NOT_ESTABLISHED")


def base_blob(ref: str, path: str) -> str:
    return subprocess.run(["git", "show", "%s:%s" % (ref, path)], cwd=HERE,
                          check=True, capture_output=True, text=True).stdout


def contracts_at(ref: str) -> dict:
    """Execute the base blob's contract table in its own namespace.

    The blob must be the HAND-WRITTEN table, and that is checked rather than assumed.
    Once this packet's own `writing_contracts.py` is committed, `HEAD` holds a module
    whose `CONTRACTS` is a PROJECTION of the declarations: exec it and the migration
    reads its own output, agrees with itself, and silently drops every `preconditions`
    list (the projection does not publish that key).  That happened once here --- the
    no-loss proof still passed, because both sides of the comparison had been
    contaminated from one source --- so the guard is a refusal with the reason, not a
    comment.
    """
    source = base_blob(ref, "src/laplace/native/contracts.py")
    if "CONTRACTS = {" not in source or '"preconditions"' not in source:
        raise SystemExit(
            "%s:src/laplace/native/contracts.py is not the hand-written contract table "
            "(no literal `CONTRACTS = {` with preconditions). Pass --base with the "
            "commit this branch started from (%s); exec-ing this packet's own projection "
            "would make the migration read its own output."
            % (ref, CAMPAIGN_BASE[:12]))
    namespace: dict = {"__name__": "writing_contracts_base"}
    exec(compile(source, "<%s:writing_contracts.py>" % ref, "exec"), namespace)
    return namespace["CONTRACTS"]


from laplace.native.declarations import clauses  # the shipped splitter


def schema_fields(schema, acc: set | None = None) -> set:
    acc = set() if acc is None else acc
    if isinstance(schema, dict):
        for key, value in (schema.get("properties") or {}).items():
            acc.add(key)
            schema_fields(value, acc)
        for key in ("items", "not", "else", "then", "if"):
            if key in schema:
                schema_fields(schema[key], acc)
        for key in ("oneOf", "anyOf", "allOf"):
            for row in schema.get(key) or []:
                schema_fields(row, acc)
    return acc


def mapping_rows() -> dict[str, list[dict]]:
    rows = list(csv.DictReader(MAPPING.open(encoding="utf-8-sig")))
    grouped: dict[str, list[dict]] = collections.defaultdict(list)
    for row in rows:
        grouped[row["operation"].split(" ")[0]].append(row)
    return grouped


def handler_lines() -> dict[str, str]:
    """The dispatch line in writing_tools._execute that routes each operation."""
    text = (HERE / "src/laplace/native/tools.py").read_text(encoding="utf-8").splitlines()
    found: dict[str, str] = {}
    pattern = re.compile(r"""operation\s*(?:==|in)\s*(.+)""")
    for number, line in enumerate(text, 1):
        if "operation" not in line or not line.lstrip().startswith(("if ", "elif ", "return ")):
            continue
        match = pattern.search(line)
        if not match:
            continue
        for name in re.findall(r"""['"]([a-z_]+)['"]""", match.group(1)):
            if name in reads.READS | reads.WRITES:
                found.setdefault(name, "src/laplace/native/tools.py:%d" % number)
    # The rest are routed by the `routes` table (writing_tools.py:569-607), whose key
    # IS the dispatch site: `"run_status": (research_surface, "/research/run/status", "GET")`.
    route_key = re.compile(r"""^\s*['"]([a-z_]+)['"]\s*:\s*\(""")
    for number, line in enumerate(text, 1):
        match = route_key.match(line)
        if match and match.group(1) in reads.READS | reads.WRITES:
            found.setdefault(match.group(1), "src/laplace/native/tools.py:%d" % number)
    return found


def pairs_from(row: dict) -> list[tuple[str, list[str], bool]]:
    """(guard name, home alternatives, optional) for one mapping row.

    mapping.csv uses two separators and they mean different things, measured over the
    155 rows: `/` separates distinct (guard, home) PAIRS on one door --- 29 rows have
    one --- and `|` separates ALTERNATIVE homes for a single guard --- 9 rows do.  So
    `expected_plan_revision/expected_source_digest` against `plan|plan-file/source-file`
    is two guards, the first of which answers to either of two homes.  Splitting on `|`
    alone (round one of this generator) silently dropped every second pair, and
    section_change lost its source-file guard entirely.
    """
    guards = [guard.strip() for guard in (row.get("old_guards") or "").split("/")
              if guard.strip() and guard.strip() != "-"]
    cells = [cell.strip() for cell in (row.get("homes") or "").split("/")
             if cell.strip() and cell.strip() != "-"]
    out: list[tuple[str, list[str], bool]] = []
    for index, guard in enumerate(guards):
        cell = cells[index] if index < len(cells) else ""
        optional = cell.endswith("?")
        alternatives = [name.strip().rstrip("?") for name in cell.replace(",", "|").split("|")
                        if name.strip() and name.strip().rstrip("?") in g.HOME_KINDS]
        out.append((guard, alternatives, optional))
    # A row may declare homes without naming a guard (a read's homes, say).
    if not guards:
        for cell in cells:
            optional = cell.endswith("?")
            for name in cell.replace(",", "|").split("|"):
                name = name.strip().rstrip("?")
                if name in g.HOME_KINDS:
                    out.append(("", [name], optional))
    return out


def homes_for(operation: str, rows: list[dict], fields: set, concept: str) -> tuple[list[str], list[str]]:
    """Home kinds this door guards, and the guard names whose home is ambiguous.

    The mapping's own `homes` column first --- that is the audit's attribution.  Then
    any guard name the operation's schema actually asks for, because the mapping
    cannot see a guard nested inside a payload object (`block.expected_source_digest`
    is one).  A guard name that answers to more than one home is resolved by the
    operation's own concept object, and never by listing every candidate: naming
    five homes for one field is the 20-names defect in a new spelling.
    """
    homes: dict[str, bool] = {}          # kind -> optional
    alternates: list[str] = []
    for row in rows:
        for guard, alternatives, optional in pairs_from(row):
            if not alternatives:
                continue
            # ONE home per guard.  Where the audit itself recorded alternatives
            # (`plan|plan-file` for expected_plan_revision: two reads publish the same
            # value under one asked-for name) the first is the home and the rest are
            # named in a rule.  Asking a caller for two tokens where the door compares
            # one is how a field comes to have five names.
            homes[alternatives[0]] = homes.get(alternatives[0], True) and optional
            if len(alternatives) > 1 and guard:
                entry = "%s -> %s" % (guard, "|".join(alternatives))
                if entry not in alternates:
                    alternates.append(entry)
    obj = g.concept_object(concept) if concept else ""
    ambiguous: list[str] = []
    for name in sorted(fields):
        candidates = g.GUARD_NAMES.get(name, ())
        if not candidates:
            continue
        if name in GENERIC_NAMES and name not in (row.get("old_guards") or "" for row in rows):
            # `revision` is a PUBLISHED name on five reads as well as an asked-for name on
            # one home (GRAMMAR.md section 2's two name columns).  Its appearance inside a
            # nested payload object --- evidence_refs[].revision is a research result's ---
            # does not attribute the authoring-state home to this door.
            ambiguous.append("%s -> %s" % (name, "|".join(candidates)))
            continue
        if len(candidates) == 1:
            homes.setdefault(candidates[0], False)
        elif obj in candidates:
            homes.setdefault(obj, False)
        elif any(candidate in homes for candidate in candidates):
            pass                         # the mapping already attributed it
        else:
            ambiguous.append("%s -> %s" % (name, "|".join(candidates)))
    return ([kind + ("?" if optional else "") for kind, optional in sorted(homes.items())],
            ambiguous + alternates)


_FILE_LINE = re.compile(r"([A-Za-z0-9_./-]+\.py):(\d+)")


from laplace.native.declarations import read_call as clean_read  # shipped


def clean_door(raw: str, fallback: str) -> str:
    """The first file:line in a grammar citation, as a path under src/laplace.

    `HomeKind.guard_doors` and `HomeKind.source` carry a whole sentence around the
    citation (the pair of comparison sites for `before`, say).  A rule's door is one
    line a reader can open, so the sentence does not come with it: the clause that
    explains the two sites lives in `says`, where the 160-character cap applies.
    """
    match = _FILE_LINE.search(str(raw or ""))
    if not match:
        return fallback
    path, line = match.group(1), match.group(2)
    if not path.startswith("src/"):
        path = "src/laplace/" + path.lstrip("./")
    return "%s:%s" % (path, line)


def identity_rules(operation: str, homes: list[str], rows: list[dict], fields: set,
                   handler: str) -> list[dict]:
    """One identity rule per home this door guards --- the structure the prose lacked.

    This is the part that is NEW, not carried: the audit found 20 guard names over 9
    values and no door naming the read its value comes from.  So for every home in the
    declaration there is a rule that names the field, the home, the read that serves it
    and the line that compares it, whether or not any sentence in the old contract
    happened to mention it.  Where the audit recorded the name the door asks for, that
    name is used; where it recorded none, the home's own `guards_today` supplies it, and
    where the home publishes no asked-for name at all the field is `expected`, the
    grammar's own list (GRAMMAR.md section 5).
    """
    recorded: dict[str, list[str]] = {}
    for row in rows:
        for guard, alternatives, _optional in pairs_from(row):
            for home in alternatives:
                recorded.setdefault(home, [])
                if guard and guard not in recorded[home]:
                    recorded[home].append(guard)
    out: list[dict] = []
    for raw in homes:
        kind_name = raw.rstrip("?")
        kind = g.HOME_KINDS[kind_name]
        names = recorded.get(kind_name) or [name for name in kind.guards_today
                                            if name in fields] or list(kind.guards_today)
        field_name = names[0] if names else "expected"
        door = clean_door(next((entry.split("=", 1)[1] for entry in kind.guard_doors
                                if entry.startswith(field_name + "=")), "") or kind.source,
                          handler)
        says = "%s is the %s home's token%s" % (
            field_name, kind_name, " (optional on this door)" if raw.endswith("?") else "")
        out.append({"kind": "identity", "field": field_name, "home": kind_name,
                    "read": clean_read(kind.read), "door": door,
                    "values": tuple(names[1:]) if len(names) > 1 else (),
                    "says": says[:SAYS_CAP - 1], "carries": (operation, "home", 0)})
    return out


def rule_for(clause: str, operation: str, fields: set, section: str, index: int,
             rows: list[dict], handler: str = "") -> dict:
    """One typed rule from one clause.  The kind is decided by what the clause
    actually names, in this order: a guard name (identity), an enum the schema
    declares, a terminal state, a choice between fields, an ordering, a scope
    limit, else the shape of a field."""
    guards = [name for name in sorted(g.GUARD_NAMES, key=len, reverse=True)
              if re.search(r"\b%s\b" % re.escape(name), clause)]
    named = [name for name in sorted(fields, key=len, reverse=True)
             if re.search(r"\b%s\b" % re.escape(name), clause)]
    # A door is a file:line a reader can check.  For a rule that is not an identity
    # guard the enforcing line is the dispatch that routes the operation to its owner;
    # naming only the owner FILE would be the thing this packet refuses --- a citation
    # nobody can open at a line.
    door = handler
    if guards:
        guard = guards[0]
        homes = g.GUARD_NAMES[guard]
        kind = g.HOME_KINDS[homes[0]]
        attributed = next((entry.split("=", 1)[1] for home in homes
                           for entry in g.HOME_KINDS[home].guard_doors
                           if entry.startswith(guard + "=")), "")
        return {"kind": "identity", "field": guard, "home": homes[0],
                "read": clean_read(kind.read), "door": clean_door(attributed or kind.source, door),
                "says": clause, "carries": (operation, section, index)}
    lowered = clause.lower()
    if any(word in clause for word in STATE_WORDS):
        return {"kind": "state", "field": named[0] if named else "", "door": door,
                "says": clause, "carries": (operation, section, index)}
    if re.search(r"\b(or|either|exactly one|one of)\b", lowered) and len(named) > 1:
        # In READING ORDER, not longest-first: "supply doi OR metadata plus provenance"
        # offers `doi` as its first branch, and an example built from the rule has to pick
        # a branch the door accepts. Ordering by name length put `provenance` first and
        # produced an example that satisfied neither branch.
        in_order = sorted(named, key=lambda name: clause.find(name))
        return {"kind": "one-of", "fields": tuple(in_order[:4]), "door": door,
                "says": clause, "carries": (operation, section, index)}
    if named:
        enumerated = enum_values(operation, named[0], fields)
        if enumerated:
            return {"kind": "enum", "field": named[0], "values": enumerated, "door": door,
                    "says": clause, "carries": (operation, section, index)}
    if re.search(r"\b(order|reader order|placed|placement|before|after)\b", lowered) and named:
        return {"kind": "order", "field": named[0], "door": door,
                "says": clause, "carries": (operation, section, index)}
    if re.search(r"\b(never|not |do not|cannot|does not|is not|no )", lowered):
        return {"kind": "scope", "field": named[0] if named else "", "door": door,
                "says": clause, "carries": (operation, section, index)}
    return {"kind": "shape", "field": named[0] if named else "", "door": door,
            "says": clause, "carries": (operation, section, index)}


_ENUMS: dict[tuple[str, str], tuple] = {}


def collect_enums(operation: str, schema) -> None:
    if isinstance(schema, dict):
        for key, value in (schema.get("properties") or {}).items():
            if isinstance(value, dict) and value.get("enum"):
                _ENUMS[(operation, key)] = tuple(value["enum"])
            collect_enums(operation, value)
        for key in ("items", "not", "else", "then", "if"):
            if key in schema:
                collect_enums(operation, schema[key])
        for key in ("oneOf", "anyOf", "allOf"):
            for row in schema.get(key) or []:
                collect_enums(operation, row)


def enum_values(operation: str, field: str, fields: set) -> tuple:
    return _ENUMS.get((operation, field), ())


def python(value) -> str:
    return repr(value)


def emit_schemas(contracts: dict, out: Path) -> None:
    body = ["\"\"\"The deployed input schemas, as data.\n",
            "GENERATED by tools/migrate_declarations.py from the contract table at the",
            "commit named in MIGRATED_FROM.  A schema is code, not prose: the audit's",
            "finding was never that the schemas are too big, it was that the sentences",
            "beside them carry obligations no field states.  They move here unchanged so",
            "that test_generated_contract.py can prove, byte for byte, that the",
            "migration lost no key.",
            "\"\"\"",
            "from __future__ import annotations", "",
            "SCHEMAS: dict[str, dict] = {"]
    for operation in sorted(contracts):
        # visual_create declares no literal input: its schema is the owner's own
        # authoring_contract, built by _variants_visual_create.
        body.append("    %r: %s," % (operation, python(contracts[operation].get("input") or {})))
    body += ["}", ""]
    out.write_text("\n".join(body) + "\n", encoding="utf-8")


def emit_declared(contracts: dict, out: Path, rows: dict, handlers: dict) -> dict:
    lines = [
        '"""The 73 deployed operations, declared: homes, payload, rules.',
        "",
        "GENERATED by tools/migrate_declarations.py.  Every rule carries, in its",
        "``carries``, the exact (operation, section, index) of the contract string it was",
        "made from, so tests/test_generated_contract.py can prove that no precondition",
        "the audit found stated was lost on the way here.",
        "",
        "A declaration is the one place an operation says what it is.  help renders it,",
        "the catalogue indexes it, the operating brief references its digest, and a",
        "refusal fills its `expected` from it.  There is no second copy.",
        "",
        "The ACT --- verb, concept, the other pairs, and the line that dispatches it --- is",
        "NOT here: it is one row set of src/laplace/native/verbs.py ROUTES, generated from",
        "tests/grammar_spec/mapping.csv, and `declare` reads it from there and refuses a",
        "declaration that states it.  Two tables for one fact is the defect that table ends.",
        '"""',
        "from __future__ import annotations", "",
        "from laplace.native.declarations import Rule, declare",
        "from laplace.writing.schemas import SCHEMAS", "",
    ]
    ledger: dict = {}
    #: What the migration computed for the act of each operation.  It is NOT emitted into
    #: the declarations any more --- the route table states it --- so it is written beside
    #: them as a check, which is how a migration can still be wrong-able about it.
    act_check: dict = {}
    for operation in sorted(contracts):
        contract = contracts[operation]
        schema = contract.get("input") or {}
        collect_enums(operation, schema)
        fields = schema_fields(schema)
        operation_rows = rows.get(operation, [])
        verbs = [r["verb"] for r in operation_rows]
        verb = collections.Counter(verbs).most_common(1)[0][0] if verbs else "read"
        concepts = [r["concept"] for r in operation_rows]
        concept = collections.Counter(concepts).most_common(1)[0][0] if concepts else ""
        also = sorted({(r["verb"], r["concept"]) for r in operation_rows} - {(verb, concept)})
        handler = handlers.get(operation, "")
        homes, ambiguous = homes_for(operation, operation_rows, fields, concept)
        rules: list[dict] = identity_rules(operation, homes, operation_rows, fields, handler)
        summary_clauses = clauses(contract.get("summary", ""))
        does = summary_clauses[0] if summary_clauses else ""
        # EVERY key of the base entry, including `input`, `example` and `examples`.  The
        # first version of this ledger stored only the prose sections, which made
        # test_the_only_thing_deleted_rather_than_carried_is_the_hand_written_example
        # vacuous: it compared the declaration against a fixture that had already dropped
        # the examples.  A no-loss proof must read the whole thing it is proving nothing
        # was lost from.
        ledger[operation] = {key: value for key, value in contract.items()}
        for index, clause in enumerate(summary_clauses[1:], start=1):
            rules.append(rule_for(clause, operation, fields, "summary", 0, operation_rows,
                                  handler))
        for index, text in enumerate(contract.get("preconditions") or []):
            for clause in clauses(text):
                rules.append(rule_for(clause, operation, fields, "preconditions", index,
                                      operation_rows, handler))
        for entry in ambiguous:
            name, _, candidates = entry.partition(" -> ")
            rules.append({"kind": "scope", "field": name, "door": handler,
                          "says": "%s names one of %s here; read the home this concept acts on"
                                  % (name, candidates),
                          "carries": (operation, "ambiguous-guard", 0)})
        outputs = [c for text in (contract.get("outputs") or []) for c in clauses(text)]
        recoverable = [c for text in (contract.get("recoverable_errors") or [])
                       for c in clauses(text)]
        errors = [c for text in (contract.get("errors") or []) for c in clauses(text)]
        extras = {}
        for key in EXTRA_KEYS:
            if key not in contract:
                continue
            value = contract[key]
            if isinstance(value, str):
                extras[key] = tuple(clauses(value))
            elif isinstance(value, list) and all(isinstance(item, str) for item in value):
                extras[key] = tuple(c for item in value for c in clauses(item))
            else:
                extras[key] = value

        lines.append("declare(")
        lines.append("    %r," % operation)
        # NOT verb=, concept=, also= or handler=.  They are read from the route table
        # (src/laplace/native/verbs.py, generated from tests/grammar_spec/mapping.csv and
        # tools/writing_verbs/http_routes.csv) and `declare` refuses them by name, so a
        # regeneration of this file cannot put a second copy of the act back.  What the
        # migration computed for them is written beside the file as a CHECK instead:
        # migrate_declarations_act_check.json, compared against the table by
        # tests/test_one_table.py.
        lines.append("    homes=%r," % (tuple(homes),))
        lines.append("    payload=SCHEMAS[%r]," % operation)
        if operation in VARIANT_BUILDERS:
            lines.append("    variants=%r," % VARIANT_BUILDERS[operation])
        if operation in PROTOCOL:
            lines.append("    protocol=%r," % PROTOCOL[operation])
        lines.append("    effects=%r," % (tuple(contract.get("effects") or ()),))
        lines.append("    does=%r," % does)
        if outputs:
            lines.append("    outputs=%r," % (tuple(outputs),))
        if recoverable:
            lines.append("    recoverable=%r," % (tuple(recoverable),))
        if errors:
            lines.append("    errors=%r," % (tuple(errors),))
        if extras:
            lines.append("    extras=%r," % (extras,))
        if operation in TURN_BOUND:
            lines.append("    turn_bound=True, turn_door=%r," % TURN_BOUND[operation])
        act_check[operation] = {"verb": verb, "concept": concept,
                                "also": [list(pair) for pair in (also or ())],
                                "handler": handler}
        if rules:
            lines.append("    rules=(")
            for rule in rules:
                parts = ["%r" % rule["kind"]]
                for key in ("field", "home", "read", "door"):
                    if rule.get(key):
                        parts.append("%s=%r" % (key, rule[key]))
                for key in ("fields", "values"):
                    if rule.get(key):
                        parts.append("%s=%r" % (key, tuple(rule[key])))
                parts.append("says=%r" % rule["says"])
                parts.append("carries=%r" % (tuple(rule["carries"]),))
                lines.append("        Rule(%s)," % ", ".join(parts))
            lines.append("    ),")
        lines.append(")")
        lines.append("")
    # Preserve the supported registration order if this historical migration is
    # explicitly rerun: HTTP help needs the complete native help declaration.
    lines.append("from laplace.web import writing_declared_http as _declared_http  # noqa: E402,F401")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out.parent / "migrate_declarations_act_check.json").write_text(
        json.dumps(act_check, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    return ledger


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=CAMPAIGN_BASE)
    args = parser.parse_args(argv)
    contracts = contracts_at(args.base)
    deployed = sorted(reads.READS | reads.WRITES)
    missing = [operation for operation in deployed if operation not in contracts]
    if missing:
        raise SystemExit("the base blob has no contract for: %r" % missing)
    contracts = {operation: contracts[operation] for operation in deployed}
    rows = mapping_rows()
    handlers = handler_lines()
    emit_schemas(contracts, HERE / "src/laplace/writing/schemas.py")
    ledger = emit_declared(contracts, HERE / "src/laplace/native/declared.py", rows, handlers)
    fixture = HERE / "tests/grammar_spec/head_contract_prose.json"
    fixture.write_text(json.dumps({"base": subprocess.run(
        ["git", "rev-parse", args.base], cwd=HERE, check=True, capture_output=True,
        text=True).stdout.strip(), "contracts": ledger}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print("operations declared:", len(contracts))
    print("handlers resolved:", sum(1 for operation in contracts if handlers.get(operation)),
          "of", len(contracts))
    print("missing handler:", [o for o in contracts if not handlers.get(o)])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
