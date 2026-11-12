"""The contract, as a view of the declarations.  Nothing is written twice here.

This module used to hold the contract itself: 73 hand-written entries with a
summary, an example, a list of preconditions and, for six operations, a second
copy of the owner's own schema.  The friction report of 2026-10-01 measured what
that cost --- 220,797 characters of `help` for the 73 operations, `concept_change`
49,285 and `structure_change` 41,476, the latter 75.3 per cent a byte-identical
duplicate of itself --- and found that the preconditions a caller needed were
*present*, buried in the third clause of a sentence inside 41,476 characters.

So the contract is no longer written.  Each operation declares itself once in
`laplace.native.declared` (verb, concept, the homes it guards, its payload
schema, its typed rules, the line that handles it) and everything here is
generated from those declarations:

* `CONTRACTS` --- kept because callers read `CONTRACTS[operation]["input"]`
  (`src/laplace/writing_tools.py:215` validates unknown fields with it).  It is
  now a projection of the declarations, not a source.
* `compact_catalogue` --- the index, from `writing_declarations.catalogue`.
* `exact_contract` --- one bounded help payload, from
  `writing_declarations.help_payload`, with this project's **live tokens** in
  `expected`.

Two things that were here are gone rather than moved:

1. **The 72 hand-written examples.**  `help section_change` offered
   `"expected_source_digest": "sha256:current"` and `help task_status` offered
   `"id": "REQUEST-example"` --- values no project contains.  The example is now
   built from the schema's own required keys with the live token of each home
   filled in (`writing_declarations.generated_example`), so an example either
   works or names the read that would make it work.
2. **The owner-contract duplicate.**  `exact_contract` embedded
   `project_structure.operation_contract()` under `owner_contract` while
   `src/laplace/writing_tools.py:271` returned the same object beside it as
   `requested_payload_contract`.  The variants are now built once, from the owner,
   by `writing_declarations.variants`, and `owner_contract` is not served at all.
   The PARAMETER of that name is gone from `exact_contract` too, not deprecated:
   a census of the tree found no caller passing it, and an argument that is
   "accepted and ignored" is a second contract with no expiry.  The one tool that
   still names it, `tools/measure_help.py`, calls the BASE commit's signature on
   the base side of its before/after and this tree's signature on the other.

*Conventional default refused*: **keeping the old table as the "stable" contract
and generating a second one next to it.**  That is the shape of every migration
that is abandoned half-done, and it is exactly the defect being cured: two copies
of one fact, free to disagree.  There is one row source, and these names are
renders of it.
"""
from __future__ import annotations

from typing import Any

from laplace.native import declarations
from laplace.native.declarations import DECLARATIONS, catalogue as _catalogue
from laplace.writing.schemas import SCHEMAS


class _Contracts(dict):
    """`CONTRACTS[operation]` --- a projection, built on read from the declaration."""

    def __missing__(self, operation: str) -> dict[str, Any]:
        declaration = DECLARATIONS.get(operation)
        if declaration is None:
            raise KeyError(operation)
        return {"input": declarations.owner_input_schema(operation),
                "summary": declaration.does,
                "effects": list(declaration.effects),
                "outputs": list(declaration.outputs),
                "recoverable_errors": list(declaration.recoverable),
                "errors": list(declaration.errors),
                **{key: list(value) if isinstance(value, tuple) else value
                   for key, value in (declaration.extras or {}).items()},
                "rules": [rule.rendered() for rule in declaration.rules],
                "verb": declaration.verb, "concept": declaration.concept,
                "homes": list(declaration.homes)}

    def __iter__(self):
        return iter(sorted(DECLARATIONS))

    def keys(self):
        return list(sorted(DECLARATIONS))

    def items(self):
        return [(operation, self[operation]) for operation in sorted(DECLARATIONS)]

    def values(self):
        return [self[operation] for operation in sorted(DECLARATIONS)]

    def __contains__(self, operation) -> bool:
        return operation in DECLARATIONS

    def __len__(self) -> int:
        return len(DECLARATIONS)

    def get(self, operation, default=None):
        return self[operation] if operation in DECLARATIONS else default


CONTRACTS = _Contracts()


def compact_catalogue(operations):
    """Small action index used by the dynamic tool declaration."""
    return _catalogue(operations)


def exact_contract(operation: str, *, permitted: bool, project: str = "",
                   root=None, variant: str | None = None,
                   payload=None) -> dict[str, Any]:
    """One bounded help payload, generated from this operation's declaration.

    The base signature took ``owner_contract``: that was how the owner's schema came
    to be served twice for one operation --- embedded here and returned beside this
    payload by ``src/laplace/writing_tools.py:271`` --- which was 75.3 per cent of
    `help structure_change`.  The variants are built once, from the owner itself, by
    ``writing_declarations.variants``, so the parameter is REMOVED rather than kept
    as a no-op: nothing in this tree passed it, and a shim with no expiry is the
    same defect at one remove.  A caller that still passes it gets a TypeError that
    names it, which is the retirement notice.
    """
    # the EXACT contract: the complete rendering, not the served default (D2 help sections)
    return declarations.help_payload(operation, permitted=permitted, project=project,
                                     root=root, variant=variant, payload=payload, full=True)


def exact_action_digests(operations=None):
    """{operation: digest of its declaration} --- the name the brief already publishes."""
    return declarations.exact_action_digests(operations)
