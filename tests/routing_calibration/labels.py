"""Build the labelled dataset the routing advisor is calibrated on.

Two label spaces, both derived mechanically from records that already exist, so a
reader can re-derive every label without trusting a judgement of mine:

**D1 --- route.**  The label is the `(verb, concept)` pair the grammar's mapping
table assigns to the operation and sub-verb the recorded row actually used.
`mapping.csv` IS that correspondence (GRAMMAR.md §7, row source `map_verbs.py`
over the audit's `verb_matrix.csv`), so the label function is a lookup, not an
opinion.  The decider is given the row's payload with every discriminator key
removed --- `operation`, `action`, `kind`, `view`, `status`, `op`, `mode` --- because
those keys ARE the answer.

What that construction measures, stated plainly: whether the verb and the concept
are recoverable from the request's own content without the operation name.  It is
not a measurement of routing from an author's instruction, because the corpus
carries no instruction field.  The arrival corpus has a `step` label, but every
step name contains its own operation (`F3-section-create-doors`), so using it as an
intent would leak the label; it is not used.

**D4 --- classify a refusal.**  The label is the grammar refusal kind
(`grammar.Refusal.KINDS`) the recorded refusal is, derived from the census's own
`error_class` by `CLASS_TO_KIND` below, which carries a reason per class.  The
decider is given only the refusal's prose --- the same input the live decision has
at `src/laplace/writing_tools.py:1383`.

Nineteen of the 210 recorded refusals have NO faithful grammar kind and are
excluded with their reason, not folded into the nearest one: 14 `external-fetch`
(an outside service answered 403/429 --- not the writing system's identity, shape
or state) and 5 `tool-permission` (the provider's own harness refused `Bash` or
`Write`, operations that are not in `writing_tools.READS | WRITES` at all).  Both
exclusions are reported as counts; the accuracy figures are given over the 191
that do have a kind, and again over all 210 with the 19 folded, so neither reading
is hidden.

The 87 friction-ledger rows carry `error_class: null`, so their D4 label is derived
from the recorded `needed` and `home` fields --- the authored fact that resolved the
refusal --- by `LEDGER_RULES`, which the classifier never sees.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
TREE = HERE.parents[1]
sys.path.insert(0, str(TREE / "src"))

from laplace.core import grammar  # noqa: E402
from laplace.native import routing

CORPUS = Path("/home/phujck/VScodeProjects/laplace/evidence/"
              "WRITING_RECONCILIATION_2026-10-02/harness/corpus")
MAPPING = TREE / "tests" / "grammar_spec" / "mapping.csv"

DISCRIMINATOR_KEYS = ("operation", "action", "view", "status", "kind", "mode")

# --------------------------------------------------------------------------
# D1: the mapping table as a lookup.
# --------------------------------------------------------------------------


def load_mapping(path: Path = MAPPING) -> tuple[dict, dict]:
    """`(leaf, discriminated)`: operation -> pairs, and operation -> key -> value -> pair."""
    leaf: dict[str, set[tuple[str, str]]] = {}
    disc: dict[str, dict[str, dict[str, tuple[str, str]]]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            op = row["operation"].strip()
            pair = (row["verb"].strip(), row["concept"].strip())
            old = row["old_verb"].strip()
            if "=" in old:
                key, _, value = old.partition("=")
                disc.setdefault(op, {}).setdefault(key.strip(), {})[value.strip()] = pair
            else:
                leaf.setdefault(op, set()).add(pair)
    return leaf, disc


def pairs_in_mapping(path: Path = MAPPING) -> set[tuple[str, str]]:
    leaf, disc = load_mapping(path)
    out = {p for pairs in leaf.values() for p in pairs}
    for keys in disc.values():
        for values in keys.values():
            out |= set(values.values())
    return out


def _nested_discriminator(payload: dict) -> dict[str, str]:
    """The discriminators a payload speaks, including the two deeper levels.

    `logical_plan_change.operation.kind` and `structure_change.op.kind` bury the
    sub-verb one and two levels down (jev-assessment.md §2, D1 detail), so a flat
    scan would miss them.
    """
    found: dict[str, str] = {}
    for key in DISCRIMINATOR_KEYS:
        value = payload.get(key)
        if isinstance(value, str):
            found[key] = value
        elif isinstance(value, dict):
            inner = value.get("kind")
            if isinstance(inner, str):
                found[key] = inner
    inner_op = payload.get("op")
    if isinstance(inner_op, dict) and isinstance(inner_op.get("kind"), str):
        found.setdefault("op.kind", inner_op["kind"])
    return found


def route_label(operation: str, payload: dict, leaf: dict, disc: dict) -> tuple[tuple[str, str] | None, str]:
    """`(pair, reason)`.  `pair is None` means the row carries no derivable label."""
    operation = (operation or "").strip()
    # The ledger spells some operations with the sub-verb inline ("structure_change
    # bind_results"); split it back into the two halves the mapping is keyed on.
    extra = ""
    if operation and operation not in leaf and operation not in disc and " " in operation:
        operation, _, extra = operation.partition(" ")
        extra = extra.strip()
    if operation not in leaf and operation not in disc:
        return None, "outside-the-mapping: operation %r has no row (the mapping covers the " \
                     "tool door's audited verbs; the HTTP door and non-writing tools are " \
                     "outside it)" % operation
    payload = payload if isinstance(payload, dict) else {}
    if not payload and disc.get(operation) and not extra:
        return None, "no-payload: the recorded row kept no payload, so there is nothing to " \
                     "route from; operation %r is discriminated by %s" % (operation, sorted(disc[operation]))
    spoken = _nested_discriminator(payload)
    if extra:
        spoken.setdefault("operation", extra.split()[0])
    for key, values in (disc.get(operation) or {}).items():
        value = spoken.get(key) or spoken.get("op.kind")
        if value is not None and value in values:
            return values[value], "mapping %s %s=%s" % (operation, key, value)
    options = leaf.get(operation, set())
    if len(options) == 1:
        return next(iter(options)), "mapping %s (one leaf pair)" % operation
    if disc.get(operation):
        return None, ("default-sub-verb-unmapped: operation %r is discriminated by %s, the "
                      "payload names no value the mapping knows (spoken: %s), and the "
                      "published contract declares no default for it either"
                      % (operation, sorted(disc[operation]), sorted(spoken.items())))
    return None, "ambiguous: operation %r has %d leaf pairs and no discriminator" % (
        operation, len(options))


# --------------------------------------------------------------------------
# D4: the census class -> the grammar's refusal kind, with a reason per class.
# --------------------------------------------------------------------------
CLASS_TO_KIND: dict[str, tuple[str | None, str]] = {
    "identity-mismatch": (
        "identity-stale",
        "a home the caller named moved: 'structure revision conflict; read the current "
        "plan state first' is exactly grammar.require's refusal, and the cure is the "
        "current token (src/laplace/project_structure.py:852-855 compares it)"),
    "out-of-range-locator": (
        "unknown-home",
        "the addressed home is not there rather than stale: 'Source line range is "
        "outside the file', 'block file is not in the selected manuscript source'. A "
        "fresher token cannot cure it; a container read can"),
    "missing-guard-field": (
        "shape",
        "a field the door requires is absent, so the request's shape is wrong before "
        "any identity is compared: 'Passage evidence requires an explicitly authored "
        "partial/read status'"),
    "unknown-project-or-record": (
        "unknown-home",
        "'unknown project', 'history record is unavailable': the home id does not name "
        "a home of this project"),
    "unknown-field-name": (
        "shape",
        "'literature_discover has unknown fields: query': the payload speaks a name the "
        "schema does not declare"),
    "precondition-order": (
        "state-not-reached",
        "a third home is not yet terminal: 'Build a current style preview before "
        "exporting it', 'record.result differs from the supervised run output' --- the "
        "state precondition GRAMMAR.md §3 gives `record` its own verb for "
        "(src/laplace/research_surface.py:1226-1229)"),
    "anchor-not-found": (
        "unknown-home",
        "'before text has no exact full-line match in consumed scope': the prose home "
        "the span addresses does not exist, which is why GRAMMAR.md §2 keeps "
        "anchor_text as payload content and the span as the home"),
    "wrong-door": (
        "shape",
        "'Use the source, bibliography, or canonical-record operation for this file': "
        "the request addresses a concept this door does not serve. Under the grammar "
        "the concept selects the door, so this class cannot recur"),
    "enum-value": ("shape", "'stage view must be summary, guidance or materials'"),
    "structure-writer-refusal": (
        "state-not-reached",
        "'canonical structure writer refused the change' names no home and no field; "
        "the nearest faithful kind is that the writer's precondition was not met. One "
        "row, and the weakest label in this table"),
    "external-fetch": (
        None,
        "NO GRAMMAR KIND. 'Full-text retrieval failed (HTTP 403/429)' is an outside "
        "service's answer, not this system's identity, shape or state. The grammar's "
        "four kinds do not cover it and this packet does not invent a fifth; 14 rows "
        "excluded"),
    "tool-permission": (
        None,
        "NO GRAMMAR KIND, and not a writing refusal at all: the operations are `Bash` "
        "and `Write`, which are not in writing_tools.READS | WRITES "
        "(src/laplace/writing_tools.py:16, :18). 5 rows excluded"),
}

LEDGER_RULES: tuple[tuple[str, str, str], ...] = (
    # (grammar kind, a phrase in the recorded `needed`/`error`, why)
    ("identity-stale", "revision", "the resolved fact is a current revision the caller had to re-read"),
    ("state-not-reached", "before", "the fact is an ordering: something had to happen first"),
    ("unknown-home", "does not exist", "the addressed home was absent"),
    ("unknown-home", "not a", "the id named no home of this project"),
    ("shape", "field", "the fact is a field name or a shape the schema requires"),
    ("shape", "must be", "the fact is a type or an enum the door requires"),
    ("shape", "path", "the fact is which base a path is resolved against"),
)


# The eight arrival refusals carry `error_class: null` (the census classed the tool
# door's failures, not the acceptance sequence's own).  They are labelled here, by
# hand, one line each with the sentence the owner served --- eight rows, every one
# of them printed in the report so the reader can disagree with a specific label
# rather than with a table.  HARNESS.md's "what a lane must move" groups C2, D3 and
# J2 as the identity-guard class and E2, E4/F4 as the altitude and door-routing
# class; that is a classification of the DEFECT, and this is a classification of the
# refusal KIND, so E4 and F4 sit in different kinds here and the reason is stated.
ARRIVAL_KINDS: dict[str, tuple[str, str]] = {
    "A1-create-no-header": ("shape", "'Missing writing-client header.' --- a field the door "
                            "requires is absent from the request"),
    "A2-create-bare": ("shape", "'title and kind (book|paper) are required'"),
    "C2-initialize-top-revision": ("identity-stale", "'selected source revision conflict; "
                                   "inspect the current edition first' --- the selected-edition home moved"),
    "D3-add-object-structure-revision": ("identity-stale", "'logical plan revision conflict' "
                                         "--- the concept-network home moved"),
    "E2-apply-revision": ("state-not-reached", "'apply_revision requires the current project "
                          "turn.' --- a third home, the turn, is not in the state this act needs; "
                          "no fresher token cures it"),
    "E4-adjudicate-no-corpus": ("unknown-home", "'unknown corpus / dir' --- the home the "
                                "request addresses is not there"),
    "F4-adjudicate-headings-blank-guard": ("shape", "'before must be non-empty: it is the byte "
                                           "guard' --- the identity slot was sent empty, which is a "
                                           "shape fault and not a stale value"),
    "K2-turn-no-message": ("shape", "'Write a message first.'"),
}


def arrival_kind(row: dict) -> tuple[str | None, str]:
    step = str(row.get("step") or "")
    if step in ARRIVAL_KINDS:
        kind, why = ARRIVAL_KINDS[step]
        return kind, "arrival hand label: " + why
    return None, "no arrival label for step %r" % step


def ledger_kind(row: dict) -> tuple[str | None, str]:
    """A ledger row's D4 label, from the fact that RESOLVED it (never from the error).

    The classifier is given `recorded.error`; the label comes from `needed` and
    `recorded.home`, which the classifier never sees, so the two are not the same
    text read twice.
    """
    needed = ((row.get("needed") or "") + " " + (row["recorded"].get("home") or "")).lower()
    if not needed.strip():
        return None, "the ledger row records no resolving fact"
    for kind, phrase, why in LEDGER_RULES:
        if phrase in needed:
            return kind, "ledger rule %r -> %s (%s)" % (phrase, kind, why)
    return "shape", "no rule matched; the default is `shape`, the kind that is not an identity"


# --------------------------------------------------------------------------
# Assembly.
# --------------------------------------------------------------------------
def load_corpus(sources: tuple[str, ...] = ("failures", "reads", "writes", "arrival", "ledger")) -> list[dict]:
    rows: list[dict] = []
    for name in sources:
        path = CORPUS / ("%s.jsonl" % name)
        rows.extend(json.loads(line) for line in path.read_text().splitlines() if line.strip())
    return rows


def build() -> dict:
    leaf, disc = load_mapping()
    declared = set(routing.ROUTE_OPTIONS)
    rows = load_corpus()
    d1: list[dict] = []
    d1_excluded: list[dict] = []
    d4: list[dict] = []
    d4_excluded: list[dict] = []
    for row in rows:
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        pair, reason = route_label(row.get("operation") or "", payload, leaf, disc)
        state = routing.RouteState(door=row.get("door") or "tool",
                                   mode=row.get("mode") or "work",
                                   payload=payload,
                                   target=str(row.get("project") or ""),
                                   path=str(row.get("path") or ""))
        if pair is None:
            d1_excluded.append({"id": row["id"], "source": row["source"],
                                "operation": row.get("operation"), "reason": reason})
        elif pair not in declared:
            d1_excluded.append({"id": row["id"], "source": row["source"],
                                "operation": row.get("operation"),
                                "reason": "mapping gives %r, which grammar.VERB_CONCEPTS does not "
                                          "declare" % (pair,)})
        else:
            d1.append({"id": row["id"], "source": row["source"],
                       "operation": row.get("operation"),
                       "label": "%s %s" % pair, "reason": reason,
                       "state": {"door": state.door, "mode": state.mode,
                                 "payload": payload, "target": state.target,
                                 "path": state.path},
                       "state_chars": len(state.state_text())})
        error = (row["recorded"].get("error") or "").strip()
        if row["recorded"].get("outcome") != "refused" or not error:
            continue
        if row["source"] == "ledger":
            kind, why = ledger_kind(row)
        elif row["source"] == "arrival":
            kind, why = arrival_kind(row)
        else:
            cls = row["recorded"].get("error_class")
            kind, why = CLASS_TO_KIND.get(cls, (None, "no entry for error_class %r" % cls))
        target = {"id": row["id"], "source": row["source"], "operation": row.get("operation"),
                  "error": error, "error_class": row["recorded"].get("error_class"),
                  "label": kind, "reason": why}
        (d4 if kind else d4_excluded).append(target)
    return {"d1": d1, "d1_excluded": d1_excluded, "d4": d4, "d4_excluded": d4_excluded,
            "declared_pairs": len(declared),
            "mapping_pairs": len(pairs_in_mapping()),
            "refusal_kinds": list(routing.RESOLVER_OPTIONS)}


def main() -> int:
    data = build()
    import collections
    print("D1 labelled rows:", len(data["d1"]), "excluded:", len(data["d1_excluded"]))
    print("   by source:", dict(collections.Counter(r["source"] for r in data["d1"])))
    print("   distinct labels:", len({r["label"] for r in data["d1"]}),
          "of", data["declared_pairs"], "declared pairs")
    print("   top labels:", collections.Counter(r["label"] for r in data["d1"]).most_common(8))
    kinds = collections.Counter(r["reason"].partition(":")[0] for r in data["d1_excluded"])
    print("   exclusion kinds:", dict(kinds.most_common()))
    for kind in kinds:
        ops = collections.Counter(r["operation"] for r in data["d1_excluded"]
                                  if r["reason"].startswith(kind))
        print("     %s -> %s" % (kind, dict(ops.most_common(8))))
    print("D4 labelled rows:", len(data["d4"]), "excluded:", len(data["d4_excluded"]))
    print("   by kind:", dict(collections.Counter(r["label"] for r in data["d4"])))
    print("   by source:", dict(collections.Counter(r["source"] for r in data["d4"])))
    print("   excluded classes:", dict(collections.Counter(r["error_class"] for r in data["d4_excluded"])))
    out = HERE / "labels.json"
    if len(sys.argv) > 1:
        out = Path(sys.argv[1])
    out.write_text(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False))
    print("written", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
