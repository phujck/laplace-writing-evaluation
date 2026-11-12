"""One dispatch per verb; the concept carries the specialisation.

The friction report of 2026-10-01 measured the disease this module ends: 152 verbs through
73 operation names, create-a-unit spelled five ways at five altitudes with four guard
spellings, and a banked row that records the OPERATION name rather than the act
(``writing_tools.py:1017-971``, ``:1000-1006``).  The grammar packet
(``evidence/WRITING_RECONCILIATION_2026-10-02/grammar/GRAMMAR.md``) fixed the alphabet:
nine verbs, 58 home kinds, ``<object>@<altitude>`` concepts, one request shape, one token.
This module is the dispatch that alphabet implies.

WHAT IT IS, EXACTLY
-------------------
``ROUTES`` is one row per (verb, concept, selector) -> one EXISTING owner call.  No owner
is rewritten and no owner is re-implemented here: every route names the branch of
``writing_tools._execute`` that already reaches the owner, by file and line, and the call
that leaves this module is the same ``(operation, payload)`` pair the old name produced.
That is not a style choice, it is the campaign's acceptance condition: differential replay
over the recorded corpus must be byte-identical, so the only safe reconciliation is one
that changes the SPELLING of the request and nothing the owner receives.

The table is generated from ``tests/grammar_spec/mapping.csv`` by the maintained tool
``tools/writing_verbs/gen_routes.py``, and
``tests/test_writing_verbs.py`` regenerates it and fails on any drift.  A hand-maintained
second table is the 20-names defect with a new spelling.

THE TWO DIRECTIONS, AND WHY BOTH EXIST
--------------------------------------
``from_owner_call(operation, payload)``  -- the SHIM direction.  An old name arrives; the
    route is selected by its own discriminator (``operation=``, ``view=``, ``mode=``,
    ``action=``, ``basis=``, ``status=``, ``op.kind=``), the old guard names are lifted out
    of the payload into ``expected`` as grammar tokens, and a grammar ``Request`` comes
    back.  This is what gives the banked row its verb, concept and altitude on EVERY
    caller path -- not only inside a provider turn.

``to_owner_call(request)``            -- the VERB direction.  A caller writes one request
    per act at any altitude and this rebuilds the owner call.  It is the exact inverse:
    ``to_owner_call(from_owner_call(op, payload)) == (op, payload)`` is asserted for every
    replayable TOOL-door row of the recorded corpus (559 of its 567 replayable rows; the other
    eight are HTTP routes and not tool operations) by
    ``tests/test_writing_verbs.py::test_the_round_trip_is_the_identity_on_the_whole_corpus``,
    and it is checked AGAIN at runtime on every live call (``classify``'s ``exact`` flag).
    A call whose round trip is not exact falls through to the legacy payload untouched,
    so a gap in this table can never change what an owner receives.

GUARD FORMS: why three, and not one
-----------------------------------
A token's digest is the owner's own published value for a recipe ``O`` or ``B`` home
(GRAMMAR.md §1), so ``expected`` -> owner guard is verbatim for 104 of the 110 guard
values in the recorded corpus (measured; see the lane report).  Two guards are not digests
and the table says so rather than pretending:

* ``counter``  -- the ``authoring-state`` home.  Its door compares a monotone integer
  (``pipeline/authoring.py:400-399``), not a digest.  A token over ``authoring.json``
  cannot BE that integer, so the route restores the integer: when the token matches the
  current file the owner is handed its own current counter, and when it does not the token
  travels instead, so the owner refuses in its own house with its own sentence
  (``revision conflict: expected ..., current N``).  Zero rows of the recorded corpus
  exercise this path (measured), which is why it is stated rather than relied on.
* ``text``     -- ``before``.  The editor's rewrite door and ``store_artifact`` compare the
  exact previous TEXT (``review_surface.py:1860``, ``manuscript_blocks.py:166``), and no
  digest reconstructs text.  So the text travels in the payload as CONTENT under one
  uniform name, ``before_content``, exactly as GRAMMAR.md §2 already rules for a span's
  ``anchor_text``; the identity beside it is the ``prose`` / ``artifact`` token in
  ``expected``.  A new caller may send the token ALONE: the dispatch then reads the
  addressed bytes, and hands them to the owner only when their digest matches the token.
* ``cursor``   -- ``conversation_history``'s ``before`` is a pagination cursor and not an
  identity at all (``writing_contracts.py:386``; GRAMMAR.md §2.1 records it as a miscount
  in the 20-name census).  It travels as ``page_cursor``.

WHAT THIS MODULE DELIBERATELY DOES NOT DO
-----------------------------------------
It does not gate.  ``require`` is the grammar's comparison and it runs AFTER the owner has
refused, to build ``needed``; it never refuses before the owner is called.  The reason is
measured: the oracle compares the innermost owner frame that raised
(``harness/_worker.py:owner_home``) and 94 of the 210 recorded refusals are identity
mismatches.  A pre-owner gate would move the home of every one of them -- it would read as
a cured refusal and be a moved one.  The grammar's resolver is added where the refusal is
formatted, so no refusal loses its house.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Mapping

from laplace.core import grammar as g

# --------------------------------------------------------------------------- #
# The route
# --------------------------------------------------------------------------- #
#: A guard that is not a digest.  The third element of a ``Route.guards`` entry.
FORMS = ("digest", "counter", "text", "cursor")

#: The payload key a non-digest guard travels under inside a request.  One name per form,
#: declared here so no route invents a second spelling, and none of them is guard-shaped
#: (``identity_names.GUARD_KEY`` matches ``revision|digest|sha256|currentness``), so
#: carrying a guard as content cannot raise the identity-name census.
CARRIERS = {"text": "before_content", "cursor": "page_cursor"}

#: An owner payload key that collides with one of the request's six FIXED fields, so the
#: grammar refuses it in a payload (``Request.__post_init__``).  ``target`` is the real
#: spelling of an edge's far endpoint, declared top-level by ``logical_plan_change connect``
#: at ``writing_contracts.py:607``; the owner's name is restored on the way out.  Measured: 2
#: recorded rows carry a top-level ``target`` and one of them APPLIED, so the shape is live.
#:
#: THIS LANE NO LONGER DECLARES IT.  Round 2 of this lane declared the carrier here and
#: reported the collision to the grammar packet, which then declared it in the shared module
#: (``grammar.PAYLOAD_CARRIERS``, ``src/laplace/grammar.py:1188``, with import-time checks at
#: ``:1401-1414``) together with the two functions that perform the rename.  Two declarations
#: of one rename is the twenty-names defect in a new spelling, so this name is now a VIEW of
#: the grammar's table and the rename itself travels through ``g.to_payload`` /
#: ``g.to_owner_payload`` -- one spelling of the owner's key, one place that moves it.
FIELD_CARRIERS = {key: carrier for key, (carrier, _because) in g.PAYLOAD_CARRIERS.items()}


@dataclass(frozen=True)
class Route:
    """One (verb, concept, selector) -> one existing owner call."""
    verb: str
    concept: str
    operation: str                                  # the old operation name
    selector: tuple[tuple[str, str], ...] = ()      # dotted payload path -> literal value
    lift: tuple[tuple[str, str], ...] = ()          # the selector pairs taken OUT of the
    #                                                 payload: those that name the ACT
    guards: tuple[tuple[str, str, str, bool], ...] = ()   # (old name, homes, form, optional)
    owner: str = ""                                 # the owner call _execute makes
    site: str = ""                                  # src/laplace/<file>.py:<line>
    when: tuple[tuple[str, str], ...] = ()          # payload keys (and optional values)
    door: str = "both"                              # "both", "shim" (old name only), "http"
    because: str = ""                               # why, when door == "shim"
    route: str = ""                                 # the HTTP path, when door == "http"
    method: str = ""                                # GET or POST, when door == "http"
    source_operation: str = ""                      # existing tool owner whose acts/guards this HTTP door reuses
    alias_of: str = ""                              # an old spelling the owner normalises
    #: Every route is reachable through its old name until replay parity retires the shim.
    expiry: str = ("retire on WRITING-RECONCILIATION-W1 replay parity through the verb "
                   "door alone; review 2026-11-01")

    @property
    def altitude(self) -> str:
        return g.concept_altitude(self.concept)

    @property
    def object(self) -> str:
        return g.concept_object(self.concept)

    @property
    def key(self) -> tuple[str, str, tuple[tuple[str, str], ...]]:
        return (self.verb, self.concept, self.selector)

    @property
    def keep(self) -> tuple[tuple[str, str], ...]:
        """The selector pairs that stay in the payload: the projection of the ask."""
        lifted = set(self.lift)
        return tuple(pair for pair in self.selector if pair not in lifted)


# --------------------------------------------------------------------------- #
# BEGIN ROUTES (generated by gen_routes.py from mapping.csv; do not edit by hand)
# -------------------------------------------------------------------------
ROUTES: tuple[Route, ...] = (
    Route(verb='bind', concept='claim-position@section', operation='structure_change',
          selector=(('operation', 'plan'), ('op.kind', 'set-serves')),
          lift=(('operation', 'plan'), ('op.kind', 'set-serves')),
          guards=(('expected_revision', 'plan', 'digest', False),),
          expiry='retire `structure_change operation=plan op.kind=set-serves` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `bind claim-position@section` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_structure.change(project, payload, root,actor={'kind':'agent','turn_id':turn_id,'mode':mode,'dispatch_id':admitt",
          site='src/laplace/writing/operations.py:273'),
    Route(verb='bind', concept='concept-node@claim', operation='research_object_change',
          selector=(('operation', 'bind-consumed'),),
          lift=(('operation', 'bind-consumed'),),
          expiry='retire `research_object_change operation=bind-consumed` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `bind concept-node@claim` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="object_facets.change(root, owner_discovery.project_scope(project, 'native'), payload,",
          site='src/laplace/writing/operations.py:407'),
    Route(verb='bind', concept='plan-section@section', operation='structure_change',
          selector=(('operation', 'bind_source'),),
          lift=(('operation', 'bind_source'),),
          guards=(('expected_plan_revision', 'plan-file', 'digest', False),),
          expiry='retire `structure_change operation=bind_source` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `bind plan-section@section` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_structure.change(project, payload, root,actor={'kind':'agent','turn_id':turn_id,'mode':mode,'dispatch_id':admitt",
          site='src/laplace/writing/operations.py:273'),
    Route(verb='bind', concept='reference@evidence', operation='literature_bind',
          selector=(),
          lift=(),
          guards=(('claim_revision', 'claim-meaning', 'digest', True),),
          expiry='retire `literature_bind` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `bind reference@evidence` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='references_surface.handle("/references/literature-bind", POST)',
          site='src/laplace/writing/operations.py:472'),
    Route(verb='bind', concept='reference@section', operation='structure_change',
          selector=(('operation', 'plan'), ('op.kind', 'set-refs')),
          lift=(('operation', 'plan'), ('op.kind', 'set-refs')),
          guards=(('expected_revision', 'plan', 'digest', False),),
          expiry='retire `structure_change operation=plan op.kind=set-refs` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `bind reference@section` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_structure.change(project, payload, root,actor={'kind':'agent','turn_id':turn_id,'mode':mode,'dispatch_id':admitt",
          site='src/laplace/writing/operations.py:273'),
    Route(verb='bind', concept='relation@relation', operation='concept_change',
          selector=(('operation', 'add_edge'),),
          lift=(('operation', 'add_edge'),),
          guards=(('base_revision', 'concept-network', 'digest', False), ('mutation_revision', 'concept-node', 'digest', True)),
          expiry='retire `concept_change operation=add_edge` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `bind relation@relation` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='concepts_surface.handle("/concepts/change", POST)',
          site='src/laplace/writing/operations.py:464'),
    Route(verb='bind', concept='relation@relation', operation='logical_plan_change',
          selector=(('operation', 'connect'),),
          lift=(('operation', 'connect'),),
          guards=(('base_revision', 'concept-network', 'digest', False),),
          door='shim', because='2 routes share (bind, relation@relation) and nothing in the payload chooses between them; reachable through its old name logical_plan_change operation=connect until a payload key is declared',
          expiry='HELD, not retirable by this wave: 2 routes share (bind, relation@relation) and nothing in the payload chooses between them; reachable through its old name logical_plan_change operation=connect until a payload key is declared. Retire when a payload key chooses between the routes sharing (bind, relation@relation) AND tools/writing_verbs/shim_retirement.py reports PARITY for `bind relation@relation` from evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='concepts_surface.handle("/concepts/plan/change", POST)',
          site='src/laplace/writing/operations.py:467'),
    Route(verb='bind', concept='repository@project', operation='development_source',
          selector=(('action', 'delegate'),),
          lift=(),
          expiry='retire `development_source` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `bind repository@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='development_source.handle(root, project, payload, {"origin": "native", "turn_id": turn_id})',
          site='src/laplace/writing/operations.py:307'),
    Route(verb='bind', concept='repository@project', operation='development_source',
          selector=(('action', 'grant'),),
          lift=(),
          expiry='retire `development_source` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `bind repository@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='development_source.handle(root, project, payload, {"origin": "native", "turn_id": turn_id})',
          site='src/laplace/writing/operations.py:307'),
    Route(verb='bind', concept='result@claim', operation='structure_change',
          selector=(('operation', 'bind_results'),),
          lift=(('operation', 'bind_results'),),
          guards=(('expected_concept_revision', 'concept-network', 'digest', False), ('expected_revision', 'plan', 'digest', False)),
          expiry='retire `structure_change operation=bind_results` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `bind result@claim` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_structure.change(project, payload, root,actor={'kind':'agent','turn_id':turn_id,'mode':mode,'dispatch_id':admitt",
          site='src/laplace/writing/operations.py:273'),
    Route(verb='bind', concept='source-ref@claim', operation='concept_change',
          selector=(('operation', 'set_source'),),
          lift=(('operation', 'set_source'),),
          guards=(('base_revision', 'concept-network', 'digest', True), ('mutation_revision', 'concept-node', 'digest', True)),
          expiry='retire `concept_change operation=set_source` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `bind source-ref@claim` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='concepts_surface.handle("/concepts/change", POST)',
          site='src/laplace/writing/operations.py:464'),
    Route(verb='bind', concept='task@claim', operation='logical_plan_change',
          selector=(('operation', 'route_obligation'),),
          lift=(('operation', 'route_obligation'),),
          guards=(('base_revision', 'concept-network', 'digest', False),),
          expiry='retire `logical_plan_change operation=route_obligation` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `bind task@claim` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='concepts_surface.handle("/concepts/plan/change", POST)',
          site='src/laplace/writing/operations.py:467'),
    Route(verb='bind', concept='task@evidence', operation='work_delivery',
          selector=(('action', 'bind'),),
          lift=(),
          expiry='retire `work_delivery` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `bind task@evidence` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='work_delivery.handle(root, project, payload, {"origin": "native", "turn_id": turn_id})',
          site='src/laplace/writing/operations.py:312'),
    Route(verb='change', concept='architecture-profile@project', operation='profile_change',
          selector=(('family', 'architecture'), ('scope', 'workspace'), ('action', 'confirm')),
          lift=(),
          expiry='retire `profile_change` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change architecture-profile@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='profiles.change(project, values, root, actor=actor)',
          site='src/laplace/writing/operations.py:430'),
    Route(verb='change', concept='architecture-profile@project', operation='profile_change',
          selector=(('family', 'architecture'), ('scope', 'workspace'), ('action', 'propose')),
          lift=(),
          expiry='retire `profile_change` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change architecture-profile@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='profiles.change(project, values, root, actor=actor)',
          site='src/laplace/writing/operations.py:430'),
    Route(verb='change', concept='argument@plan', operation='argument',
          selector=(),
          lift=(),
          guards=(('base_revision', 'authoring-state', 'counter', False),),
          expiry='retire `argument` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change argument@plan` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='authoring.save(project, payload, root)',
          site='src/laplace/writing/operations.py:296'),
    Route(verb='change', concept='artifact@paragraph', operation='structure_change',
          selector=(('operation', 'paragraph_plan'),),
          lift=(('operation', 'paragraph_plan'),),
          guards=(('expected_plan_revision', 'plan-file', 'digest', False),),
          expiry='retire `structure_change operation=paragraph_plan` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change artifact@paragraph` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_structure.change(project, payload, root,actor={'kind':'agent','turn_id':turn_id,'mode':mode,'dispatch_id':admitt",
          site='src/laplace/writing/operations.py:273'),
    Route(verb='change', concept='artifact@project', operation='research_handover',
          selector=(('action', 'export'),),
          lift=(),
          expiry='retire `research_handover` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change artifact@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_handover.object_request(root, owner_discovery.project_scope(project, 'native'),",
          site='src/laplace/writing/operations.py:411'),
    Route(verb='change', concept='artifact@project', operation='store_artifact',
          selector=(),
          lift=(),
          guards=(('before', 'artifact', 'text', False),),
          expiry='retire `store_artifact` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change artifact@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='artifacts.store(root, project, payload, turn_id)',
          site='src/laplace/writing/operations.py:404'),
    Route(verb='change', concept='artifact@section', operation='structure_change',
          selector=(('operation', 'section_contract'),),
          lift=(('operation', 'section_contract'),),
          guards=(('expected_plan_revision', 'plan-file', 'digest', False),),
          expiry='retire `structure_change operation=section_contract` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change artifact@section` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_structure.change(project, payload, root,actor={'kind':'agent','turn_id':turn_id,'mode':mode,'dispatch_id':admitt",
          site='src/laplace/writing/operations.py:273'),
    Route(verb='change', concept='block@paragraph', operation='block_change',
          selector=(('operation', 'undo'),),
          lift=(('operation', 'undo'),),
          expiry='retire `block_change operation=undo` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change block@paragraph` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='manuscript_blocks.change(root, project, payload)',
          site='src/laplace/writing/operations.py:194'),
    Route(verb='change', concept='claim-meaning@claim', operation='logical_plan_change',
          selector=(('operation', 'edit_meaning'),),
          lift=(('operation', 'edit_meaning'),),
          guards=(('base_revision', 'concept-network', 'digest', False),),
          expiry='retire `logical_plan_change operation=edit_meaning` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change claim-meaning@claim` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='concepts_surface.handle("/concepts/plan/change", POST)',
          site='src/laplace/writing/operations.py:467'),
    Route(verb='change', concept='concept-node@claim', operation='concept_change',
          selector=(('operation', 'edit_node'),),
          lift=(('operation', 'edit_node'),),
          guards=(('base_revision', 'concept-network', 'digest', True), ('mutation_revision', 'concept-node', 'digest', True)),
          expiry='retire `concept_change operation=edit_node` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change concept-node@claim` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='concepts_surface.handle("/concepts/change", POST)',
          site='src/laplace/writing/operations.py:464'),
    Route(verb='change', concept='concept-node@claim', operation='concept_change',
          selector=(('operation', 'set_kind'),),
          lift=(('operation', 'set_kind'),),
          guards=(('base_revision', 'concept-network', 'digest', True), ('mutation_revision', 'concept-node', 'digest', True)),
          door='shim', because='6 routes share (change, concept-node@claim) and nothing in the payload chooses between them; reachable through its old name concept_change operation=set_kind until a payload key is declared',
          expiry='HELD, not retirable by this wave: 6 routes share (change, concept-node@claim) and nothing in the payload chooses between them; reachable through its old name concept_change operation=set_kind until a payload key is declared. Retire when a payload key chooses between the routes sharing (change, concept-node@claim) AND tools/writing_verbs/shim_retirement.py reports PARITY for `change concept-node@claim` from evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='concepts_surface.handle("/concepts/change", POST)',
          site='src/laplace/writing/operations.py:464'),
    Route(verb='change', concept='concept-node@claim', operation='concept_change',
          selector=(('operation', 'set_mathematics'),),
          lift=(('operation', 'set_mathematics'),),
          guards=(('base_revision', 'concept-network', 'digest', True), ('mutation_revision', 'concept-node', 'digest', True)),
          door='shim', because='6 routes share (change, concept-node@claim) and nothing in the payload chooses between them; reachable through its old name concept_change operation=set_mathematics until a payload key is declared',
          expiry='HELD, not retirable by this wave: 6 routes share (change, concept-node@claim) and nothing in the payload chooses between them; reachable through its old name concept_change operation=set_mathematics until a payload key is declared. Retire when a payload key chooses between the routes sharing (change, concept-node@claim) AND tools/writing_verbs/shim_retirement.py reports PARITY for `change concept-node@claim` from evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='concepts_surface.handle("/concepts/change", POST)',
          site='src/laplace/writing/operations.py:464'),
    Route(verb='change', concept='concept-node@claim', operation='concept_change',
          selector=(('operation', 'set_projection'),),
          lift=(('operation', 'set_projection'),),
          guards=(('base_revision', 'concept-network', 'digest', True), ('mutation_revision', 'concept-node', 'digest', True)),
          door='shim', because='6 routes share (change, concept-node@claim) and nothing in the payload chooses between them; reachable through its old name concept_change operation=set_projection until a payload key is declared',
          expiry='HELD, not retirable by this wave: 6 routes share (change, concept-node@claim) and nothing in the payload chooses between them; reachable through its old name concept_change operation=set_projection until a payload key is declared. Retire when a payload key chooses between the routes sharing (change, concept-node@claim) AND tools/writing_verbs/shim_retirement.py reports PARITY for `change concept-node@claim` from evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='concepts_surface.handle("/concepts/change", POST)',
          site='src/laplace/writing/operations.py:464'),
    Route(verb='change', concept='concept-node@claim', operation='concept_change',
          selector=(('operation', 'set_status'),),
          lift=(('operation', 'set_status'),),
          guards=(('base_revision', 'concept-network', 'digest', True), ('mutation_revision', 'concept-node', 'digest', True)),
          door='shim', because='6 routes share (change, concept-node@claim) and nothing in the payload chooses between them; reachable through its old name concept_change operation=set_status until a payload key is declared',
          expiry='HELD, not retirable by this wave: 6 routes share (change, concept-node@claim) and nothing in the payload chooses between them; reachable through its old name concept_change operation=set_status until a payload key is declared. Retire when a payload key chooses between the routes sharing (change, concept-node@claim) AND tools/writing_verbs/shim_retirement.py reports PARITY for `change concept-node@claim` from evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='concepts_surface.handle("/concepts/change", POST)',
          site='src/laplace/writing/operations.py:464'),
    Route(verb='change', concept='concept-node@claim', operation='research_object_change',
          selector=(('operation', 'settle-question'),),
          lift=(('operation', 'settle-question'),),
          door='shim', because='6 routes share (change, concept-node@claim) and nothing in the payload chooses between them; reachable through its old name research_object_change operation=settle-question until a payload key is declared',
          expiry='HELD, not retirable by this wave: 6 routes share (change, concept-node@claim) and nothing in the payload chooses between them; reachable through its old name research_object_change operation=settle-question until a payload key is declared. Retire when a payload key chooses between the routes sharing (change, concept-node@claim) AND tools/writing_verbs/shim_retirement.py reports PARITY for `change concept-node@claim` from evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="object_facets.change(root, owner_discovery.project_scope(project, 'native'), payload,",
          site='src/laplace/writing/operations.py:407'),
    Route(verb='change', concept='document-form@project', operation='style',
          selector=(),
          lift=(),
          expiry='retire `style` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change document-form@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="document_templates.change(project,{key:value for key,value in payload.items() if key!='project'},root,",
          site='src/laplace/writing/operations.py:218'),
    Route(verb='change', concept='framing@plan', operation='framing',
          selector=(),
          lift=(),
          guards=(('base_revision', 'authoring-state', 'counter', False),),
          expiry='retire `framing` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change framing@plan` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='project_work.framing(project, payload, root)',
          site='src/laplace/writing/operations.py:294'),
    Route(verb='change', concept='guide-catalogue@project', operation='project_guidance_change',
          selector=(('operation', 'configure'),),
          lift=(('operation', 'configure'),),
          guards=(('before', 'guide-document', 'text', True), ('expected_catalog_revision', 'guide-catalogue', 'digest', False)),
          expiry='retire `project_guidance_change operation=configure` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change guide-catalogue@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='project_protocol.change(project, payload, root)',
          site='src/laplace/writing/operations.py:447'),
    Route(verb='change', concept='guide-document@project', operation='project_guidance_change',
          selector=(('operation', 'write'),),
          lift=(('operation', 'write'),),
          guards=(('before', 'guide-document', 'text', True), ('expected_catalog_revision', 'guide-catalogue', 'digest', False)),
          expiry='retire `project_guidance_change operation=write` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change guide-document@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='project_protocol.change(project, payload, root)',
          site='src/laplace/writing/operations.py:447'),
    Route(verb='change', concept='material-reference@project', operation='material_reference_change',
          selector=(('action', 'adopt'),),
          lift=(),
          guards=(('expected_revision', 'project-metadata', 'digest', False),),
          expiry='retire `material_reference_change` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change material-reference@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='writing_projects.change_material_reference(project, {**payload, "by": "eigen:session"}, root)',
          site='src/laplace/writing/operations.py:363'),
    Route(verb='change', concept='note@claim', operation='note_status',
          selector=(('status', 'open'),),
          lift=(),
          guards=(('base_revision', 'authoring-state', 'counter', True),),
          expiry='retire `note_status` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change note@claim` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='authoring.correction_status(project, {',
          site='src/laplace/writing/operations.py:326'),
    Route(verb='change', concept='obligation@claim', operation='logical_plan_change',
          selector=(('operation', 'update_obligation'),),
          lift=(('operation', 'update_obligation'),),
          guards=(('base_revision', 'concept-network', 'digest', False),),
          expiry='retire `logical_plan_change operation=update_obligation` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change obligation@claim` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='concepts_surface.handle("/concepts/plan/change", POST)',
          site='src/laplace/writing/operations.py:467'),
    Route(verb='change', concept='plan-section@section', operation='structure_change',
          selector=(('operation', 'plan'),),
          lift=(('operation', 'plan'),),
          guards=(('expected_revision', 'plan', 'digest', False),),
          expiry='retire `structure_change operation=plan` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change plan-section@section` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_structure.change(project, payload, root,actor={'kind':'agent','turn_id':turn_id,'mode':mode,'dispatch_id':admitt",
          site='src/laplace/writing/operations.py:273'),
    Route(verb='change', concept='plan-section@section', operation='structure_change',
          selector=(('operation', 'plan'), ('op.kind', 'edit-job')),
          lift=(('operation', 'plan'), ('op.kind', 'edit-job')),
          guards=(('expected_revision', 'plan', 'digest', False),),
          door='shim', because='6 routes share (change, plan-section@section) and nothing in the payload chooses between them; reachable through its old name structure_change operation=plan op.kind=edit-job until a payload key is declared',
          expiry='HELD, not retirable by this wave: 6 routes share (change, plan-section@section) and nothing in the payload chooses between them; reachable through its old name structure_change operation=plan op.kind=edit-job until a payload key is declared. Retire when a payload key chooses between the routes sharing (change, plan-section@section) AND tools/writing_verbs/shim_retirement.py reports PARITY for `change plan-section@section` from evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_structure.change(project, payload, root,actor={'kind':'agent','turn_id':turn_id,'mode':mode,'dispatch_id':admitt",
          site='src/laplace/writing/operations.py:273'),
    Route(verb='change', concept='plan-section@section', operation='structure_change',
          selector=(('operation', 'plan'), ('op.kind', 'edit-notes')),
          lift=(('operation', 'plan'), ('op.kind', 'edit-notes')),
          guards=(('expected_revision', 'plan', 'digest', False),),
          door='shim', because='6 routes share (change, plan-section@section) and nothing in the payload chooses between them; reachable through its old name structure_change operation=plan op.kind=edit-notes until a payload key is declared',
          expiry='HELD, not retirable by this wave: 6 routes share (change, plan-section@section) and nothing in the payload chooses between them; reachable through its old name structure_change operation=plan op.kind=edit-notes until a payload key is declared. Retire when a payload key chooses between the routes sharing (change, plan-section@section) AND tools/writing_verbs/shim_retirement.py reports PARITY for `change plan-section@section` from evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_structure.change(project, payload, root,actor={'kind':'agent','turn_id':turn_id,'mode':mode,'dispatch_id':admitt",
          site='src/laplace/writing/operations.py:273'),
    Route(verb='change', concept='plan-section@section', operation='structure_change',
          selector=(('operation', 'plan'), ('op.kind', 'retitle')),
          lift=(('operation', 'plan'), ('op.kind', 'retitle')),
          guards=(('expected_revision', 'plan', 'digest', False),),
          door='shim', because='6 routes share (change, plan-section@section) and nothing in the payload chooses between them; reachable through its old name structure_change operation=plan op.kind=retitle until a payload key is declared',
          expiry='HELD, not retirable by this wave: 6 routes share (change, plan-section@section) and nothing in the payload chooses between them; reachable through its old name structure_change operation=plan op.kind=retitle until a payload key is declared. Retire when a payload key chooses between the routes sharing (change, plan-section@section) AND tools/writing_verbs/shim_retirement.py reports PARITY for `change plan-section@section` from evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_structure.change(project, payload, root,actor={'kind':'agent','turn_id':turn_id,'mode':mode,'dispatch_id':admitt",
          site='src/laplace/writing/operations.py:273'),
    Route(verb='change', concept='plan-section@section', operation='structure_change',
          selector=(('operation', 'plan'), ('op.kind', 'set-meta')),
          lift=(('operation', 'plan'), ('op.kind', 'set-meta')),
          guards=(('expected_revision', 'plan', 'digest', False),),
          door='shim', because='6 routes share (change, plan-section@section) and nothing in the payload chooses between them; reachable through its old name structure_change operation=plan op.kind=set-meta until a payload key is declared',
          expiry='HELD, not retirable by this wave: 6 routes share (change, plan-section@section) and nothing in the payload chooses between them; reachable through its old name structure_change operation=plan op.kind=set-meta until a payload key is declared. Retire when a payload key chooses between the routes sharing (change, plan-section@section) AND tools/writing_verbs/shim_retirement.py reports PARITY for `change plan-section@section` from evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_structure.change(project, payload, root,actor={'kind':'agent','turn_id':turn_id,'mode':mode,'dispatch_id':admitt",
          site='src/laplace/writing/operations.py:273'),
    Route(verb='change', concept='plan-section@section', operation='structure_change',
          selector=(('operation', 'plan'), ('op.kind', 'toggle-beat')),
          lift=(('operation', 'plan'), ('op.kind', 'toggle-beat')),
          guards=(('expected_revision', 'plan', 'digest', False),),
          door='shim', because='6 routes share (change, plan-section@section) and nothing in the payload chooses between them; reachable through its old name structure_change operation=plan op.kind=toggle-beat until a payload key is declared',
          expiry='HELD, not retirable by this wave: 6 routes share (change, plan-section@section) and nothing in the payload chooses between them; reachable through its old name structure_change operation=plan op.kind=toggle-beat until a payload key is declared. Retire when a payload key chooses between the routes sharing (change, plan-section@section) AND tools/writing_verbs/shim_retirement.py reports PARITY for `change plan-section@section` from evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_structure.change(project, payload, root,actor={'kind':'agent','turn_id':turn_id,'mode':mode,'dispatch_id':admitt",
          site='src/laplace/writing/operations.py:273'),
    Route(verb='change', concept='plan@plan', operation='structure_change',
          selector=(('operation', 'plan'), ('op.kind', 'set-outline')),
          lift=(('operation', 'plan'), ('op.kind', 'set-outline')),
          guards=(('expected_revision', 'plan', 'digest', False),),
          expiry='retire `structure_change operation=plan op.kind=set-outline` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change plan@plan` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_structure.change(project, payload, root,actor={'kind':'agent','turn_id':turn_id,'mode':mode,'dispatch_id':admitt",
          site='src/laplace/writing/operations.py:273'),
    Route(verb='change', concept='profile-candidate@project', operation='profile_change',
          selector=(('action', 'apply'),),
          lift=(),
          expiry='retire `profile_change` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change profile-candidate@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='profiles.change(project, values, root, actor=actor)',
          site='src/laplace/writing/operations.py:430'),
    Route(verb='change', concept='project-metadata@project', operation='project_metadata_change',
          selector=(),
          lift=(),
          guards=(('expected_revision', 'project-metadata', 'digest', False),),
          expiry='retire `project_metadata_change` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change project-metadata@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='writing_projects.change_metadata(project,',
          site='src/laplace/writing/operations.py:366'),
    Route(verb='change', concept='prose@paragraph', operation='apply_revision',
          selector=(),
          lift=(),
          guards=(('before', 'prose', 'text', True),),
          expiry='retire `apply_revision` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change prose@paragraph` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='source_application.apply_revision(root, project, turn_id, payload)',
          site='src/laplace/writing/operations.py:178'),
    Route(verb='change', concept='reference@evidence', operation='reference_update',
          selector=(),
          lift=(),
          expiry='retire `reference_update` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change reference@evidence` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='references_surface.handle("/references/update", POST)',
          site='src/laplace/writing/operations.py:481'),
    Route(verb='change', concept='relation@relation', operation='concept_change',
          selector=(('operation', 'retype_edge'),),
          lift=(('operation', 'retype_edge'),),
          guards=(('base_revision', 'concept-network', 'digest', False), ('mutation_revision', 'concept-node', 'digest', True)),
          expiry='retire `concept_change operation=retype_edge` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change relation@relation` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='concepts_surface.handle("/concepts/change", POST)',
          site='src/laplace/writing/operations.py:464'),
    Route(verb='change', concept='repository-file@paragraph', operation='development_source',
          selector=(('action', 'apply'),),
          lift=(),
          expiry='retire `development_source` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change repository-file@paragraph` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='development_source.handle(root, project, payload, {"origin": "native", "turn_id": turn_id})',
          site='src/laplace/writing/operations.py:307'),
    Route(verb='change', concept='repository@project', operation='development_source',
          selector=(('action', 'revoke'),),
          lift=(),
          expiry='retire `development_source` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change repository@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='development_source.handle(root, project, payload, {"origin": "native", "turn_id": turn_id})',
          site='src/laplace/writing/operations.py:307'),
    Route(verb='change', concept='result-binding@evidence', operation='research_reconcile',
          selector=(),
          lift=(),
          expiry='retire `research_reconcile` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change result-binding@evidence` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='_owner_answer(research_records.reconcile(named, payload, root=root))',
          site='src/laplace/writing/operations.py:524'),
    Route(verb='change', concept='run@run', operation='run_cancel',
          selector=(),
          lift=(),
          expiry='retire `run_cancel` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change run@run` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='_owner_answer(research_runs.cancel(named, payload, Path(root)))',
          site='src/laplace/writing/operations.py:532'),
    Route(verb='change', concept='section@section', operation='section_change',
          selector=(('operation', 'convert'),),
          lift=(('operation', 'convert'),),
          guards=(('expected_plan_revision', 'plan|plan-file', 'digest', True), ('expected_source_digest', 'source-file', 'digest', False)),
          expiry='retire `section_change operation=convert` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change section@section` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='manuscript_structure.change(project, payload, root)',
          site='src/laplace/writing/operations.py:191'),
    Route(verb='change', concept='style-profile@project', operation='profile_change',
          selector=(('family', 'voice'), ('scope', 'workspace'), ('action', 'propose')),
          lift=(),
          expiry='retire `profile_change` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change style-profile@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='profiles.change(project, values, root, actor=actor)',
          site='src/laplace/writing/operations.py:430'),
    Route(verb='change', concept='style-profile@project', operation='writing_style_profile_change',
          selector=(('basis', 'author_preference'),),
          lift=(),
          guards=(('expected_profile_revision', 'style-profile', 'digest', False), ('expected_provenance_revision', 'style-provenance', 'digest', True)),
          expiry='retire `writing_style_profile_change` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change style-profile@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='writing_style.update_profile(project, {k:v for k,v in payload.items() if k!="project"}, root)',
          site='src/laplace/writing/operations.py:441'),
    Route(verb='change', concept='style-profile@project', operation='writing_style_profile_change',
          selector=(('basis', 'source_calibration'),),
          lift=(),
          guards=(('expected_profile_revision', 'style-profile', 'digest', False), ('expected_provenance_revision', 'style-provenance', 'digest', False)),
          expiry='retire `writing_style_profile_change` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change style-profile@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='writing_style.update_profile(project, {k:v for k,v in payload.items() if k!="project"}, root)',
          site='src/laplace/writing/operations.py:441'),
    Route(verb='change', concept='style-state@project', operation='profile_change',
          selector=(('family', 'voice'), ('scope', 'project'), ('action', 'propose')),
          lift=(),
          expiry='retire `profile_change` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change style-state@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='profiles.change(project, values, root, actor=actor)',
          site='src/laplace/writing/operations.py:430'),
    Route(verb='change', concept='style-state@project', operation='writing_style_change',
          selector=(),
          lift=(),
          guards=(('expected_revision', 'style-state', 'digest', False),),
          expiry='retire `writing_style_change` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change style-state@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='writing_style.save(project, payload, root)',
          site='src/laplace/writing/operations.py:438'),
    Route(verb='change', concept='task@evidence', operation='task_status',
          selector=(),
          lift=(),
          expiry='retire `task_status` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change task@evidence` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='project_work.transition(project, payload, root)',
          site='src/laplace/writing/operations.py:316'),
    Route(verb='change', concept='turn@project', operation='session_settings_change',
          selector=(),
          lift=(),
          expiry='retire `session_settings_change` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change turn@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='tool_sessions.session_settings_change(root, project, payload, turn_id)',
          site='src/laplace/writing/operations.py:240'),
    Route(verb='change', concept='workflow-definition@project', operation='workflow_definition_change',
          selector=(('action', 'save'),),
          lift=(),
          expiry='retire `workflow_definition_change` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `change workflow-definition@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='tool_work.workflow_definition(root, project, mode, payload, turn_id)',
          site='src/laplace/writing/operations.py:279'),
    Route(verb='create', concept='artifact@project', operation='research_handover',
          selector=(('action', 'prepare'),),
          lift=(),
          expiry='retire `research_handover` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `create artifact@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_handover.object_request(root, owner_discovery.project_scope(project, 'native'),",
          site='src/laplace/writing/operations.py:411'),
    Route(verb='create', concept='block@paragraph', operation='block_change',
          selector=(('operation', 'insert'),),
          lift=(('operation', 'insert'),),
          expiry='retire `block_change operation=insert` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `create block@paragraph` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='manuscript_blocks.change(root, project, payload)',
          site='src/laplace/writing/operations.py:194'),
    Route(verb='create', concept='block@paragraph', operation='block_change',
          selector=(('operation', 'insert-at-caret'),),
          lift=(('operation', 'insert-at-caret'),),
          when=(('destination.paragraph', ''),),
          expiry='retire `block_change operation=insert-at-caret` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `create block@paragraph` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='manuscript_blocks.change(root, project, payload)',
          site='src/laplace/writing/operations.py:194'),
    Route(verb='create', concept='chapter@chapter', operation='chapter',
          selector=(),
          lift=(),
          guards=(('expected_root_digest', 'selected-edition', 'digest', True),),
          expiry='retire `chapter` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `create chapter@chapter` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='manuscript_structure.create_chapter(project, payload.get("title", ""), root, expected_root_digest=payload.get("expected_',
          site='src/laplace/writing/operations.py:225'),
    Route(verb='create', concept='concept-node@claim', operation='concept_change',
          selector=(('operation', 'add_node'),),
          lift=(('operation', 'add_node'),),
          guards=(('base_revision', 'concept-network', 'digest', False), ('mutation_revision', 'concept-node', 'digest', True)),
          expiry='retire `concept_change operation=add_node` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `create concept-node@claim` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='concepts_surface.handle("/concepts/change", POST)',
          site='src/laplace/writing/operations.py:464'),
    Route(verb='create', concept='concept-node@claim', operation='logical_plan_change',
          selector=(('operation', 'add_object'),),
          lift=(('operation', 'add_object'),),
          guards=(('base_revision', 'concept-network', 'digest', False),),
          door='shim', because='4 routes share (create, concept-node@claim) and nothing in the payload chooses between them; reachable through its old name logical_plan_change operation=add_object until a payload key is declared',
          expiry='HELD, not retirable by this wave: 4 routes share (create, concept-node@claim) and nothing in the payload chooses between them; reachable through its old name logical_plan_change operation=add_object until a payload key is declared. Retire when a payload key chooses between the routes sharing (create, concept-node@claim) AND tools/writing_verbs/shim_retirement.py reports PARITY for `create concept-node@claim` from evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='concepts_surface.handle("/concepts/plan/change", POST)',
          site='src/laplace/writing/operations.py:467'),
    Route(verb='create', concept='concept-node@claim', operation='research_object_change',
          selector=(('operation', 'save-object'),),
          lift=(('operation', 'save-object'),),
          door='shim', because='4 routes share (create, concept-node@claim) and nothing in the payload chooses between them; reachable through its old name research_object_change operation=save-object until a payload key is declared',
          expiry='HELD, not retirable by this wave: 4 routes share (create, concept-node@claim) and nothing in the payload chooses between them; reachable through its old name research_object_change operation=save-object until a payload key is declared. Retire when a payload key chooses between the routes sharing (create, concept-node@claim) AND tools/writing_verbs/shim_retirement.py reports PARITY for `create concept-node@claim` from evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="object_facets.change(root, owner_discovery.project_scope(project, 'native'), payload,",
          site='src/laplace/writing/operations.py:407'),
    Route(verb='create', concept='concept-node@claim', operation='research_object_change',
          selector=(('operation', 'save-question'),),
          lift=(('operation', 'save-question'),),
          door='shim', because='4 routes share (create, concept-node@claim) and nothing in the payload chooses between them; reachable through its old name research_object_change operation=save-question until a payload key is declared',
          expiry='HELD, not retirable by this wave: 4 routes share (create, concept-node@claim) and nothing in the payload chooses between them; reachable through its old name research_object_change operation=save-question until a payload key is declared. Retire when a payload key chooses between the routes sharing (create, concept-node@claim) AND tools/writing_verbs/shim_retirement.py reports PARITY for `create concept-node@claim` from evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="object_facets.change(root, owner_discovery.project_scope(project, 'native'), payload,",
          site='src/laplace/writing/operations.py:407'),
    Route(verb='create', concept='heading@section', operation='section_change',
          selector=(('operation', 'insert-heading'),),
          lift=(('operation', 'insert-heading'),),
          guards=(('expected_plan_revision', 'plan|plan-file', 'digest', True), ('expected_source_digest', 'source-file', 'digest', False)),
          expiry='retire `section_change operation=insert-heading` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `create heading@section` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='manuscript_structure.change(project, payload, root)',
          site='src/laplace/writing/operations.py:191'),
    Route(verb='create', concept='material-reference@project', operation='material_reference_change',
          selector=(('action', 'attach'),),
          lift=(),
          guards=(('expected_revision', 'project-metadata', 'digest', False),),
          expiry='retire `material_reference_change` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `create material-reference@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='writing_projects.change_material_reference(project, {**payload, "by": "eigen:session"}, root)',
          site='src/laplace/writing/operations.py:363'),
    Route(verb='create', concept='note@claim', operation='note',
          selector=(),
          lift=(),
          expiry='retire `note` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `create note@claim` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='authoring.bank_correction(project, {**payload, "by":"eigen:review" if mode == "review" else "eigen:session"}, root)',
          site='src/laplace/writing/operations.py:322'),
    Route(verb='create', concept='obligation@claim', operation='logical_plan_change',
          selector=(('operation', 'add_obligation'),),
          lift=(('operation', 'add_obligation'),),
          guards=(('base_revision', 'concept-network', 'digest', False),),
          expiry='retire `logical_plan_change operation=add_obligation` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `create obligation@claim` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='concepts_surface.handle("/concepts/plan/change", POST)',
          site='src/laplace/writing/operations.py:467'),
    Route(verb='create', concept='plan-section@section', operation='structure_change',
          selector=(('operation', 'plan'), ('op.kind', 'add-section')),
          lift=(('operation', 'plan'), ('op.kind', 'add-section')),
          guards=(('expected_revision', 'plan', 'digest', False),),
          expiry='retire `structure_change operation=plan op.kind=add-section` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `create plan-section@section` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_structure.change(project, payload, root,actor={'kind':'agent','turn_id':turn_id,'mode':mode,'dispatch_id':admitt",
          site='src/laplace/writing/operations.py:273'),
    Route(verb='create', concept='plan-section@section', operation='structure_change',
          selector=(('operation', 'plan'), ('op.kind', 'restore-section')),
          lift=(('operation', 'plan'), ('op.kind', 'restore-section')),
          guards=(('expected_revision', 'plan', 'digest', False),),
          door='shim', because='2 routes share (create, plan-section@section) and nothing in the payload chooses between them; reachable through its old name structure_change operation=plan op.kind=restore-section until a payload key is declared',
          expiry='HELD, not retirable by this wave: 2 routes share (create, plan-section@section) and nothing in the payload chooses between them; reachable through its old name structure_change operation=plan op.kind=restore-section until a payload key is declared. Retire when a payload key chooses between the routes sharing (create, plan-section@section) AND tools/writing_verbs/shim_retirement.py reports PARITY for `create plan-section@section` from evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_structure.change(project, payload, root,actor={'kind':'agent','turn_id':turn_id,'mode':mode,'dispatch_id':admitt",
          site='src/laplace/writing/operations.py:273'),
    Route(verb='create', concept='plan@plan', operation='structure_change',
          selector=(('operation', 'initialize'),),
          lift=(('operation', 'initialize'),),
          guards=(('expected_revision', 'plan', 'digest', False), ('expected_source_revision', 'selected-edition', 'digest', False)),
          expiry='retire `structure_change operation=initialize` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `create plan@plan` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_structure.change(project, payload, root,actor={'kind':'agent','turn_id':turn_id,'mode':mode,'dispatch_id':admitt",
          site='src/laplace/writing/operations.py:273'),
    Route(verb='create', concept='plan@plan', operation='structure_change',
          selector=(('operation', 'start_authoring'),),
          lift=(('operation', 'start_authoring'),),
          guards=(('expected_project_lifecycle', 'project-lifecycle', 'digest', False),),
          door='shim', because='2 routes share (create, plan@plan) and nothing in the payload chooses between them; reachable through its old name structure_change operation=start_authoring until a payload key is declared',
          expiry='HELD, not retirable by this wave: 2 routes share (create, plan@plan) and nothing in the payload chooses between them; reachable through its old name structure_change operation=start_authoring until a payload key is declared. Retire when a payload key chooses between the routes sharing (create, plan@plan) AND tools/writing_verbs/shim_retirement.py reports PARITY for `create plan@plan` from evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_structure.change(project, payload, root,actor={'kind':'agent','turn_id':turn_id,'mode':mode,'dispatch_id':admitt",
          site='src/laplace/writing/operations.py:273'),
    Route(verb='create', concept='producer@run', operation='research_producer',
          selector=(),
          lift=(),
          expiry='retire `research_producer` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `create producer@run` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='_owner_answer(research_runs.register_producer(named, payload, root=root))',
          site='src/laplace/writing/operations.py:528'),
    Route(verb='create', concept='proposal@paragraph', operation='propose_revision',
          selector=(),
          lift=(),
          expiry='retire `propose_revision` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `create proposal@paragraph` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='tool_source.propose_revision(root, project, payload, turn_id)',
          site='src/laplace/writing/operations.py:197'),
    Route(verb='create', concept='reference@evidence', operation='literature_import',
          selector=(),
          lift=(),
          expiry='retire `literature_import` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `create reference@evidence` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='references_surface.handle("/references/literature-import", POST)',
          site='src/laplace/writing/operations.py:471'),
    Route(verb='create', concept='reference@evidence', operation='reference_attach',
          selector=(),
          lift=(),
          door='shim', because='2 routes share (create, reference@evidence) and nothing in the payload chooses between them; reachable through its old name reference_attach until a payload key is declared',
          expiry='HELD, not retirable by this wave: 2 routes share (create, reference@evidence) and nothing in the payload chooses between them; reachable through its old name reference_attach until a payload key is declared. Retire when a payload key chooses between the routes sharing (create, reference@evidence) AND tools/writing_verbs/shim_retirement.py reports PARITY for `create reference@evidence` from evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='references_surface.handle("/references/attach", POST)',
          site='src/laplace/writing/operations.py:480'),
    Route(verb='create', concept='repository-file@paragraph', operation='development_source',
          selector=(('action', 'candidate'),),
          lift=(),
          expiry='retire `development_source` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `create repository-file@paragraph` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='development_source.handle(root, project, payload, {"origin": "native", "turn_id": turn_id})',
          site='src/laplace/writing/operations.py:307'),
    Route(verb='create', concept='section@section', operation='section_change',
          selector=(('operation', 'create'),),
          lift=(('operation', 'create'),),
          guards=(('expected_plan_revision', 'plan|plan-file', 'digest', True), ('expected_source_digest', 'source-file', 'digest', False)),
          expiry='retire `section_change operation=create` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `create section@section` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='manuscript_structure.change(project, payload, root)',
          site='src/laplace/writing/operations.py:191'),
    Route(verb='create', concept='section@section', operation='section_change',
          selector=(('operation', 'restore'),),
          lift=(('operation', 'restore'),),
          guards=(('expected_plan_revision', 'plan|plan-file', 'digest', True), ('expected_source_digest', 'source-file', 'digest', False)),
          when=(('receipt_id', ''),),
          expiry='retire `section_change operation=restore` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `create section@section` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='manuscript_structure.change(project, payload, root)',
          site='src/laplace/writing/operations.py:191'),
    Route(verb='create', concept='task@project', operation='dispatch_plan',
          selector=(),
          lift=(),
          expiry='retire `dispatch_plan` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `create task@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='tool_work.dispatch(root, project, mode, operation, payload, turn_id, observe_reads=observe_reads)',
          site='src/laplace/writing/operations.py:252'),
    Route(verb='create', concept='task@project', operation='structure_change',
          selector=(('operation', 'prepare_work'),),
          lift=(('operation', 'prepare_work'),),
          guards=(('expected_plan_revision', 'plan-file', 'digest', False),),
          when=(('expected_selection', ''), ('section_ids', '')),
          expiry='retire `structure_change operation=prepare_work` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `create task@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_structure.change(project, payload, root,actor={'kind':'agent','turn_id':turn_id,'mode':mode,'dispatch_id':admitt",
          site='src/laplace/writing/operations.py:273'),
    Route(verb='create', concept='task@project', operation='workflow_definition_change',
          selector=(('action', 'prepare'),),
          lift=(),
          expiry='retire `workflow_definition_change` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `create task@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='tool_work.workflow_definition(root, project, mode, payload, turn_id)',
          site='src/laplace/writing/operations.py:279'),
    Route(verb='create', concept='task@section', operation='task',
          selector=(),
          lift=(),
          expiry='retire `task` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `create task@section` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='project_work.task(project, payload, root)',
          site='src/laplace/writing/operations.py:298'),
    Route(verb='create', concept='visual-spec@run', operation='visual_create',
          selector=(),
          lift=(),
          guards=(('expected_revision', 'visual-spec', 'digest', True),),
          expiry='retire `visual_create` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `create visual-spec@run` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='visuals_surface.handle("/visuals/create", POST)',
          site='src/laplace/writing/operations.py:484'),
    Route(verb='delete', concept='block@paragraph', operation='block_change',
          selector=(('operation', 'delete'),),
          lift=(('operation', 'delete'),),
          expiry='retire `block_change operation=delete` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `delete block@paragraph` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='manuscript_blocks.change(root, project, payload)',
          site='src/laplace/writing/operations.py:194'),
    Route(verb='delete', concept='claim-position@section', operation='structure_change',
          selector=(('operation', 'plan'), ('op.kind', 'remove-node')),
          lift=(('operation', 'plan'), ('op.kind', 'remove-node')),
          guards=(('expected_revision', 'plan', 'digest', False),),
          expiry='retire `structure_change operation=plan op.kind=remove-node` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `delete claim-position@section` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_structure.change(project, payload, root,actor={'kind':'agent','turn_id':turn_id,'mode':mode,'dispatch_id':admitt",
          site='src/laplace/writing/operations.py:273'),
    Route(verb='delete', concept='material-reference@project', operation='material_reference_change',
          selector=(('action', 'remove'),),
          lift=(),
          guards=(('expected_revision', 'project-metadata', 'digest', False),),
          expiry='retire `material_reference_change` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `delete material-reference@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='writing_projects.change_material_reference(project, {**payload, "by": "eigen:session"}, root)',
          site='src/laplace/writing/operations.py:363'),
    Route(verb='delete', concept='note@claim', operation='note_status',
          selector=(('status', 'dismissed'),),
          lift=(),
          guards=(('base_revision', 'authoring-state', 'counter', True),),
          expiry='retire `note_status` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `delete note@claim` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='authoring.correction_status(project, {',
          site='src/laplace/writing/operations.py:326'),
    Route(verb='delete', concept='note@claim', operation='note_status',
          selector=(('status', 'resolved'),),
          lift=(),
          guards=(('base_revision', 'authoring-state', 'counter', True),),
          expiry='retire `note_status` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `delete note@claim` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='authoring.correction_status(project, {',
          site='src/laplace/writing/operations.py:326'),
    Route(verb='delete', concept='plan-section@section', operation='structure_change',
          selector=(('operation', 'plan'), ('op.kind', 'remove-section')),
          lift=(('operation', 'plan'), ('op.kind', 'remove-section')),
          guards=(('expected_revision', 'plan', 'digest', False),),
          expiry='retire `structure_change operation=plan op.kind=remove-section` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `delete plan-section@section` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_structure.change(project, payload, root,actor={'kind':'agent','turn_id':turn_id,'mode':mode,'dispatch_id':admitt",
          site='src/laplace/writing/operations.py:273'),
    Route(verb='delete', concept='proposal@paragraph', operation='proposal_supersede',
          selector=(),
          lift=(),
          expiry='retire `proposal_supersede` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `delete proposal@paragraph` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='manuscript_proposals.supersede(',
          site='src/laplace/writing/operations.py:199'),
    Route(verb='delete', concept='relation@relation', operation='concept_change',
          selector=(('operation', 'remove_edge'),),
          lift=(('operation', 'remove_edge'),),
          guards=(('base_revision', 'concept-network', 'digest', False), ('mutation_revision', 'concept-node', 'digest', True)),
          expiry='retire `concept_change operation=remove_edge` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `delete relation@relation` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='concepts_surface.handle("/concepts/change", POST)',
          site='src/laplace/writing/operations.py:464'),
    Route(verb='delete', concept='section@section', operation='section_change',
          selector=(('operation', 'delete'),),
          lift=(('operation', 'delete'),),
          guards=(('expected_plan_revision', 'plan|plan-file', 'digest', True), ('expected_source_digest', 'source-file', 'digest', False)),
          expiry='retire `section_change operation=delete` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `delete section@section` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='manuscript_structure.change(project, payload, root)',
          site='src/laplace/writing/operations.py:191'),
    Route(verb='delete', concept='section@section', operation='section_change',
          selector=(('operation', 'undo-create'),),
          lift=(('operation', 'undo-create'),),
          guards=(('expected_plan_revision', 'plan|plan-file', 'digest', True), ('expected_source_digest', 'source-file', 'digest', False)),
          when=(('receipt_id', ''),),
          expiry='retire `section_change operation=undo-create` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `delete section@section` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='manuscript_structure.change(project, payload, root)',
          site='src/laplace/writing/operations.py:191'),
    Route(verb='delete', concept='spine-position@plan', operation='concept_change',
          selector=(('operation', 'unset_spine'),),
          lift=(('operation', 'unset_spine'),),
          guards=(('base_revision', 'concept-network', 'digest', False), ('mutation_revision', 'concept-node', 'digest', True)),
          expiry='retire `concept_change operation=unset_spine` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `delete spine-position@plan` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='concepts_surface.handle("/concepts/change", POST)',
          site='src/laplace/writing/operations.py:464'),
    Route(verb='delete', concept='spine-position@plan', operation='structure_change',
          selector=(('operation', 'spine'), ('op.kind', 'unset-spine')),
          lift=(('operation', 'spine'), ('op.kind', 'unset-spine')),
          guards=(('expected_revision', 'plan', 'digest', False),),
          door='shim', because='2 routes share (delete, spine-position@plan) and nothing in the payload chooses between them; reachable through its old name structure_change operation=spine op.kind=unset-spine until a payload key is declared',
          expiry='HELD, not retirable by this wave: 2 routes share (delete, spine-position@plan) and nothing in the payload chooses between them; reachable through its old name structure_change operation=spine op.kind=unset-spine until a payload key is declared. Retire when a payload key chooses between the routes sharing (delete, spine-position@plan) AND tools/writing_verbs/shim_retirement.py reports PARITY for `delete spine-position@plan` from evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_structure.change(project, payload, root,actor={'kind':'agent','turn_id':turn_id,'mode':mode,'dispatch_id':admitt",
          site='src/laplace/writing/operations.py:273'),
    Route(verb='delete', concept='storage@project', operation='storage_prune',
          selector=(),
          lift=(),
          expiry='retire `storage_prune` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `delete storage@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='writing_storage.prune(project, payload, root)',
          site='src/laplace/writing/operations.py:342'),
    Route(verb='move', concept='block@paragraph', operation='block_change',
          selector=(('operation', 'move'),),
          lift=(('operation', 'move'),),
          expiry='retire `block_change operation=move` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `move block@paragraph` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='manuscript_blocks.change(root, project, payload)',
          site='src/laplace/writing/operations.py:194'),
    Route(verb='move', concept='claim-position@section', operation='structure_change',
          selector=(('operation', 'plan'), ('op.kind', 'move-node')),
          lift=(('operation', 'plan'), ('op.kind', 'move-node')),
          guards=(('expected_revision', 'plan', 'digest', False),),
          expiry='retire `structure_change operation=plan op.kind=move-node` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `move claim-position@section` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_structure.change(project, payload, root,actor={'kind':'agent','turn_id':turn_id,'mode':mode,'dispatch_id':admitt",
          site='src/laplace/writing/operations.py:273'),
    Route(verb='move', concept='claim-position@section', operation='structure_change',
          selector=(('operation', 'plan'), ('op.kind', 'reorder-nodes')),
          lift=(('operation', 'plan'), ('op.kind', 'reorder-nodes')),
          guards=(('expected_revision', 'plan', 'digest', False),),
          door='shim', because='2 routes share (move, claim-position@section) and nothing in the payload chooses between them; reachable through its old name structure_change operation=plan op.kind=reorder-nodes until a payload key is declared',
          expiry='HELD, not retirable by this wave: 2 routes share (move, claim-position@section) and nothing in the payload chooses between them; reachable through its old name structure_change operation=plan op.kind=reorder-nodes until a payload key is declared. Retire when a payload key chooses between the routes sharing (move, claim-position@section) AND tools/writing_verbs/shim_retirement.py reports PARITY for `move claim-position@section` from evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_structure.change(project, payload, root,actor={'kind':'agent','turn_id':turn_id,'mode':mode,'dispatch_id':admitt",
          site='src/laplace/writing/operations.py:273'),
    Route(verb='move', concept='concept-node@claim', operation='concept_change',
          selector=(('operation', 'move_node'),),
          lift=(('operation', 'move_node'),),
          guards=(('base_revision', 'concept-network', 'digest', False), ('mutation_revision', 'concept-node', 'digest', True)),
          expiry='retire `concept_change operation=move_node` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `move concept-node@claim` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='concepts_surface.handle("/concepts/change", POST)',
          site='src/laplace/writing/operations.py:464'),
    Route(verb='move', concept='plan-section@section', operation='structure_change',
          selector=(('operation', 'plan'), ('op.kind', 'reorder-appendices')),
          lift=(('operation', 'plan'), ('op.kind', 'reorder-appendices')),
          guards=(('expected_revision', 'plan', 'digest', False),),
          expiry='retire `structure_change operation=plan op.kind=reorder-appendices` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `move plan-section@section` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_structure.change(project, payload, root,actor={'kind':'agent','turn_id':turn_id,'mode':mode,'dispatch_id':admitt",
          site='src/laplace/writing/operations.py:273'),
    Route(verb='move', concept='plan-section@section', operation='structure_change',
          selector=(('operation', 'plan'), ('op.kind', 'reorder-sections')),
          lift=(('operation', 'plan'), ('op.kind', 'reorder-sections')),
          guards=(('expected_revision', 'plan', 'digest', False),),
          door='shim', because='2 routes share (move, plan-section@section) and nothing in the payload chooses between them; reachable through its old name structure_change operation=plan op.kind=reorder-sections until a payload key is declared',
          expiry='HELD, not retirable by this wave: 2 routes share (move, plan-section@section) and nothing in the payload chooses between them; reachable through its old name structure_change operation=plan op.kind=reorder-sections until a payload key is declared. Retire when a payload key chooses between the routes sharing (move, plan-section@section) AND tools/writing_verbs/shim_retirement.py reports PARITY for `move plan-section@section` from evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_structure.change(project, payload, root,actor={'kind':'agent','turn_id':turn_id,'mode':mode,'dispatch_id':admitt",
          site='src/laplace/writing/operations.py:273'),
    Route(verb='move', concept='spine-position@plan', operation='structure_change',
          selector=(('operation', 'spine'),),
          lift=(('operation', 'spine'),),
          guards=(('expected_revision', 'plan', 'digest', False),),
          expiry='retire `structure_change operation=spine` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `move spine-position@plan` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_structure.change(project, payload, root,actor={'kind':'agent','turn_id':turn_id,'mode':mode,'dispatch_id':admitt",
          site='src/laplace/writing/operations.py:273'),
    Route(verb='move', concept='spine-position@plan', operation='structure_change',
          selector=(('operation', 'spine'), ('op.kind', 'reorder-spine')),
          lift=(('operation', 'spine'), ('op.kind', 'reorder-spine')),
          guards=(('expected_revision', 'plan', 'digest', False),),
          door='shim', because='2 routes share (move, spine-position@plan) and nothing in the payload chooses between them; reachable through its old name structure_change operation=spine op.kind=reorder-spine until a payload key is declared',
          expiry='HELD, not retirable by this wave: 2 routes share (move, spine-position@plan) and nothing in the payload chooses between them; reachable through its old name structure_change operation=spine op.kind=reorder-spine until a payload key is declared. Retire when a payload key chooses between the routes sharing (move, spine-position@plan) AND tools/writing_verbs/shim_retirement.py reports PARITY for `move spine-position@plan` from evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_structure.change(project, payload, root,actor={'kind':'agent','turn_id':turn_id,'mode':mode,'dispatch_id':admitt",
          site='src/laplace/writing/operations.py:273'),
    Route(verb='place', concept='claim-position@section', operation='structure_change',
          selector=(('operation', 'plan'), ('op.kind', 'add-node')),
          lift=(('operation', 'plan'), ('op.kind', 'add-node')),
          guards=(('expected_revision', 'plan', 'digest', False),),
          expiry='retire `structure_change operation=plan op.kind=add-node` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `place claim-position@section` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_structure.change(project, payload, root,actor={'kind':'agent','turn_id':turn_id,'mode':mode,'dispatch_id':admitt",
          site='src/laplace/writing/operations.py:273'),
    Route(verb='place', concept='claim-position@section', operation='structure_change',
          selector=(('operation', 'plan'), ('op.kind', 'set-nodes')),
          lift=(('operation', 'plan'), ('op.kind', 'set-nodes')),
          guards=(('expected_revision', 'plan', 'digest', False),),
          door='shim', because='2 routes share (place, claim-position@section) and nothing in the payload chooses between them; reachable through its old name structure_change operation=plan op.kind=set-nodes until a payload key is declared',
          expiry='HELD, not retirable by this wave: 2 routes share (place, claim-position@section) and nothing in the payload chooses between them; reachable through its old name structure_change operation=plan op.kind=set-nodes until a payload key is declared. Retire when a payload key chooses between the routes sharing (place, claim-position@section) AND tools/writing_verbs/shim_retirement.py reports PARITY for `place claim-position@section` from evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_structure.change(project, payload, root,actor={'kind':'agent','turn_id':turn_id,'mode':mode,'dispatch_id':admitt",
          site='src/laplace/writing/operations.py:273'),
    Route(verb='place', concept='spine-position@plan', operation='concept_change',
          selector=(('operation', 'set_spine'),),
          lift=(('operation', 'set_spine'),),
          guards=(('base_revision', 'concept-network', 'digest', False), ('mutation_revision', 'concept-node', 'digest', True)),
          expiry='retire `concept_change operation=set_spine` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `place spine-position@plan` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='concepts_surface.handle("/concepts/change", POST)',
          site='src/laplace/writing/operations.py:464'),
    Route(verb='place', concept='spine-position@plan', operation='structure_change',
          selector=(('operation', 'spine'), ('op.kind', 'set-narrative')),
          lift=(('operation', 'spine'), ('op.kind', 'set-narrative')),
          guards=(('expected_revision', 'plan', 'digest', False),),
          door='shim', because='2 routes share (place, spine-position@plan) and nothing in the payload chooses between them; reachable through its old name structure_change operation=spine op.kind=set-narrative until a payload key is declared',
          expiry='HELD, not retirable by this wave: 2 routes share (place, spine-position@plan) and nothing in the payload chooses between them; reachable through its old name structure_change operation=spine op.kind=set-narrative until a payload key is declared. Retire when a payload key chooses between the routes sharing (place, spine-position@plan) AND tools/writing_verbs/shim_retirement.py reports PARITY for `place spine-position@plan` from evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_structure.change(project, payload, root,actor={'kind':'agent','turn_id':turn_id,'mode':mode,'dispatch_id':admitt",
          site='src/laplace/writing/operations.py:273'),
    Route(verb='place', concept='visual@section', operation='visual_place',
          selector=(),
          lift=(),
          guards=(('base_revision', 'source-file', 'digest', True), ('expected_source_revision', 'selected-edition', 'digest', True)),
          expiry='retire `visual_place` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `place visual@section` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='visuals_surface.handle("/visuals/place", POST)',
          site='src/laplace/writing/operations.py:486'),
    Route(verb='read', concept='act-ledger@project', operation='author_history',
          selector=(('view', 'activity'),),
          lift=(),
          expiry='retire `author_history` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read act-ledger@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='author_history.source(project,payload,root)',
          site='src/laplace/writing/operations.py:375'),
    Route(verb='read', concept='act-ledger@project', operation='author_history',
          selector=(('view', 'record'),),
          lift=(),
          expiry='retire `author_history` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read act-ledger@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='author_history.source(project,payload,root)',
          site='src/laplace/writing/operations.py:375'),
    Route(verb='read', concept='act-ledger@project', operation='author_history',
          selector=(('view', 'source'),),
          lift=(),
          expiry='retire `author_history` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read act-ledger@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='author_history.source(project,payload,root)',
          site='src/laplace/writing/operations.py:375'),
    Route(verb='read', concept='act-ledger@project', operation='author_history',
          selector=(('view', 'telemetry'),),
          lift=(),
          expiry='retire `author_history` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read act-ledger@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='author_history.source(project,payload,root)',
          site='src/laplace/writing/operations.py:375'),
    Route(verb='read', concept='architecture-profile@project', operation='profile',
          selector=(('family', 'architecture'), ('scope', 'workspace'), ('view', 'content')),
          lift=(),
          expiry='retire `profile` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read architecture-profile@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='profiles.inspect(project, values, root, actor=actor)',
          site='src/laplace/writing/operations.py:428'),
    Route(verb='read', concept='architecture-profile@project', operation='profile',
          selector=(('family', 'architecture'), ('scope', 'workspace'), ('view', 'summary')),
          lift=(),
          expiry='retire `profile` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read architecture-profile@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='profiles.inspect(project, values, root, actor=actor)',
          site='src/laplace/writing/operations.py:428'),
    Route(verb='read', concept='artifact@project', operation='materials',
          selector=(),
          lift=(),
          expiry='retire `materials` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read artifact@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='artifacts.catalogue(root, project, material_payload)',
          site='src/laplace/writing/operations.py:371'),
    Route(verb='read', concept='artifact@project', operation='read_artifact',
          selector=(),
          lift=(),
          door='shim', because='5 routes share (read, artifact@project) and nothing in the payload chooses between them; reachable through its old name read_artifact until a payload key is declared',
          expiry='HELD, not retirable by this wave: 5 routes share (read, artifact@project) and nothing in the payload chooses between them; reachable through its old name read_artifact until a payload key is declared. Retire when a payload key chooses between the routes sharing (read, artifact@project) AND tools/writing_verbs/shim_retirement.py reports PARITY for `read artifact@project` from evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='artifacts.read(root, project, payload)',
          site='src/laplace/writing/operations.py:401'),
    Route(verb='read', concept='artifact@project', operation='research_handover',
          selector=(('action', 'inspect'),),
          lift=(),
          expiry='retire `research_handover` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read artifact@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_handover.object_request(root, owner_discovery.project_scope(project, 'native'),",
          site='src/laplace/writing/operations.py:411'),
    Route(verb='read', concept='artifact@project', operation='research_handover',
          selector=(('action', 'read'),),
          lift=(),
          expiry='retire `research_handover` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read artifact@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_handover.object_request(root, owner_discovery.project_scope(project, 'native'),",
          site='src/laplace/writing/operations.py:411'),
    Route(verb='read', concept='artifact@project', operation='research_handover',
          selector=(('action', 'request'),),
          lift=(),
          expiry='retire `research_handover` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read artifact@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_handover.object_request(root, owner_discovery.project_scope(project, 'native'),",
          site='src/laplace/writing/operations.py:411'),
    Route(verb='read', concept='build@project', operation='build_status',
          selector=(),
          lift=(),
          expiry='retire `build_status` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read build@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='tool_source.build(root, project, operation, payload)',
          site='src/laplace/writing/operations.py:207'),
    Route(verb='read', concept='change-history@project', operation='author_changes',
          selector=(),
          lift=(),
          expiry='retire `author_changes` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read change-history@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='manuscript_fragments.change_preview(project, payload, root)',
          site='src/laplace/writing/operations.py:398'),
    Route(verb='read', concept='concept-catalogue@plan', operation='logical_plan',
          selector=(('view', 'catalog'),),
          lift=(),
          expiry='retire `logical_plan` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read concept-catalogue@plan` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='concepts_surface.handle("/concepts/catalog" if payload.get("view")=="catalog" else "/concepts/plan/context", GET)',
          site='src/laplace/writing/operations.py:465'),
    Route(verb='read', concept='concept-network@claim', operation='concept_tree',
          selector=(),
          lift=(),
          expiry='retire `concept_tree` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read concept-network@claim` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='concepts_surface.handle("/concepts/tree", GET)',
          site='src/laplace/writing/operations.py:462'),
    Route(verb='read', concept='concept-network@plan', operation='logical_plan',
          selector=(('view', 'attention'),),
          lift=(),
          expiry='retire `logical_plan` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read concept-network@plan` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='concepts_surface.handle("/concepts/catalog" if payload.get("view")=="catalog" else "/concepts/plan/context", GET)',
          site='src/laplace/writing/operations.py:465'),
    Route(verb='read', concept='concept-node@claim', operation='concept',
          selector=(),
          lift=(),
          expiry='retire `concept` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read concept-node@claim` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='concepts_surface.handle("/concepts/source" if payload.get("source_index") is not None else "/concepts/context", GET)',
          site='src/laplace/writing/operations.py:460'),
    Route(verb='read', concept='concept-node@claim', operation='concept_history',
          selector=(),
          lift=(),
          door='shim', because='2 routes share (read, concept-node@claim) and nothing in the payload chooses between them; reachable through its old name concept_history until a payload key is declared',
          expiry='HELD, not retirable by this wave: 2 routes share (read, concept-node@claim) and nothing in the payload chooses between them; reachable through its old name concept_history until a payload key is declared. Retire when a payload key chooses between the routes sharing (read, concept-node@claim) AND tools/writing_verbs/shim_retirement.py reports PARITY for `read concept-node@claim` from evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='concepts_surface.handle("/concepts/history", GET)',
          site='src/laplace/writing/operations.py:463'),
    Route(verb='read', concept='contract@project', operation='app_settings',
          selector=(('scope', 'application'),),
          lift=(),
          expiry='retire `app_settings` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read contract@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='writing_projects.app_settings(root, **{key: value for key, value in fields.items() if key != "by"})',
          site='src/laplace/writing/operations.py:348'),
    Route(verb='read', concept='contract@project', operation='help',
          selector=(),
          lift=(),
          expiry='retire `help` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read contract@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='_help_renderer(root, project, mode, payload, turn_id=turn_id)',
          site='src/laplace/writing/operations.py:236'),
    Route(verb='read', concept='contract@project', operation='repository',
          selector=(('action', 'interface'),),
          lift=(),
          expiry='retire `repository` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read contract@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='writing_sources.execute(root, payload, interface=_interface_projection)',
          site='src/laplace/writing/operations.py:336'),
    Route(verb='read', concept='document-form@project', operation='document',
          selector=(),
          lift=(),
          expiry='retire `document` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read document-form@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="document_templates.inspect(project,{key:value for key,value in payload.items() if key!='project'},root,actor={'kind':'ag",
          site='src/laplace/writing/operations.py:209'),
    Route(verb='read', concept='guide-document@project', operation='project_guidance',
          selector=(),
          lift=(),
          expiry='retire `project_guidance` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read guide-document@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='project_protocol.read(project, payload, root)',
          site='src/laplace/writing/operations.py:444'),
    Route(verb='read', concept='material-reference@project', operation='material_references',
          selector=(),
          lift=(),
          expiry='retire `material_references` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read material-reference@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='writing_projects.material_references(project, root, **{key: value for key, value in fields.items() if key != "by"})',
          site='src/laplace/writing/operations.py:355'),
    Route(verb='read', concept='note@project', operation='author_history',
          selector=(('view', 'corrections'),),
          lift=(),
          expiry='retire `author_history` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read note@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='author_history.source(project,payload,root)',
          site='src/laplace/writing/operations.py:375'),
    Route(verb='read', concept='pipeline@project', operation='pipeline',
          selector=(('view', 'audit'),),
          lift=(),
          expiry='retire `pipeline` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read pipeline@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='{**result,"writing_stage":{"operation":"writing_stage",',
          site='src/laplace/writing/operations.py:254'),
    Route(verb='read', concept='pipeline@project', operation='pipeline',
          selector=(('view', 'summary'),),
          lift=(),
          expiry='retire `pipeline` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read pipeline@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='{**result,"writing_stage":{"operation":"writing_stage",',
          site='src/laplace/writing/operations.py:254'),
    Route(verb='read', concept='plan@plan', operation='structure',
          selector=(),
          lift=(),
          expiry='retire `structure` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read plan@plan` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='project_structure.read(project,scope,root)',
          site='src/laplace/writing/operations.py:269'),
    Route(verb='read', concept='profile-candidate@project', operation='profile',
          selector=(('view', 'candidate'),),
          lift=(),
          expiry='retire `profile` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read profile-candidate@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='profiles.inspect(project, values, root, actor=actor)',
          site='src/laplace/writing/operations.py:428'),
    Route(verb='read', concept='profile-candidate@project', operation='profile',
          selector=(('view', 'candidates'),),
          lift=(),
          expiry='retire `profile` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read profile-candidate@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='profiles.inspect(project, values, root, actor=actor)',
          site='src/laplace/writing/operations.py:428'),
    Route(verb='read', concept='project-metadata@project', operation='project_metadata',
          selector=(),
          lift=(),
          expiry='retire `project_metadata` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read project-metadata@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='writing_projects.metadata(project,root)',
          site='src/laplace/writing/operations.py:345'),
    Route(verb='read', concept='project@project', operation='project',
          selector=(),
          lift=(),
          expiry='retire `project` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read project@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="{**project_work_views.read(project, {key: value for key, value in payload.items() if key != 'project'}, root,",
          site='src/laplace/writing/operations.py:281'),
    Route(verb='read', concept='proof@claim', operation='proof_targets',
          selector=(),
          lift=(),
          expiry='retire `proof_targets` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read proof@claim` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='formal_surface.handle("/formal/targets", GET)',
          site='src/laplace/writing/operations.py:487'),
    Route(verb='read', concept='proof@project', operation='proofs',
          selector=(),
          lift=(),
          expiry='retire `proofs` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read proof@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='formal_surface.handle("/formal/state", GET)',
          site='src/laplace/writing/operations.py:488'),
    Route(verb='read', concept='reference-candidate@evidence', operation='literature_discover',
          selector=(),
          lift=(),
          expiry='retire `literature_discover` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read reference-candidate@evidence` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='references_surface.handle("/references/literature-discover", GET)',
          site='src/laplace/writing/operations.py:469'),
    Route(verb='read', concept='reference-text@evidence', operation='reference_text',
          selector=(),
          lift=(),
          expiry='retire `reference_text` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read reference-text@evidence` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="literature.observe_read(project,str(payload.get('key') or ''),root,",
          site='src/laplace/writing/operations.py:174'),
    Route(verb='read', concept='reference@claim', operation='literature_scope',
          selector=(),
          lift=(),
          expiry='retire `literature_scope` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read reference@claim` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='references_surface.handle("/references/literature-scope", GET)',
          site='src/laplace/writing/operations.py:473'),
    Route(verb='read', concept='reference@claim', operation='literature_uses',
          selector=(),
          lift=(),
          door='shim', because='2 routes share (read, reference@claim) and nothing in the payload chooses between them; reachable through its old name literature_uses until a payload key is declared',
          expiry='HELD, not retirable by this wave: 2 routes share (read, reference@claim) and nothing in the payload chooses between them; reachable through its old name literature_uses until a payload key is declared. Retire when a payload key chooses between the routes sharing (read, reference@claim) AND tools/writing_verbs/shim_retirement.py reports PARITY for `read reference@claim` from evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='references_surface.handle("/references/literature-uses", GET)',
          site='src/laplace/writing/operations.py:475'),
    Route(verb='read', concept='reference@evidence', operation='literature_lookup',
          selector=(),
          lift=(),
          expiry='retire `literature_lookup` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read reference@evidence` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='references_surface.handle("/references/literature-lookup", GET)',
          site='src/laplace/writing/operations.py:470'),
    Route(verb='read', concept='reference@evidence', operation='reference',
          selector=(),
          lift=(),
          door='shim', because='3 routes share (read, reference@evidence) and nothing in the payload chooses between them; reachable through its old name reference until a payload key is declared',
          expiry='HELD, not retirable by this wave: 3 routes share (read, reference@evidence) and nothing in the payload chooses between them; reachable through its old name reference until a payload key is declared. Retire when a payload key chooses between the routes sharing (read, reference@evidence) AND tools/writing_verbs/shim_retirement.py reports PARITY for `read reference@evidence` from evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='references_surface.handle("/references/item", GET)',
          site='src/laplace/writing/operations.py:476'),
    Route(verb='read', concept='reference@evidence', operation='reference_source',
          selector=(),
          lift=(),
          door='shim', because='3 routes share (read, reference@evidence) and nothing in the payload chooses between them; reachable through its old name reference_source until a payload key is declared',
          expiry='HELD, not retirable by this wave: 3 routes share (read, reference@evidence) and nothing in the payload chooses between them; reachable through its old name reference_source until a payload key is declared. Retire when a payload key chooses between the routes sharing (read, reference@evidence) AND tools/writing_verbs/shim_retirement.py reports PARITY for `read reference@evidence` from evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='references_surface.handle("/references/source", GET)',
          site='src/laplace/writing/operations.py:477'),
    Route(verb='read', concept='reference@project', operation='references',
          selector=(),
          lift=(),
          expiry='retire `references` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read reference@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='references_surface.handle("/references/search", GET)',
          site='src/laplace/writing/operations.py:468'),
    Route(verb='read', concept='reference@project', operation='references_attached',
          selector=(),
          lift=(),
          door='shim', because='2 routes share (read, reference@project) and nothing in the payload chooses between them; reachable through its old name references_attached until a payload key is declared',
          expiry='HELD, not retirable by this wave: 2 routes share (read, reference@project) and nothing in the payload chooses between them; reachable through its old name references_attached until a payload key is declared. Retire when a payload key chooses between the routes sharing (read, reference@project) AND tools/writing_verbs/shim_retirement.py reports PARITY for `read reference@project` from evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='references_surface.handle("/references/attached", GET)',
          site='src/laplace/writing/operations.py:479'),
    Route(verb='read', concept='repository-file@paragraph', operation='repository',
          selector=(('action', 'files'),),
          lift=(),
          expiry='retire `repository` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read repository-file@paragraph` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='writing_sources.execute(root, payload, interface=_interface_projection)',
          site='src/laplace/writing/operations.py:336'),
    Route(verb='read', concept='repository-file@paragraph', operation='repository',
          selector=(('action', 'read'),),
          lift=(),
          expiry='retire `repository` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read repository-file@paragraph` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='writing_sources.execute(root, payload, interface=_interface_projection)',
          site='src/laplace/writing/operations.py:336'),
    Route(verb='read', concept='repository-file@paragraph', operation='repository',
          selector=(('action', 'search'),),
          lift=(),
          expiry='retire `repository` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read repository-file@paragraph` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='writing_sources.execute(root, payload, interface=_interface_projection)',
          site='src/laplace/writing/operations.py:336'),
    Route(verb='read', concept='repository@project', operation='development_source',
          selector=(('action', 'read'),),
          lift=(),
          expiry='retire `development_source` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read repository@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='development_source.handle(root, project, payload, {"origin": "native", "turn_id": turn_id})',
          site='src/laplace/writing/operations.py:307'),
    Route(verb='read', concept='repository@project', operation='development_source',
          selector=(('action', 'status'),),
          lift=(),
          expiry='retire `development_source` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read repository@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='development_source.handle(root, project, payload, {"origin": "native", "turn_id": turn_id})',
          site='src/laplace/writing/operations.py:307'),
    Route(verb='read', concept='repository@project', operation='repository',
          selector=(('action', 'list'),),
          lift=(),
          expiry='retire `repository` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read repository@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='writing_sources.execute(root, payload, interface=_interface_projection)',
          site='src/laplace/writing/operations.py:336'),
    Route(verb='read', concept='repository@project', operation='repository',
          selector=(('action', 'view'),),
          lift=(),
          expiry='retire `repository` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read repository@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='writing_sources.execute(root, payload, interface=_interface_projection)',
          site='src/laplace/writing/operations.py:336'),
    Route(verb='read', concept='result@project', operation='research',
          selector=(('view', 'full'),),
          lift=(),
          expiry='retire `research` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read result@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="_owner_answer((200,research_records.inspect_request(project,payload['request'],root)))",
          site='src/laplace/writing/operations.py:516'),
    Route(verb='read', concept='result@project', operation='research',
          selector=(('view', 'result'),),
          lift=(),
          expiry='retire `research` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read result@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="_owner_answer((200,research_records.inspect_request(project,payload['request'],root)))",
          site='src/laplace/writing/operations.py:516'),
    Route(verb='read', concept='result@project', operation='research',
          selector=(('view', 'summary'),),
          lift=(),
          expiry='retire `research` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read result@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="_owner_answer((200,research_records.inspect_request(project,payload['request'],root)))",
          site='src/laplace/writing/operations.py:516'),
    Route(verb='read', concept='run@run', operation='run_status',
          selector=(),
          lift=(),
          expiry='retire `run_status` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read run@run` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="_owner_answer((200,research_runs.inspect_request(project,payload['request'],root)))",
          site='src/laplace/writing/operations.py:520'),
    Route(verb='read', concept='source-file@paragraph', operation='source',
          selector=(),
          lift=(),
          expiry='retire `source` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read source-file@paragraph` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='tool_source.read_source(root, project, payload, turn_id)',
          site='src/laplace/writing/operations.py:228'),
    Route(verb='read', concept='stage@project', operation='writing_stage',
          selector=(('view', 'full'),),
          lift=(),
          guards=(('known_revision', 'stage', 'digest', True),),
          expiry='retire `writing_stage` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read stage@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='writing_stages.inspect(project,',
          site='src/laplace/writing/operations.py:265'),
    Route(verb='read', concept='stage@project', operation='writing_stage',
          selector=(('view', 'guidance'),),
          lift=(),
          guards=(('known_revision', 'stage', 'digest', True),),
          expiry='retire `writing_stage` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read stage@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='writing_stages.inspect(project,',
          site='src/laplace/writing/operations.py:265'),
    Route(verb='read', concept='stage@project', operation='writing_stage',
          selector=(('view', 'materials'),),
          lift=(),
          guards=(('known_revision', 'stage', 'digest', True),),
          expiry='retire `writing_stage` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read stage@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='writing_stages.inspect(project,',
          site='src/laplace/writing/operations.py:265'),
    Route(verb='read', concept='stage@project', operation='writing_stage',
          selector=(('view', 'summary'),),
          lift=(),
          guards=(('known_revision', 'stage', 'digest', True),),
          expiry='retire `writing_stage` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read stage@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='writing_stages.inspect(project,',
          site='src/laplace/writing/operations.py:265'),
    Route(verb='read', concept='storage@project', operation='storage',
          selector=(),
          lift=(),
          expiry='retire `storage` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read storage@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='writing_storage.inspect(project, root)',
          site='src/laplace/writing/operations.py:339'),
    Route(verb='read', concept='style-calibration@project', operation='writing_style_calibration',
          selector=(),
          lift=(),
          expiry='retire `writing_style_calibration` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read style-calibration@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='writing_style.calibration(project, {k:v for k,v in payload.items() if k!="project"}, root)',
          site='src/laplace/writing/operations.py:435'),
    Route(verb='read', concept='style-profile@project', operation='profile',
          selector=(('family', 'voice'), ('scope', 'workspace'), ('view', 'content')),
          lift=(),
          expiry='retire `profile` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read style-profile@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='profiles.inspect(project, values, root, actor=actor)',
          site='src/laplace/writing/operations.py:428'),
    Route(verb='read', concept='style-profile@project', operation='profile',
          selector=(('family', 'voice'), ('scope', 'workspace'), ('view', 'summary')),
          lift=(),
          expiry='retire `profile` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read style-profile@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='profiles.inspect(project, values, root, actor=actor)',
          site='src/laplace/writing/operations.py:428'),
    Route(verb='read', concept='style-profile@project', operation='writing_style',
          selector=(('view', 'profile'),),
          lift=(),
          expiry='retire `writing_style` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read style-profile@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='writing_style.inspect(project, {k:v for k,v in payload.items() if k!="project"}, root)',
          site='src/laplace/writing/operations.py:432'),
    Route(verb='read', concept='style-provenance@project', operation='writing_style',
          selector=(('view', 'provenance'),),
          lift=(),
          expiry='retire `writing_style` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read style-provenance@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='writing_style.inspect(project, {k:v for k,v in payload.items() if k!="project"}, root)',
          site='src/laplace/writing/operations.py:432'),
    Route(verb='read', concept='style-state@project', operation='profile',
          selector=(('family', 'voice'), ('scope', 'project'), ('view', 'content')),
          lift=(),
          expiry='retire `profile` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read style-state@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='profiles.inspect(project, values, root, actor=actor)',
          site='src/laplace/writing/operations.py:428'),
    Route(verb='read', concept='style-state@project', operation='profile',
          selector=(('family', 'voice'), ('scope', 'project'), ('view', 'summary')),
          lift=(),
          expiry='retire `profile` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read style-state@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='profiles.inspect(project, values, root, actor=actor)',
          site='src/laplace/writing/operations.py:428'),
    Route(verb='read', concept='style-state@project', operation='writing_style',
          selector=(('view', 'summary'),),
          lift=(),
          expiry='retire `writing_style` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read style-state@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='writing_style.inspect(project, {k:v for k,v in payload.items() if k!="project"}, root)',
          site='src/laplace/writing/operations.py:432'),
    Route(verb='read', concept='task@evidence', operation='work_delivery',
          selector=(('action', 'status'),),
          lift=(),
          expiry='retire `work_delivery` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read task@evidence` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='work_delivery.handle(root, project, payload, {"origin": "native", "turn_id": turn_id})',
          site='src/laplace/writing/operations.py:312'),
    Route(verb='read', concept='task@project', operation='dispatch',
          selector=(),
          lift=(),
          expiry='retire `dispatch` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read task@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='tool_work.dispatch(root, project, mode, operation, payload, turn_id, observe_reads=observe_reads)',
          site='src/laplace/writing/operations.py:252'),
    Route(verb='read', concept='task@project', operation='dispatch_returns',
          selector=(),
          lift=(),
          door='shim', because='3 routes share (read, task@project) and nothing in the payload chooses between them; reachable through its old name dispatch_returns until a payload key is declared',
          expiry='HELD, not retirable by this wave: 3 routes share (read, task@project) and nothing in the payload chooses between them; reachable through its old name dispatch_returns until a payload key is declared. Retire when a payload key chooses between the routes sharing (read, task@project) AND tools/writing_verbs/shim_retirement.py reports PARITY for `read task@project` from evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='tool_work.dispatch(root, project, mode, operation, payload, turn_id, observe_reads=observe_reads)',
          site='src/laplace/writing/operations.py:252'),
    Route(verb='read', concept='task@project', operation='dispatch_status',
          selector=(),
          lift=(),
          door='shim', because='3 routes share (read, task@project) and nothing in the payload chooses between them; reachable through its old name dispatch_status until a payload key is declared',
          expiry='HELD, not retirable by this wave: 3 routes share (read, task@project) and nothing in the payload chooses between them; reachable through its old name dispatch_status until a payload key is declared. Retire when a payload key chooses between the routes sharing (read, task@project) AND tools/writing_verbs/shim_retirement.py reports PARITY for `read task@project` from evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='tool_work.dispatch(root, project, mode, operation, payload, turn_id, observe_reads=observe_reads)',
          site='src/laplace/writing/operations.py:252'),
    Route(verb='read', concept='turn@project', operation='conversation_history',
          selector=(),
          lift=(),
          guards=(('before', '', 'cursor', True),),
          expiry='retire `conversation_history` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read turn@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='tool_sessions.conversation_history(root, project, payload, turn_id)',
          site='src/laplace/writing/operations.py:242'),
    Route(verb='read', concept='turn@project', operation='session_settings',
          selector=(),
          lift=(),
          door='shim', because='2 routes share (read, turn@project) and nothing in the payload chooses between them; reachable through its old name session_settings until a payload key is declared',
          expiry='HELD, not retirable by this wave: 2 routes share (read, turn@project) and nothing in the payload chooses between them; reachable through its old name session_settings until a payload key is declared. Retire when a payload key chooses between the routes sharing (read, turn@project) AND tools/writing_verbs/shim_retirement.py reports PARITY for `read turn@project` from evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='tool_sessions.session_settings(root, project, payload, turn_id)',
          site='src/laplace/writing/operations.py:238'),
    Route(verb='read', concept='visual@project', operation='visuals',
          selector=(),
          lift=(),
          expiry='retire `visuals` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `read visual@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='visuals_surface.handle("/visuals/state", GET)',
          site='src/laplace/writing/operations.py:483'),
    Route(verb='record', concept='concept-node@claim', operation='research_object_change',
          selector=(('operation', 'clear-reconsideration'),),
          lift=(('operation', 'clear-reconsideration'),),
          expiry='retire `research_object_change operation=clear-reconsideration` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `record concept-node@claim` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="object_facets.change(root, owner_discovery.project_scope(project, 'native'), payload,",
          site='src/laplace/writing/operations.py:407'),
    Route(verb='record', concept='concept-node@claim', operation='research_object_change',
          selector=(('operation', 'mark-reconsideration'),),
          lift=(('operation', 'mark-reconsideration'),),
          door='shim', because='2 routes share (record, concept-node@claim) and nothing in the payload chooses between them; reachable through its old name research_object_change operation=mark-reconsideration until a payload key is declared',
          expiry='HELD, not retirable by this wave: 2 routes share (record, concept-node@claim) and nothing in the payload chooses between them; reachable through its old name research_object_change operation=mark-reconsideration until a payload key is declared. Retire when a payload key chooses between the routes sharing (record, concept-node@claim) AND tools/writing_verbs/shim_retirement.py reports PARITY for `record concept-node@claim` from evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="object_facets.change(root, owner_discovery.project_scope(project, 'native'), payload,",
          site='src/laplace/writing/operations.py:407'),
    Route(verb='record', concept='result@run', operation='research_record',
          selector=(),
          lift=(),
          guards=(('expected_revision', 'result', 'digest', True),),
          expiry='retire `research_record` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `record result@run` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='_owner_answer(research_records.record(named, payload, root=root))',
          site='src/laplace/writing/operations.py:526'),
    Route(verb='record', concept='task@evidence', operation='work_delivery',
          selector=(('action', 'submit'),),
          lift=(),
          expiry='retire `work_delivery` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `record task@evidence` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='work_delivery.handle(root, project, payload, {"origin": "native", "turn_id": turn_id})',
          site='src/laplace/writing/operations.py:312'),
    Route(verb='record', concept='task@evidence', operation='work_review',
          selector=(),
          lift=(),
          expiry='retire `work_review` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `record task@evidence` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='project_work_review.record(project, payload, root, door={"origin": "native", "turn_id": turn_id}, mode=mode)',
          site='src/laplace/writing/operations.py:303'),
    Route(verb='run', concept='build@project', operation='build',
          selector=(),
          lift=(),
          expiry='retire `build` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `run build@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='tool_source.build(root, project, operation, payload)',
          site='src/laplace/writing/operations.py:207'),
    Route(verb='run', concept='experiment@run', operation='experiment_run',
          selector=(('mode', 'full'),),
          lift=(),
          expiry='retire `experiment_run` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `run experiment@run` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='_owner_answer(research_runs.launch(named, payload, root=root))',
          site='src/laplace/writing/operations.py:530'),
    Route(verb='run', concept='experiment@run', operation='experiment_run',
          selector=(('mode', 'smoke'),),
          lift=(),
          expiry='retire `experiment_run` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `run experiment@run` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='_owner_answer(research_runs.launch(named, payload, root=root))',
          site='src/laplace/writing/operations.py:530'),
    Route(verb='run', concept='export@project', operation='export_pdf',
          selector=(('mode', 'selected-source'),),
          lift=(),
          expiry='retire `export_pdf` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `run export@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='document_style.export_pdf(project,root,mode=str(payload.get("mode") or "selected-source"),candidate_ref=payload.get("can',
          site='src/laplace/writing/operations.py:222'),
    Route(verb='run', concept='export@project', operation='export_pdf',
          selector=(('mode', 'style-preview'),),
          lift=(),
          expiry='retire `export_pdf` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `run export@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='document_style.export_pdf(project,root,mode=str(payload.get("mode") or "selected-source"),candidate_ref=payload.get("can',
          site='src/laplace/writing/operations.py:222'),
    Route(verb='run', concept='plan@plan', operation='structure_change',
          selector=(('operation', 'reconcile'),),
          lift=(('operation', 'reconcile'),),
          guards=(('expected_revision', 'plan', 'digest', False),),
          expiry='retire `structure_change operation=reconcile` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `run plan@plan` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner="project_structure.change(project, payload, root,actor={'kind':'agent','turn_id':turn_id,'mode':mode,'dispatch_id':admitt",
          site='src/laplace/writing/operations.py:273'),
    Route(verb='run', concept='proof@claim', operation='proof_check',
          selector=(),
          lift=(),
          guards=(('concept_revision', 'concept-network', 'digest', True), ('result_revision', 'result', 'digest', True), ('source_revision', 'producer', 'digest', True)),
          expiry='retire `proof_check` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `run proof@claim` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='formal_surface.handle("/formal/check", POST)',
          site='src/laplace/writing/operations.py:489'),
    Route(verb='run', concept='reference-text@evidence', operation='reference_fetch',
          selector=(),
          lift=(),
          expiry='retire `reference_fetch` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `run reference-text@evidence` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='references_surface.handle("/references/fetch", POST)',
          site='src/laplace/writing/operations.py:474'),
    Route(verb='run', concept='reference@project', operation='reference_refresh',
          selector=(),
          lift=(),
          expiry='retire `reference_refresh` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `run reference@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='references_surface.handle("/references/refresh", POST)',
          site='src/laplace/writing/operations.py:482'),
    Route(verb='run', concept='repository@project', operation='development_source',
          selector=(('action', 'check'),),
          lift=(),
          expiry='retire `development_source` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `run repository@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='development_source.handle(root, project, payload, {"origin": "native", "turn_id": turn_id})',
          site='src/laplace/writing/operations.py:307'),
    Route(verb='run', concept='task@evidence', operation='work_delivery',
          selector=(('action', 'recover'),),
          lift=(),
          expiry='retire `work_delivery` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `run task@evidence` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='work_delivery.handle(root, project, payload, {"origin": "native", "turn_id": turn_id})',
          site='src/laplace/writing/operations.py:312'),
    Route(verb='run', concept='task@project', operation='dispatch_continue',
          selector=(),
          lift=(),
          when=(('packet', ''),),
          expiry='retire `dispatch_continue` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `run task@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='tool_work.dispatch(root, project, mode, operation, payload, turn_id, observe_reads=observe_reads)',
          site='src/laplace/writing/operations.py:252'),
    Route(verb='run', concept='task@project', operation='dispatch_launch',
          selector=(),
          lift=(),
          expiry='retire `dispatch_launch` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `run task@project` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='tool_work.dispatch(root, project, mode, operation, payload, turn_id, observe_reads=observe_reads)',
          site='src/laplace/writing/operations.py:252'),
    Route(verb='run', concept='visual@run', operation='visual_render',
          selector=(),
          lift=(),
          expiry='retire `visual_render` when tools/writing_verbs/shim_retirement.py reports RETIRABLE for `run visual@run` -- i.e. when a recorded row of that route replayed through writing_tools.request() with byte PARITY against the old name in evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/parity-verb-door/rows.jsonl; review 2026-11-01',
          owner='visuals_surface.handle("/visuals/render", POST)',
          site='src/laplace/writing/operations.py:485'),
)
HTTP_ROUTES: tuple[Route, ...] = (
    Route(verb='change', concept='project@project', operation='http-door',
          door='http', route='*', method='POST', source_operation='', because='the door-wide header rule: every mutating route under the eight writing prefixes',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='scanner.writing_prefix_guard(path)',
          site='src/laplace/web/scanner.py:2047'),
    Route(verb='change', concept='prose@paragraph', operation='authoring/apply',
          door='http', route='/authoring/apply', method='POST', source_operation='', because='',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='source_application.apply_proposal(root, payload)',
          site='src/laplace/web/authoring_http.py:172'),
    Route(verb='change', concept='block@paragraph', operation='authoring/block-change',
          door='http', route='/authoring/block-change', method='POST', source_operation='', because='',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='manuscript_blocks.change(root, project, payload)',
          site='src/laplace/web/authoring_http.py:137'),
    Route(verb='read', concept='build@project', operation='authoring/build-status',
          door='http', route='/authoring/build', method='GET', source_operation='build_status', because='present and ok do not mean current; fresh and a readable returned PDF establish the current build',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='projection_viewer.recompile_status(source root repo_root)',
          site='src/laplace/web/authoring_http.py:99'),
    Route(verb='run', concept='build@project', operation='authoring/build-start',
          door='http', route='/authoring/build', method='POST', source_operation='build', because='a successful response queues or starts work; terminal build state is read from the GET',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='projection_viewer.recompile(source root project author repo_root)',
          site='src/laplace/web/authoring_http.py:99'),
    Route(verb='create', concept='note@paragraph', operation='authoring/correction-request-save',
          door='http', route='/authoring/correction', method='POST', source_operation='', because='Source-bound same-request passage origin; no new native route or Work authority',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='pipeline.authoring source-bound comment owner',
          site='src/laplace/web/authoring_http.py:140'),
    Route(verb='read', concept='note@paragraph', operation='authoring/correction-origin',
          door='http', route='/authoring/correction-origin', method='GET', source_operation='', because='Source-bound same-request passage origin; no new native route or Work authority',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='pipeline.authoring source-bound comment owner',
          site='src/laplace/web/authoring_http.py:160'),
    Route(verb='read', concept='source-file@paragraph', operation='authoring/correction-prepare',
          door='http', route='/authoring/correction-prepare', method='POST', source_operation='', because='Source-bound same-request passage origin; no new native route or Work authority',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='pipeline.authoring source-bound comment owner',
          site='src/laplace/web/authoring_http.py:153'),
    Route(verb='read', concept='note@paragraph', operation='authoring/correction-request',
          door='http', route='/authoring/correction-request', method='GET', source_operation='', because='Source-bound same-request passage origin; no new native route or Work authority',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='pipeline.authoring source-bound comment owner',
          site='src/laplace/web/authoring_http.py:157'),
    Route(verb='change', concept='note@paragraph', operation='authoring/correction-settle',
          door='http', route='/authoring/correction-settle', method='POST', source_operation='', because='Explicit original request settlement; never deletes an existing comment or starts a review',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='pipeline.authoring same-request origin settlement',
          site='src/laplace/web/authoring_http.py:155'),
    Route(verb='read', concept='document-form@project', operation='authoring/document',
          door='http', route='/authoring/document', method='GET', source_operation='document', because='bounded document and exact source/dependency handles from native document owner',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='writing.document.current(project, root)',
          site='src/laplace/web/authoring_http.py:79'),
    Route(verb='read', concept='turn@project', operation='authoring/events',
          door='http', route='/authoring/events', method='GET', source_operation='conversation_history', because='the live projection of one durable turn; completion is not visible delivery until the saved session read renders it',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='authoring_surface.stream(handler query)',
          site='src/laplace/web/scanner.py:1329'),
    Route(verb='read', concept='project@project', operation='authoring/health',
          door='http', route='/authoring/health', method='GET', source_operation='', because='process health; view=traffic is the bounded process traffic ledger, loopback only; no native door',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='scanner._health_view + authoring_surface.handle(path) / writing.traffic.snapshot',
          site='src/laplace/web/scanner.py:1293'),
    Route(verb='read', concept='contract@project', operation='authoring/help',
          door='http', route='/authoring/help', method='GET', source_operation='help', because='Current contract inspection only; no provider read or retry',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='authoring_http.inspect_help(root query)',
          site='src/laplace/web/authoring_http.py:103'),
    Route(verb='read', concept='act-ledger@project', operation='authoring/history',
          door='http', route='/authoring/history', method='GET', source_operation='author_history', because='Same correction owner read fields/cut as native author_history',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='pipeline.authoring.history',
          site='src/laplace/web/authoring_http.py:77'),
    Route(verb='read', concept='note@project', operation='authoring/history',
          door='http', route='/authoring/history', method='GET', source_operation='author_history', because='Same correction owner read fields/cut as native author_history',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='pipeline.authoring.history',
          site='src/laplace/web/authoring_http.py:77'),
    Route(verb='change', concept='turn@project', operation='authoring/interrupt',
          door='http', route='/authoring/interrupt', method='POST', source_operation='', because='interrupt requests cancellation; terminal interrupted or failed state arrives through the turn result',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='writing turn provider interrupt',
          site='src/laplace/web/authoring_http.py:170'),
    Route(verb='delete', concept='proposal@paragraph', operation='authoring/proposal-decision',
          door='http', route='/authoring/proposal-decision', method='POST', source_operation='', because="deciding a suggestion RETIRES it: accept and reject both end the proposal's life as a pending home, which is `delete` in the nine (GRAMMAR.md section 3's note_status argument, where status=resolved|dismissed is delete note@claim)",
          when=(('decision', ''),),
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='manuscript_proposals.decide(root, project, payload)',
          site='src/laplace/web/authoring_http.py:96'),
    Route(verb='read', concept='proposal@paragraph', operation='authoring/proposal-preview',
          door='http', route='/authoring/proposal-preview', method='GET', source_operation='', because='',
          when=(('id', ''),),
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='manuscript_proposals.preview(root project turn_id)',
          site='src/laplace/web/authoring_http.py:89'),
    Route(verb='read', concept='proposal@paragraph', operation='authoring/proposals',
          door='http', route='/authoring/proposals', method='GET', source_operation='', because='',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='session_reads.pending_proposals(root project)',
          site='src/laplace/web/authoring_http.py:87'),
    Route(verb='read', concept='project@project', operation='authoring/providers',
          door='http', route='/authoring/providers', method='GET', source_operation='', because='',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='authoring_surface.handle(path)',
          site='src/laplace/web/authoring_http.py:73'),
    Route(verb='read', concept='project@project', operation='authoring/reader',
          door='http', route='/authoring/reader', method='GET', source_operation='project', because='selected-input read/preparation through project view; never inference',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='sealed_reader.request(root, values)',
          site='src/laplace/web/authoring_http.py:107'),
    Route(verb='read', concept='project@project', operation='authoring/reader',
          door='http', route='/authoring/reader', method='POST', source_operation='project', because='selected-input read/preparation through project view; never inference',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='sealed_reader.request(root, values)',
          site='src/laplace/web/authoring_http.py:107'),
    Route(verb='change', concept='plan-section@section', operation='authoring/section-change',
          door='http', route='/authoring/section-change', method='POST', source_operation='', because='',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='manuscript_structure.change(project, payload, root)',
          site='src/laplace/web/authoring_http.py:134'),
    Route(verb='read', concept='turn@project', operation='authoring/session',
          door='http', route='/authoring/session', method='GET', source_operation='conversation_history', because='',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='session_reads.session_state(root id before view limit)',
          site='src/laplace/web/authoring_http.py:101'),
    Route(verb='read', concept='turn@project', operation='authoring/session-settings-read',
          door='http', route='/authoring/session-settings', method='GET', source_operation='', because='Same guarded settings owner; pure query reads and exact change/withdraw custody, legacy flat changes retained',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='writing.session_settings.request',
          site='src/laplace/web/authoring_http.py:121'),
    Route(verb='change', concept='turn@project', operation='authoring/session-settings-change',
          door='http', route='/authoring/session-settings', method='POST', source_operation='', because='Same guarded settings owner; pure query reads and exact change/withdraw custody, legacy flat changes retained',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='writing.session_settings.request',
          site='src/laplace/web/authoring_http.py:121'),
    Route(verb='read', concept='turn@project', operation='authoring/session-turn',
          door='http', route='/authoring/session-turn', method='GET', source_operation='conversation_history', because='Selected message uses exact session and turn identity plus a pinned request or displayed-reply page; it does not fold the rich turn',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='session_reads.public_message(root payload) for view=message; session_turn_detail for other views',
          site='src/laplace/web/authoring_http.py:105'),
    Route(verb='read', concept='project@project', operation='authoring/state-summary',
          door='http', route='/authoring/state', method='GET', source_operation='project', because='Framing and session metadata only; no unrelated historical source bodies',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='pipeline.authoring.summary / sessions',
          site='src/laplace/web/authoring_http.py:75'),
    Route(verb='change', concept='turn@project', operation='authoring/steer',
          door='http', route='/authoring/steer', method='POST', source_operation='', because='steering adds scoped input to the active turn and does not start or replay one',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='turn_control.steer_turn(root payload)',
          site='src/laplace/web/authoring_http.py:170'),
    Route(verb='read', concept='change-history@project', operation='authoring/structural-undo',
          door='http', route='/authoring/structural-undo', method='GET', source_operation='', because="the read half of the editor's Undo: it serves the exact inverse of one banked structural change and writes nothing",
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='author_history.structural_undo',
          site='src/laplace/web/authoring_http.py:94'),
    Route(verb='run', concept='turn@project', operation='authoring/turn',
          door='http', route='/authoring/turn', method='POST', source_operation='', because='',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='turn_admission.start_turn(root, payload) (the lifecycle entry)',
          site='src/laplace/writing/turn_admission.py:796'),
    Route(verb='read', concept='technical-friction@project', operation='corpus/friction-read',
          door='http', route='/corpus/friction', method='GET', source_operation='', because='Technical reports are open observations in existing friction channel; no guidance, node membership or work completion authority',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='technical_friction.read',
          site='src/laplace/web/scanner.py:1814'),
    Route(verb='create', concept='technical-friction@project', operation='corpus/friction-create',
          door='http', route='/corpus/friction', method='POST', source_operation='', because='Technical reports are open observations in existing friction channel; no guidance, node membership or work completion authority',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='corpus_ingest.friction_add',
          site='src/laplace/web/scanner.py:2329'),
    Route(verb='record', concept='technical-friction@project', operation='corpus/friction-report',
          door='http', route='/corpus/friction', method='POST', source_operation='', because='Technical reports are open observations in existing friction channel; no guidance, node membership or work completion authority',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='corpus_ingest.friction_add',
          site='src/laplace/web/scanner.py:2329'),
    Route(verb='read', concept='artifact@project', operation='projection/pdf',
          door='http', route='/projection/pdf', method='GET', source_operation='read_artifact', because='a readable PDF is the artifact delivery; build status alone is not',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='projection_viewer serves the resolved PDF bytes',
          site='src/laplace/manuscript/projection_viewer.py:2308'),
    Route(verb='read', concept='source-file@paragraph', operation='projection/source',
          door='http', route='/projection/tex', method='GET', source_operation='', because='Exact registered-source query/receipt contract; historical reads use author_history',
          when=(('view', 'source'), ('corpus', ''), ('file', '')),
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='projection_viewer._source_observation(path)',
          site='src/laplace/manuscript/projection_viewer.py:2196'),
    Route(verb='change', concept='source-file@paragraph', operation='projection/source-save',
          door='http', route='/projection/tex', method='POST', source_operation='', because='Exact registered-source query/receipt contract; historical reads use author_history',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='projection_viewer._save_source(path, query, body)',
          site='src/laplace/manuscript/projection_viewer.py:2196'),
    Route(verb='read', concept='contract@project', operation='projects/app-settings',
          door='http', route='/projects/app-settings', method='GET', source_operation='app_settings', because='Existing global owners with no dummy project or new model-policy store',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='writing_projects.app_settings / writing_style.update_global_profile',
          site='src/laplace/projects/library.py:1096'),
    Route(verb='change', concept='style-profile@project', operation='projects/app-voice-change',
          door='http', route='/projects/app-settings', method='POST', source_operation='', because='Existing global owners with no dummy project or new model-policy store',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='writing_projects.app_settings / writing_style.update_global_profile',
          site='src/laplace/projects/library.py:1096'),
    Route(verb='create', concept='project@project', operation='projects/create',
          door='http', route='/projects/create', method='POST', source_operation='', because='',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='writing_projects.handle(path)',
          site='src/laplace/projects/library.py:1147'),
    Route(verb='read', concept='material-reference@project', operation='projects/material-intake',
          door='http', route='/projects/material-intake', method='GET', source_operation='material_references', because='raw byte custody and exact scoped read/recovery',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='artifact and Material intake owner',
          site='src/laplace/projects/material_intake.py:377'),
    Route(verb='create', concept='material-reference@project', operation='projects/material-intake-link',
          door='http', route='/projects/material-intake/link', method='POST', source_operation='', because='raw byte custody and exact scoped read/recovery',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='artifact and Material intake owner',
          site='src/laplace/projects/material_intake.py:377'),
    Route(verb='read', concept='artifact@project', operation='projects/material-intake-original',
          door='http', route='/projects/material-intake/original', method='GET', source_operation='', because='raw byte custody and exact scoped read/recovery',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='artifact and Material intake owner',
          site='src/laplace/projects/material_intake.py:377'),
    Route(verb='read', concept='artifact@project', operation='projects/material-intake-read',
          door='http', route='/projects/material-intake/read', method='GET', source_operation='read_artifact', because='raw byte custody and exact scoped read/recovery',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='artifact and Material intake owner',
          site='src/laplace/projects/material_intake.py:377'),
    Route(verb='create', concept='artifact@project', operation='projects/material-intake-upload',
          door='http', route='/projects/material-intake/upload', method='POST', source_operation='', because='raw byte custody and exact scoped read/recovery',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='artifact and Material intake owner',
          site='src/laplace/projects/material_intake.py:377'),
    Route(verb='read', concept='material-reference@project', operation='projects/material-references',
          door='http', route='/projects/material-references', method='GET', source_operation='material_references', because='Registry membership owner and active-consumer readthroughbinding',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='writing_projects.material_references / change_material_reference',
          site='src/laplace/projects/library.py:1114'),
    Route(verb='create', concept='material-reference@project', operation='projects/material-reference-change',
          door='http', route='/projects/material-references', method='POST', source_operation='material_reference_change', because='Registry membership owner and active-consumer readthroughbinding',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='writing_projects.material_references / change_material_reference',
          site='src/laplace/projects/library.py:1114'),
    Route(verb='change', concept='material-reference@project', operation='projects/material-reference-change',
          door='http', route='/projects/material-references', method='POST', source_operation='material_reference_change', because='Registry membership owner and active-consumer readthroughbinding',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='writing_projects.material_references / change_material_reference',
          site='src/laplace/projects/library.py:1114'),
    Route(verb='delete', concept='material-reference@project', operation='projects/material-reference-change',
          door='http', route='/projects/material-references', method='POST', source_operation='material_reference_change', because='Registry membership owner and active-consumer readthroughbinding',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='writing_projects.material_references / change_material_reference',
          site='src/laplace/projects/library.py:1114'),
    Route(verb='run', concept='reference-text@evidence', operation='references/reference_fetch',
          door='http', route='/references/fetch', method='POST', source_operation='reference_fetch', because='same native/HTTP literature schema and owner',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='literature existing owner',
          site='src/laplace/research/literature.py:914'),
    Route(verb='bind', concept='reference@evidence', operation='references/literature_bind',
          door='http', route='/references/literature-bind', method='POST', source_operation='literature_bind', because='same native/HTTP literature schema and owner',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='literature existing owner',
          site='src/laplace/research/literature.py:936'),
    Route(verb='create', concept='reference@evidence', operation='references/literature_import',
          door='http', route='/references/literature-import', method='POST', source_operation='literature_import', because='Closed retained original or legacy DOI/manual metadata through the same import owner',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='literature existing owner',
          site='src/laplace/research/literature.py:936'),
    Route(verb='read', concept='reference@claim', operation='references/literature_scope',
          door='http', route='/references/literature-scope', method='GET', source_operation='literature_scope', because='same native/HTTP literature schema and owner',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='literature existing owner',
          site='src/laplace/research/literature.py:910'),
    Route(verb='read', concept='reference@evidence', operation='references/reference_source',
          door='http', route='/references/source', method='GET', source_operation='reference_source', because='same native/HTTP literature schema and owner',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='literature existing owner',
          site='src/laplace/research/literature.py:923'),
    Route(verb='read', concept='reference-text@evidence', operation='references/reference_text',
          door='http', route='/references/text', method='GET', source_operation='reference_text', because='same native/HTTP literature schema and owner',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='literature existing owner',
          site='src/laplace/research/literature.py:919'),
    Route(verb='record', concept='result@run', operation='research/record',
          door='http', route='/research/record', method='POST', source_operation='research_record', because='Explicit guarded canonical result recording and request replay',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='research_records.record',
          site='src/laplace/web/research_surface.py:82'),
    Route(verb='read', concept='result@project', operation='research/record-request',
          door='http', route='/research/record/request', method='GET', source_operation='research', because='Exact canonical result request outcome without Save',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='research_records.inspect_request',
          site='src/laplace/web/research_surface.py:143'),
    Route(verb='read', concept='run@run', operation='research/run-request',
          door='http', route='/research/run/request', method='GET', source_operation='run_status', because='Exact original request read without launch or replacement',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='research_runs.inspect_request',
          site='src/laplace/web/research_surface.py:133'),
    Route(verb='change', concept='prose@paragraph', operation='review/adjudicate',
          door='http', route='/review/adjudicate', method='POST', source_operation='', because='',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='review_http.handle(path)',
          site='src/laplace/web/review_http.py:212'),
    Route(verb='create', concept='note@paragraph', operation='review/adjudicate-comment',
          door='http', route='/review/adjudicate', method='POST', source_operation='', because='comment maps to create note at three altitudes through one owner branch',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='review_surface.adjudicate(md, project, payload)',
          site='src/laplace/manuscript/review_surface.py:2459'),
    Route(verb='create', concept='note@section', operation='review/adjudicate-comment',
          door='http', route='/review/adjudicate', method='POST', source_operation='', because='',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='review_surface.adjudicate(md, project, payload)',
          site='src/laplace/manuscript/review_surface.py:2459'),
    Route(verb='create', concept='note@chapter', operation='review/adjudicate-comment',
          door='http', route='/review/adjudicate', method='POST', source_operation='', because='',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='review_surface.adjudicate(md, project, payload)',
          site='src/laplace/manuscript/review_surface.py:2459'),
    Route(verb='read', concept='document-form@project', operation='walk/doc',
          door='http', route='/walk/doc', method='GET', source_operation='document', because='the rendered manuscript projection; source bytes and owner identities remain canonical',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='walk.doc(corpus identities)',
          site='src/laplace/manuscript/walk.py:3066'),
    Route(verb='read', concept='task@evidence', operation='work/delivery-read',
          door='http', route='/work/delivery', method='GET', source_operation='', because='Owner-issued project + JSON request inspection including review-setup and renew-request; adapter refuses effects',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='work_delivery.handle(root project request human)',
          site='src/laplace/web/project_work_surface.py:188'),
    Route(verb='read', concept='project@project', operation='work/object-discovery',
          door='http', route='/work/discovery', method='GET', source_operation='', because='Same emitted owner contract; local HTTP scope is supplied by the trusted adapter, not a payload.',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='work.owner_discovery.request',
          site='src/laplace/web/project_work_surface.py:27'),
    Route(verb='read', concept='artifact@project', operation='work/materials',
          door='http', route='/work/materials', method='GET', source_operation='materials', because='latest recorded artifact receipt per scoped path; bounded pagination; currentness deferred to exact read',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='project_work_surface.materials',
          site='src/laplace/web/project_work_surface.py:79'),
    Route(verb='create', concept='concept-node@claim', operation='work/object-change',
          door='http', route='/work/object-change', method='POST', source_operation='research_object_change', because='Same emitted owner contract; local HTTP scope is supplied by the trusted adapter, not a payload.',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='work.object_facets.change',
          site='src/laplace/web/project_work_surface.py:40'),
    Route(verb='change', concept='concept-node@claim', operation='work/object-change',
          door='http', route='/work/object-change', method='POST', source_operation='research_object_change', because='Same emitted owner contract; local HTTP scope is supplied by the trusted adapter, not a payload.',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='work.object_facets.change',
          site='src/laplace/web/project_work_surface.py:40'),
    Route(verb='bind', concept='concept-node@claim', operation='work/object-change',
          door='http', route='/work/object-change', method='POST', source_operation='research_object_change', because='Same emitted owner contract; local HTTP scope is supplied by the trusted adapter, not a payload.',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='work.object_facets.change',
          site='src/laplace/web/project_work_surface.py:40'),
    Route(verb='record', concept='concept-node@claim', operation='work/object-change',
          door='http', route='/work/object-change', method='POST', source_operation='research_object_change', because='Same emitted owner contract; local HTTP scope is supplied by the trusted adapter, not a payload.',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='work.object_facets.change',
          site='src/laplace/web/project_work_surface.py:40'),
    Route(verb='create', concept='artifact@project', operation='work/object-handover',
          door='http', route='/work/object-handover', method='POST', source_operation='research_handover', because='Same emitted owner contract; local HTTP scope is supplied by the trusted adapter, not a payload.',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='projects.project_handover.object_request',
          site='src/laplace/web/project_work_surface.py:43'),
    Route(verb='read', concept='artifact@project', operation='work/object-handover',
          door='http', route='/work/object-handover', method='POST', source_operation='research_handover', because='Same emitted owner contract; local HTTP scope is supplied by the trusted adapter, not a payload.',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='projects.project_handover.object_request',
          site='src/laplace/web/project_work_surface.py:43'),
    Route(verb='change', concept='artifact@project', operation='work/object-handover',
          door='http', route='/work/object-handover', method='POST', source_operation='research_handover', because='Same emitted owner contract; local HTTP scope is supplied by the trusted adapter, not a payload.',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='projects.project_handover.object_request',
          site='src/laplace/web/project_work_surface.py:43'),
    Route(verb='read', concept='architecture-profile@project', operation='work/profiles',
          door='http', route='/work/profiles', method='GET', source_operation='profile', because='Typed scoped profile inspection and immutable candidate handles; projectless workspace metadata only',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='profiles.inspect(project values root)',
          site='src/laplace/web/project_work_surface.py:130'),
    Route(verb='read', concept='style-profile@project', operation='work/profiles',
          door='http', route='/work/profiles', method='GET', source_operation='profile', because='Typed scoped profile inspection and immutable candidate handles; projectless workspace metadata only',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='profiles.inspect(project values root)',
          site='src/laplace/web/project_work_surface.py:130'),
    Route(verb='read', concept='style-state@project', operation='work/profiles',
          door='http', route='/work/profiles', method='GET', source_operation='profile', because='Typed scoped profile inspection and immutable candidate handles; projectless workspace metadata only',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='profiles.inspect(project values root)',
          site='src/laplace/web/project_work_surface.py:130'),
    Route(verb='read', concept='profile-candidate@project', operation='work/profiles',
          door='http', route='/work/profiles', method='GET', source_operation='profile', because='Typed scoped profile inspection and immutable candidate handles; projectless workspace metadata only',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='profiles.inspect(project values root)',
          site='src/laplace/web/project_work_surface.py:130'),
    Route(verb='change', concept='architecture-profile@project', operation='work/profiles-change',
          door='http', route='/work/profiles/change', method='POST', source_operation='profile_change', because='Same guarded preference authority and separate explicit human confirmation',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='profiles.change(project payload root)',
          site='src/laplace/web/project_work_surface.py:137'),
    Route(verb='change', concept='style-profile@project', operation='work/profiles-change',
          door='http', route='/work/profiles/change', method='POST', source_operation='profile_change', because='Same guarded preference authority and separate explicit human confirmation',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='profiles.change(project payload root)',
          site='src/laplace/web/project_work_surface.py:137'),
    Route(verb='change', concept='style-state@project', operation='work/profiles-change',
          door='http', route='/work/profiles/change', method='POST', source_operation='profile_change', because='Same guarded preference authority and separate explicit human confirmation',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='profiles.change(project payload root)',
          site='src/laplace/web/project_work_surface.py:137'),
    Route(verb='change', concept='profile-candidate@project', operation='work/profiles-change',
          door='http', route='/work/profiles/change', method='POST', source_operation='profile_change', because='Same guarded preference authority and separate explicit human confirmation',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='profiles.change(project payload root)',
          site='src/laplace/web/project_work_surface.py:137'),
    Route(verb='read', concept='project@project', operation='work/session-preferences-read',
          door='http', route='/work/session-preferences', method='GET', source_operation='', because='Same guarded settings owner; pure query reads and exact change/withdraw custody, legacy flat changes retained',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='writing.session_settings.request',
          site='src/laplace/web/project_work_surface.py:83'),
    Route(verb='change', concept='project@project', operation='work/session-preferences-change',
          door='http', route='/work/session-preferences', method='POST', source_operation='', because='Same guarded settings owner; pure query reads and exact change/withdraw custody, legacy flat changes retained',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='writing.session_settings.request',
          site='src/laplace/web/project_work_surface.py:83'),
    Route(verb='read', concept='storage@project', operation='work/storage',
          door='http', route='/work/storage', method='GET', source_operation='storage', because='',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='writing_storage.inspect(project root)',
          site='src/laplace/web/project_work_surface.py:51'),
    Route(verb='delete', concept='storage@project', operation='work/storage-prune',
          door='http', route='/work/storage/prune', method='POST', source_operation='storage_prune', because='',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='writing_storage.prune(project payload root)',
          site='src/laplace/web/project_work_surface.py:54'),
    Route(verb='read', concept='plan@plan', operation='work/structure',
          door='http', route='/work/structure', method='GET', source_operation='structure', because='',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='project_structure.read(project values repo_root http=True)',
          site='src/laplace/web/project_work_surface.py:109'),
    Route(verb='change', concept='artifact@section', operation='work/structure-change',
          door='http', route='/work/structure/change', method='POST', source_operation='structure_change', because='the HTTP door reuses every act and guard of the existing structure_change operation',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='project_structure.change(project payload repo_root)',
          site='src/laplace/web/project_work_surface.py:127'),
    Route(verb='change', concept='artifact@paragraph', operation='work/structure-change',
          door='http', route='/work/structure/change', method='POST', source_operation='structure_change', because='the HTTP door reuses every act and guard of the existing structure_change operation',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='project_structure.change(project payload repo_root)',
          site='src/laplace/web/project_work_surface.py:127'),
    Route(verb='create', concept='task@project', operation='work/structure-change',
          door='http', route='/work/structure/change', method='POST', source_operation='structure_change', because='the HTTP door reuses every act and guard of the existing structure_change operation',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='project_structure.change(project payload repo_root)',
          site='src/laplace/web/project_work_surface.py:127'),
    Route(verb='bind', concept='plan-section@section', operation='work/structure-change',
          door='http', route='/work/structure/change', method='POST', source_operation='structure_change', because='the HTTP door reuses every act and guard of the existing structure_change operation',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='project_structure.change(project payload repo_root)',
          site='src/laplace/web/project_work_surface.py:127'),
    Route(verb='create', concept='plan@plan', operation='work/structure-change',
          door='http', route='/work/structure/change', method='POST', source_operation='structure_change', because='the HTTP door reuses every act and guard of the existing structure_change operation',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='project_structure.change(project payload repo_root)',
          site='src/laplace/web/project_work_surface.py:127'),
    Route(verb='change', concept='plan-section@section', operation='work/structure-change',
          door='http', route='/work/structure/change', method='POST', source_operation='structure_change', because='the HTTP door reuses every act and guard of the existing structure_change operation',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='project_structure.change(project payload repo_root)',
          site='src/laplace/web/project_work_surface.py:127'),
    Route(verb='create', concept='plan-section@section', operation='work/structure-change',
          door='http', route='/work/structure/change', method='POST', source_operation='structure_change', because='the HTTP door reuses every act and guard of the existing structure_change operation',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='project_structure.change(project payload repo_root)',
          site='src/laplace/web/project_work_surface.py:127'),
    Route(verb='delete', concept='plan-section@section', operation='work/structure-change',
          door='http', route='/work/structure/change', method='POST', source_operation='structure_change', because='the HTTP door reuses every act and guard of the existing structure_change operation',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='project_structure.change(project payload repo_root)',
          site='src/laplace/web/project_work_surface.py:127'),
    Route(verb='change', concept='plan@plan', operation='work/structure-change',
          door='http', route='/work/structure/change', method='POST', source_operation='structure_change', because='the HTTP door reuses every act and guard of the existing structure_change operation',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='project_structure.change(project payload repo_root)',
          site='src/laplace/web/project_work_surface.py:127'),
    Route(verb='move', concept='plan-section@section', operation='work/structure-change',
          door='http', route='/work/structure/change', method='POST', source_operation='structure_change', because='the HTTP door reuses every act and guard of the existing structure_change operation',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='project_structure.change(project payload repo_root)',
          site='src/laplace/web/project_work_surface.py:127'),
    Route(verb='move', concept='claim-position@section', operation='work/structure-change',
          door='http', route='/work/structure/change', method='POST', source_operation='structure_change', because='the HTTP door reuses every act and guard of the existing structure_change operation',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='project_structure.change(project payload repo_root)',
          site='src/laplace/web/project_work_surface.py:127'),
    Route(verb='bind', concept='reference@section', operation='work/structure-change',
          door='http', route='/work/structure/change', method='POST', source_operation='structure_change', because='the HTTP door reuses every act and guard of the existing structure_change operation',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='project_structure.change(project payload repo_root)',
          site='src/laplace/web/project_work_surface.py:127'),
    Route(verb='place', concept='claim-position@section', operation='work/structure-change',
          door='http', route='/work/structure/change', method='POST', source_operation='structure_change', because='the HTTP door reuses every act and guard of the existing structure_change operation',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='project_structure.change(project payload repo_root)',
          site='src/laplace/web/project_work_surface.py:127'),
    Route(verb='delete', concept='claim-position@section', operation='work/structure-change',
          door='http', route='/work/structure/change', method='POST', source_operation='structure_change', because='the HTTP door reuses every act and guard of the existing structure_change operation',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='project_structure.change(project payload repo_root)',
          site='src/laplace/web/project_work_surface.py:127'),
    Route(verb='bind', concept='claim-position@section', operation='work/structure-change',
          door='http', route='/work/structure/change', method='POST', source_operation='structure_change', because='the HTTP door reuses every act and guard of the existing structure_change operation',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='project_structure.change(project payload repo_root)',
          site='src/laplace/web/project_work_surface.py:127'),
    Route(verb='move', concept='spine-position@plan', operation='work/structure-change',
          door='http', route='/work/structure/change', method='POST', source_operation='structure_change', because='the HTTP door reuses every act and guard of the existing structure_change operation',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='project_structure.change(project payload repo_root)',
          site='src/laplace/web/project_work_surface.py:127'),
    Route(verb='place', concept='spine-position@plan', operation='work/structure-change',
          door='http', route='/work/structure/change', method='POST', source_operation='structure_change', because='the HTTP door reuses every act and guard of the existing structure_change operation',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='project_structure.change(project payload repo_root)',
          site='src/laplace/web/project_work_surface.py:127'),
    Route(verb='delete', concept='spine-position@plan', operation='work/structure-change',
          door='http', route='/work/structure/change', method='POST', source_operation='structure_change', because='the HTTP door reuses every act and guard of the existing structure_change operation',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='project_structure.change(project payload repo_root)',
          site='src/laplace/web/project_work_surface.py:127'),
    Route(verb='run', concept='plan@plan', operation='work/structure-change',
          door='http', route='/work/structure/change', method='POST', source_operation='structure_change', because='the HTTP door reuses every act and guard of the existing structure_change operation',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='project_structure.change(project payload repo_root)',
          site='src/laplace/web/project_work_surface.py:127'),
    Route(verb='bind', concept='result@claim', operation='work/structure-change',
          door='http', route='/work/structure/change', method='POST', source_operation='structure_change', because='the HTTP door reuses every act and guard of the existing structure_change operation',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='project_structure.change(project payload repo_root)',
          site='src/laplace/web/project_work_surface.py:127'),
    Route(verb='read', concept='project@project', operation='work/workflow-history',
          door='http', route='/work/workflow-definitions', method='GET', source_operation='project', because='Existing workflow owner read; closed opt-in history schema and actual served scope, no destination/effect authority.',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='pipeline.workflow_definitions.read',
          site='src/laplace/web/workflow_definitions_surface.py:21'),
    Route(verb='read', concept='project@project', operation='work/workflow-operation-read',
          door='http', route='/work/workflow-definitions', method='POST', source_operation='project', because='Pure bounded JSON read through owner contract; POST is not Save or Start.',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='pipeline.workflow_definitions.read',
          site='src/laplace/web/workflow_definitions_surface.py:31'),
    Route(verb='change', concept='workflow-definition@project', operation='work/workflow-withdraw',
          door='http', route='/work/workflow-definitions/withdraw', method='POST', source_operation='workflow_definition_change', because='Exact original request no-admission decision under actual caller Scope; recorded receipt is not undone.',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='pipeline.workflow_definitions.withdraw',
          site='src/laplace/web/workflow_definitions_surface.py:54'),
    Route(verb='create', concept='task@project', operation='work/workflow-withdraw',
          door='http', route='/work/workflow-definitions/withdraw', method='POST', source_operation='workflow_definition_change', because='Exact original request no-admission decision under actual caller Scope; recorded receipt is not undone.',
          expiry='not a shim: the HTTP door keeps its route. Re-measure when HTTP replay and the browser delivery gate stop covering it; review 2026-11-01',
          owner='pipeline.workflow_definitions.withdraw',
          site='src/laplace/web/workflow_definitions_surface.py:54'),
)
KEEP_SELECTOR = ['action', 'basis', 'family', 'kind', 'mode', 'scope', 'status', 'view']
SELECTOR_ALIASES = {
    ('section_change', 'create-section'): ('create', 'src/laplace/manuscript/manuscript_structure.py:1132'),
    ('section_change', 'delete-section'): ('delete', 'src/laplace/manuscript/manuscript_structure.py:1131'),
    ('section_change', 'restore-section'): ('restore', 'src/laplace/manuscript/manuscript_structure.py:1131'),
}
SPELLING_TOLERANT = {
    ('concept_change', 'base_revision'): 'src/laplace/research/concepts.py:846',
    ('concept_change', 'mutation_revision'): 'src/laplace/research/concepts.py:1041',
    ('literature_bind', 'claim_revision'): 'src/laplace/research/literature.py:395',
    ('logical_plan_change', 'base_revision'): 'src/laplace/research/concepts.py:1041',
    ('proof_check', 'concept_revision'): 'src/laplace/pipeline/formal_verification.py:267',
    ('proof_check', 'source_revision'): 'src/laplace/pipeline/formal_verification.py:269',
    ('propose_revision', 'content_revision'): 'src/laplace/manuscript/proposal_basis.py:219',
    ('structure_change', 'expected_concept_revision'): 'src/laplace/manuscript/project_structure.py:853',
    ('structure_change', 'expected_revision'): 'src/laplace/manuscript/project_structure.py:766',
    ('structure_change', 'expected_source_revision'): 'src/laplace/manuscript/project_structure.py:777',
    ('visual_create', 'expected_revision'): 'src/laplace/pipeline/visual_production.py:139',
    ('writing_stage', 'known_revision'): 'src/laplace/writing/stages.py:81',
}
SELECTOR_DEFAULTS = {
    ('author_history', 'view'): ('corrections', 'src/laplace/writing/operations.py:379', 'spelled'),
    ('export_pdf', 'mode'): ('selected-source', 'src/laplace/writing/operations.py:224', 'spelled'),
    ('logical_plan', 'view'): ('attention', 'src/laplace/writing/operations.py:466', 'else-branch:catalog'),
    ('pipeline', 'view'): ('summary', 'src/laplace/writing/operations.py:257', 'spelled'),
    ('profile', 'view'): ('summary', 'src/laplace/manuscript/profiles.py:252', 'spelled'),
    ('repository', 'action'): ('list', 'src/laplace/projects/writing_sources.py:499', 'spelled'),
    ('research', 'view'): ('summary', 'src/laplace/research/research_catalogue.py:554', 'else-branch:result'),
    ('writing_stage', 'view'): ('guidance', 'src/laplace/writing/stages.py:62', 'spelled'),
    ('writing_style', 'view'): ('summary', 'src/laplace/manuscript/writing_style.py:321', 'spelled'),
}
GENERATED_FROM = 'tests/grammar_spec/mapping.csv lf-lines sha256:75b388a4c990d39ff65555131c862d3fe0bc4835e2cb12b149a517f161e5f999'
HTTP_GENERATED_FROM = 'tools/writing_verbs/http_routes.csv lf-lines sha256:398cb8f45a9bcb76ac075469758544521249a82cf623558a0b709e6a50768988'
SITE_HOW = {'reference_text': 'branch', 'apply_revision': 'branch', 'section_change': 'branch', 'block_change': 'branch', 'propose_revision': 'branch', 'proposal_supersede': 'branch', 'build': 'branch', 'build_status': 'branch', 'document': 'branch', 'style': 'branch', 'export_pdf': 'branch', 'chapter': 'branch', 'source': 'branch', 'help': 'branch', 'session_settings': 'branch', 'session_settings_change': 'branch', 'conversation_history': 'branch', 'dispatch_plan': 'branch', 'dispatch': 'branch', 'dispatch_launch': 'branch', 'dispatch_continue': 'branch', 'dispatch_status': 'branch', 'dispatch_returns': 'branch', 'pipeline': 'branch', 'writing_stage': 'branch', 'structure': 'branch', 'structure_change': 'branch', 'workflow_definition_change': 'branch', 'project': 'branch', 'framing': 'branch', 'argument': 'branch', 'task': 'branch', 'work_review': 'branch', 'development_source': 'branch', 'work_delivery': 'branch', 'task_status': 'branch', 'note': 'branch', 'note_status': 'branch', 'repository': 'branch', 'storage': 'branch', 'storage_prune': 'branch', 'project_metadata': 'branch', 'app_settings': 'branch', 'material_references': 'branch', 'material_reference_change': 'branch', 'project_metadata_change': 'branch', 'materials': 'branch', 'author_history': 'branch', 'author_changes': 'branch', 'read_artifact': 'branch', 'store_artifact': 'branch', 'research_object_change': 'branch', 'research_handover': 'branch', 'profile': 'branch', 'profile_change': 'branch', 'writing_style': 'branch', 'writing_style_calibration': 'branch', 'writing_style_change': 'branch', 'writing_style_profile_change': 'branch', 'project_guidance': 'branch', 'project_guidance_change': 'branch', 'research': 'branch', 'run_status': 'branch', 'research_reconcile': 'branch', 'research_record': 'branch', 'research_producer': 'branch', 'experiment_run': 'branch', 'run_cancel': 'branch', 'concept': 'routes-table', 'concept_tree': 'routes-table', 'concept_history': 'routes-table', 'concept_change': 'routes-table', 'logical_plan': 'routes-table', 'logical_plan_change': 'routes-table', 'references': 'routes-table', 'literature_discover': 'routes-table', 'literature_lookup': 'routes-table', 'literature_import': 'routes-table', 'literature_bind': 'routes-table', 'literature_scope': 'routes-table', 'reference_fetch': 'routes-table', 'literature_uses': 'routes-table', 'reference': 'routes-table', 'reference_source': 'routes-table', 'references_attached': 'routes-table', 'reference_attach': 'routes-table', 'reference_update': 'routes-table', 'reference_refresh': 'routes-table', 'visuals': 'routes-table', 'visual_create': 'routes-table', 'visual_render': 'routes-table', 'visual_place': 'routes-table', 'proof_targets': 'routes-table', 'proofs': 'routes-table', 'proof_check': 'routes-table'}
PRIMARY_ACT = {
    'app_settings': ('read', 'contract@project', 'first-row-of-mapping.csv (the owner requires its discriminator)'),
    'apply_revision': ('change', 'prose@paragraph', 'no-selector'),
    'argument': ('change', 'argument@plan', 'no-selector'),
    'author_changes': ('read', 'change-history@project', 'no-selector'),
    'author_history': ('read', 'note@project', 'owner-default'),
    'block_change': ('delete', 'block@paragraph', 'first-row-of-mapping.csv (the owner requires its discriminator)'),
    'build': ('run', 'build@project', 'no-selector'),
    'build_status': ('read', 'build@project', 'no-selector'),
    'chapter': ('create', 'chapter@chapter', 'no-selector'),
    'concept': ('read', 'concept-node@claim', 'no-selector'),
    'concept_change': ('bind', 'relation@relation', 'first-row-of-mapping.csv (the owner requires its discriminator)'),
    'concept_history': ('read', 'concept-node@claim', 'no-selector'),
    'concept_tree': ('read', 'concept-network@claim', 'no-selector'),
    'conversation_history': ('read', 'turn@project', 'no-selector'),
    'development_source': ('bind', 'repository@project', 'first-row-of-mapping.csv (the owner requires its discriminator)'),
    'dispatch': ('read', 'task@project', 'no-selector'),
    'dispatch_continue': ('run', 'task@project', 'no-selector'),
    'dispatch_launch': ('run', 'task@project', 'no-selector'),
    'dispatch_plan': ('create', 'task@project', 'no-selector'),
    'dispatch_returns': ('read', 'task@project', 'no-selector'),
    'dispatch_status': ('read', 'task@project', 'no-selector'),
    'document': ('read', 'document-form@project', 'no-selector'),
    'experiment_run': ('run', 'experiment@run', 'first-row-of-mapping.csv (the owner requires its discriminator)'),
    'export_pdf': ('run', 'export@project', 'owner-default'),
    'framing': ('change', 'framing@plan', 'no-selector'),
    'help': ('read', 'contract@project', 'no-selector'),
    'literature_bind': ('bind', 'reference@evidence', 'no-selector'),
    'literature_discover': ('read', 'reference-candidate@evidence', 'no-selector'),
    'literature_import': ('create', 'reference@evidence', 'no-selector'),
    'literature_lookup': ('read', 'reference@evidence', 'no-selector'),
    'literature_scope': ('read', 'reference@claim', 'no-selector'),
    'literature_uses': ('read', 'reference@claim', 'no-selector'),
    'logical_plan': ('read', 'concept-network@plan', 'owner-default'),
    'logical_plan_change': ('create', 'concept-node@claim', 'first-row-of-mapping.csv (the owner requires its discriminator)'),
    'material_reference_change': ('create', 'material-reference@project', 'first-row-of-mapping.csv (the owner requires its discriminator)'),
    'material_references': ('read', 'material-reference@project', 'no-selector'),
    'materials': ('read', 'artifact@project', 'no-selector'),
    'note': ('create', 'note@claim', 'no-selector'),
    'note_status': ('delete', 'note@claim', 'first-row-of-mapping.csv (the owner requires its discriminator)'),
    'pipeline': ('read', 'pipeline@project', 'owner-default'),
    'profile': ('read', 'architecture-profile@project', 'first-row-of-mapping.csv (the owner requires its discriminator)'),
    'profile_change': ('change', 'architecture-profile@project', 'first-row-of-mapping.csv (the owner requires its discriminator)'),
    'project': ('read', 'project@project', 'no-selector'),
    'project_guidance': ('read', 'guide-document@project', 'no-selector'),
    'project_guidance_change': ('change', 'guide-catalogue@project', 'first-row-of-mapping.csv (the owner requires its discriminator)'),
    'project_metadata': ('read', 'project-metadata@project', 'no-selector'),
    'project_metadata_change': ('change', 'project-metadata@project', 'no-selector'),
    'proof_check': ('run', 'proof@claim', 'no-selector'),
    'proof_targets': ('read', 'proof@claim', 'no-selector'),
    'proofs': ('read', 'proof@project', 'no-selector'),
    'proposal_supersede': ('delete', 'proposal@paragraph', 'no-selector'),
    'propose_revision': ('create', 'proposal@paragraph', 'no-selector'),
    'read_artifact': ('read', 'artifact@project', 'no-selector'),
    'reference': ('read', 'reference@evidence', 'no-selector'),
    'reference_attach': ('create', 'reference@evidence', 'no-selector'),
    'reference_fetch': ('run', 'reference-text@evidence', 'no-selector'),
    'reference_refresh': ('run', 'reference@project', 'no-selector'),
    'reference_source': ('read', 'reference@evidence', 'no-selector'),
    'reference_text': ('read', 'reference-text@evidence', 'no-selector'),
    'reference_update': ('change', 'reference@evidence', 'no-selector'),
    'references': ('read', 'reference@project', 'no-selector'),
    'references_attached': ('read', 'reference@project', 'no-selector'),
    'repository': ('read', 'repository@project', 'owner-default'),
    'research': ('read', 'result@project', 'owner-default'),
    'research_handover': ('create', 'artifact@project', 'first-row-of-mapping.csv (the owner requires its discriminator)'),
    'research_object_change': ('create', 'concept-node@claim', 'first-row-of-mapping.csv (the owner requires its discriminator)'),
    'research_producer': ('create', 'producer@run', 'no-selector'),
    'research_reconcile': ('change', 'result-binding@evidence', 'no-selector'),
    'research_record': ('record', 'result@run', 'no-selector'),
    'run_cancel': ('change', 'run@run', 'no-selector'),
    'run_status': ('read', 'run@run', 'no-selector'),
    'section_change': ('change', 'section@section', 'first-row-of-mapping.csv (the owner requires its discriminator)'),
    'session_settings': ('read', 'turn@project', 'no-selector'),
    'session_settings_change': ('change', 'turn@project', 'no-selector'),
    'source': ('read', 'source-file@paragraph', 'no-selector'),
    'storage': ('read', 'storage@project', 'no-selector'),
    'storage_prune': ('delete', 'storage@project', 'no-selector'),
    'store_artifact': ('change', 'artifact@project', 'no-selector'),
    'structure': ('read', 'plan@plan', 'no-selector'),
    'structure_change': ('change', 'artifact@section', 'first-row-of-mapping.csv (the owner requires its discriminator)'),
    'style': ('change', 'document-form@project', 'no-selector'),
    'task': ('create', 'task@section', 'no-selector'),
    'task_status': ('change', 'task@evidence', 'no-selector'),
    'visual_create': ('create', 'visual-spec@run', 'no-selector'),
    'visual_place': ('place', 'visual@section', 'no-selector'),
    'visual_render': ('run', 'visual@run', 'no-selector'),
    'visuals': ('read', 'visual@project', 'no-selector'),
    'work_delivery': ('bind', 'task@evidence', 'first-row-of-mapping.csv (the owner requires its discriminator)'),
    'work_review': ('record', 'task@evidence', 'no-selector'),
    'workflow_definition_change': ('change', 'workflow-definition@project', 'first-row-of-mapping.csv (the owner requires its discriminator)'),
    'writing_stage': ('read', 'stage@project', 'owner-default'),
    'writing_style': ('read', 'style-state@project', 'owner-default'),
    'writing_style_calibration': ('read', 'style-calibration@project', 'no-selector'),
    'writing_style_change': ('change', 'style-state@project', 'no-selector'),
    'writing_style_profile_change': ('change', 'style-profile@project', 'first-row-of-mapping.csv (the owner requires its discriminator)'),
    'authoring/apply': ('change', 'prose@paragraph', 'http-route'),
    'authoring/block-change': ('change', 'block@paragraph', 'http-route'),
    'authoring/build-start': ('run', 'build@project', 'http-route'),
    'authoring/build-status': ('read', 'build@project', 'http-route'),
    'authoring/correction-origin': ('read', 'note@paragraph', 'http-route'),
    'authoring/correction-prepare': ('read', 'source-file@paragraph', 'http-route'),
    'authoring/correction-request': ('read', 'note@paragraph', 'http-route'),
    'authoring/correction-request-save': ('create', 'note@paragraph', 'http-route'),
    'authoring/correction-settle': ('change', 'note@paragraph', 'http-route'),
    'authoring/document': ('read', 'document-form@project', 'http-route'),
    'authoring/events': ('read', 'turn@project', 'http-route'),
    'authoring/health': ('read', 'project@project', 'http-route'),
    'authoring/help': ('read', 'contract@project', 'http-route'),
    'authoring/history': ('read', 'act-ledger@project', 'http-route'),
    'authoring/interrupt': ('change', 'turn@project', 'http-route'),
    'authoring/proposal-decision': ('delete', 'proposal@paragraph', 'http-route'),
    'authoring/proposal-preview': ('read', 'proposal@paragraph', 'http-route'),
    'authoring/proposals': ('read', 'proposal@paragraph', 'http-route'),
    'authoring/providers': ('read', 'project@project', 'http-route'),
    'authoring/reader': ('read', 'project@project', 'http-route'),
    'authoring/section-change': ('change', 'plan-section@section', 'http-route'),
    'authoring/session': ('read', 'turn@project', 'http-route'),
    'authoring/session-settings-change': ('change', 'turn@project', 'http-route'),
    'authoring/session-settings-read': ('read', 'turn@project', 'http-route'),
    'authoring/session-turn': ('read', 'turn@project', 'http-route'),
    'authoring/state-summary': ('read', 'project@project', 'http-route'),
    'authoring/steer': ('change', 'turn@project', 'http-route'),
    'authoring/structural-undo': ('read', 'change-history@project', 'http-route'),
    'authoring/turn': ('run', 'turn@project', 'http-route'),
    'corpus/friction-create': ('create', 'technical-friction@project', 'http-route'),
    'corpus/friction-read': ('read', 'technical-friction@project', 'http-route'),
    'corpus/friction-report': ('record', 'technical-friction@project', 'http-route'),
    'http-door': ('change', 'project@project', 'http-route'),
    'projection/pdf': ('read', 'artifact@project', 'http-route'),
    'projection/source': ('read', 'source-file@paragraph', 'http-route'),
    'projection/source-save': ('change', 'source-file@paragraph', 'http-route'),
    'projects/app-settings': ('read', 'contract@project', 'http-route'),
    'projects/app-voice-change': ('change', 'style-profile@project', 'http-route'),
    'projects/create': ('create', 'project@project', 'http-route'),
    'projects/material-intake': ('read', 'material-reference@project', 'http-route'),
    'projects/material-intake-link': ('create', 'material-reference@project', 'http-route'),
    'projects/material-intake-original': ('read', 'artifact@project', 'http-route'),
    'projects/material-intake-read': ('read', 'artifact@project', 'http-route'),
    'projects/material-intake-upload': ('create', 'artifact@project', 'http-route'),
    'projects/material-reference-change': ('create', 'material-reference@project', 'http-route'),
    'projects/material-references': ('read', 'material-reference@project', 'http-route'),
    'references/literature_bind': ('bind', 'reference@evidence', 'http-route'),
    'references/literature_import': ('create', 'reference@evidence', 'http-route'),
    'references/literature_scope': ('read', 'reference@claim', 'http-route'),
    'references/reference_fetch': ('run', 'reference-text@evidence', 'http-route'),
    'references/reference_source': ('read', 'reference@evidence', 'http-route'),
    'references/reference_text': ('read', 'reference-text@evidence', 'http-route'),
    'research/record': ('record', 'result@run', 'http-route'),
    'research/record-request': ('read', 'result@project', 'http-route'),
    'research/run-request': ('read', 'run@run', 'http-route'),
    'review/adjudicate': ('change', 'prose@paragraph', 'http-route'),
    'review/adjudicate-comment': ('create', 'note@paragraph', 'http-route'),
    'walk/doc': ('read', 'document-form@project', 'http-route'),
    'work/delivery-read': ('read', 'task@evidence', 'http-route'),
    'work/materials': ('read', 'artifact@project', 'http-route'),
    'work/object-change': ('create', 'concept-node@claim', 'http-route'),
    'work/object-discovery': ('read', 'project@project', 'http-route'),
    'work/object-handover': ('create', 'artifact@project', 'http-route'),
    'work/profiles': ('read', 'architecture-profile@project', 'http-route'),
    'work/profiles-change': ('change', 'architecture-profile@project', 'http-route'),
    'work/session-preferences-change': ('change', 'project@project', 'http-route'),
    'work/session-preferences-read': ('read', 'project@project', 'http-route'),
    'work/storage': ('read', 'storage@project', 'http-route'),
    'work/storage-prune': ('delete', 'storage@project', 'http-route'),
    'work/structure': ('read', 'plan@plan', 'http-route'),
    'work/structure-change': ('change', 'artifact@section', 'http-route'),
    'work/workflow-history': ('read', 'project@project', 'http-route'),
    'work/workflow-operation-read': ('read', 'project@project', 'http-route'),
    'work/workflow-withdraw': ('change', 'workflow-definition@project', 'http-route'),
}
# -------------------------------------------------------------------------
# END ROUTES
# --------------------------------------------------------------------------- #


def _dig(payload: Mapping[str, Any], path: str, default=None) -> Any:
    """Read a dotted payload path (``op.kind``) without raising."""
    cur: Any = payload
    for part in path.split("."):
        if not isinstance(cur, Mapping) or part not in cur:
            return default
        cur = cur[part]
    return cur


def _put(payload: dict, path: str, value: Any) -> None:
    parts = path.split(".")
    cur = payload
    for part in parts[:-1]:
        nxt = cur.get(part)
        if part in cur and not isinstance(nxt,Mapping):
            raise ValueError("Supplied selector parent must be an object: " + path)
        cur[part] = dict(nxt) if isinstance(nxt, Mapping) else {}
        cur = cur[part]
    cur[parts[-1]] = value


def _drop(payload: dict, path: str) -> None:
    parts = path.split(".")
    cur = payload
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, Mapping):
            return
        cur[part] = dict(nxt)
        cur = cur[part]
    cur.pop(parts[-1], None)


def selector_matches(route: Route, payload: Mapping[str, Any]) -> bool:
    """Does this payload name this route's act?

    A kept selector key (``view``, ``mode``, ``action``, ``basis``, ``status``, ``kind``) is
    a projection of the ask, so a payload that OMITS it still names the route whose value is
    the owner's own default -- ``SELECTOR_DEFAULTS`` carries each default with the line that
    applies it.  A lifted key (``operation``, ``op.kind``) names the act and must match.
    """
    for path, value in route.selector:
        observed = _dig(payload, path)
        # An old spelling the OWNER itself normalises still names this route.  Nine audited
        # section_change sub-verbs are five acts at src/laplace/manuscript_structure.py:1043-1044,
        # so `create-section` is `create`; the caller is not refused over the spelling and the
        # rebuild uses the canonical one (so the round trip is not byte-exact and that call
        # falls through to its own payload).
        alias = SELECTOR_ALIASES.get((route.operation, str(observed or "")))
        if alias is not None and alias[0] == value:
            continue
        if observed is None and path in KEEP_SELECTOR:
            default = SELECTOR_DEFAULTS.get((route.operation, path))
            if default is not None and default[0] == value:
                continue
            return False
        if str(observed or "") != value:
            return False
    return True


BY_OPERATION: dict[str, tuple[Route, ...]] = {}
BY_PAIR: dict[tuple[str, str], tuple[Route, ...]] = {}


def _index() -> None:
    by_op: dict[str, list[Route]] = {}
    by_pair: dict[tuple[str, str], list[Route]] = {}
    for route in (*ROUTES, *(row for row in HTTP_ROUTES if row.operation in {"authoring/proposals","authoring/proposal-preview","authoring/proposal-decision","corpus/friction-read","corpus/friction-report","corpus/friction-create","projection/source"})):
        by_op.setdefault(route.operation, []).append(route)
        by_pair.setdefault((route.verb, route.concept), []).append(route)
    BY_OPERATION.clear()
    BY_PAIR.clear()
    # most specific selector first, so a nested row wins over its leaf ancestor
    for op, rows in by_op.items():
        BY_OPERATION[op] = tuple(sorted(rows, key=lambda r: -len(r.selector)))
    for pair, rows in by_pair.items():
        BY_PAIR[pair] = tuple(rows)


_index()


# --------------------------------------------------------------------------- #
# The shim direction: an old name becomes a request
# --------------------------------------------------------------------------- #
#: Which payload keys name the home a whole-project act is about.  The target is a
#: PROJECTION of the payload, never a consumption of it, so the round trip stays exact:
#: ``to_owner_call`` rebuilds the owner call from the payload alone and ignores ``target``.
TARGET_KEYS = ("node", "node_id", "id", "section_id", "section", "path", "file",
               "key", "citekey", "stage", "producer_id", "spec_id", "claim")


def target_for(project: str, concept: str, payload: Mapping[str, Any]) -> str:
    """The home id of the act: ``<project>`` or ``<project>::<id>`` (GRAMMAR.md §1)."""
    kind = g.concept_object(concept)
    home = g.HOME_KINDS.get(kind)
    if home is not None and home.id_is.strip() == "project":
        return project
    for key in TARGET_KEYS:
        value = payload.get(key) if isinstance(payload, Mapping) else None
        if isinstance(value, str) and value:
            return project + "::" + value
        if isinstance(value, (list, tuple)) and value and isinstance(value[0], str):
            return project + "::" + value[0]
    return project


def _home_id_without_token(kind: str, project: str, target: str) -> str:
    """The owner-declared id of a route home before a caller token can override it."""
    home = g.HOME_KINDS.get(kind)
    if home is not None and home.id_is.strip() == "project":
        return project or str(target or "").partition("::")[0]
    return target if "::" in str(target or "") else project


def requested_by_metadata(value: str) -> dict:
    """Bounded requested label; it is neither actual actor nor authority."""
    if not value:
        return {}
    import hashlib
    raw = value.encode("utf-8")
    return {"requested_by":{"text":value[:240], "sha256":hashlib.sha256(raw).hexdigest(),
                            "bytes":len(raw), "truncated":len(value)>240}}


@dataclass(frozen=True)
class Classified:
    """What the dispatch knows about one call, on any caller path."""
    route: Route | None
    request: g.Request | None
    owner_call: tuple[str, dict] | None
    exact: bool
    reason: str = ""
    #: did the VERB door, given only the request, find this same route and rebuild the same
    #: call?  False where two routes share a (verb, concept) and only the old name chooses.
    verb_door: bool = False
    verb_door_reason: str = ""
    #: guards whose rebuilt spelling differs from the caller's and whose door compares them
    #: as equal, each with the comparison that makes that true.
    tolerated: tuple[str, ...] = ()

    @property
    def row(self) -> dict:
        """The banked row's new grain: verb, concept, altitude -- never the operation name
        alone, which is the defect ``writing_tools.py:1017-971`` and ``:1000-1006`` bank
        today (synthesis §1.7)."""
        if self.route is None or self.request is None:
            return {"verb": None, "concept": None, "altitude": None,
                    "dispatch": "unmapped", "dispatch_reason": self.reason}
        return {"verb": self.route.verb, "concept": self.route.concept,
                "altitude": self.route.altitude, "target": self.request.target,
                **requested_by_metadata(self.request.by),
                "dispatch": "exact" if self.exact else "fell-through",
                **({} if self.exact else {"dispatch_reason": self.reason})}


def route_for_operation(operation: str, payload: Mapping[str, Any]) -> Route | None:
    rows = BY_OPERATION.get(str(operation), ())
    for route in rows:
        if selector_matches(route, payload):
            return route
    # A kept selector carrying a value the audit never saw: the owner's own else-branch
    # handles it (``writing_tools.py:647`` sends every `research` view but `result` to one
    # read; ``:379`` defaults a stage view), so the act is the DEFAULT route and the unknown
    # value stays in the payload where the owner reads it.  Nothing is invented: the route
    # is the one SELECTOR_DEFAULTS already declares, with its citation.
    for route in rows:
        if not route.keep or route.lift:
            continue
        if all(SELECTOR_DEFAULTS.get((route.operation, key), (None,))[0] == value
               for key, value in route.keep):
            return route
    return None


# These owner guards are opaque consumed edit bases, including null-create. A generic
# digest-home substitution cannot preserve their exact semantics. One mapping, both ways.
EXACT_OWNER_FIELDS = {'workflow_definition_change': {'expected_revision': 'definition_edit_guard'}}


def from_owner_call(operation: str, payload: Mapping[str, Any], *, project: str = "",
                    by: str = "", root=None) -> tuple[Route, g.Request]:
    """The shim rewrite; root resolves owner-relative file identities for live calls.

    Without a workspace, a caller can test a syntactic legacy round trip but cannot
    resolve manuscript-relative aliases into an owner's canonical file identity.
    """
    route = route_for_operation(operation, payload)
    if route is None:
        raise ValueError("no route for operation %r with this payload" % (operation,))
    rest = dict(payload)
    raw_expected = rest.pop("expected", ())
    if isinstance(raw_expected, str):
        raw_expected = (raw_expected,)
    elif not isinstance(raw_expected, (list, tuple)):
        raise ValueError("expected is a token or a list of tokens")
    # Parse here through the grammar's existing parser.  Besides keeping malformed input on
    # the unchanged fall-through path, this gives the old-name shim the owner's precedence:
    # a canonical token covers its home before a legacy guard of the same home is consulted.
    canonical = tuple(str(item) for item in raw_expected)
    canonical_tokens = tuple(g.parse(item) for item in canonical)
    covered = {token.kind for token in canonical_tokens}
    expected: list[str] = list(canonical)
    target = target_for(project, route.concept, payload)
    for path, _value in route.lift:
        _drop(rest, path)
    for owner_key, carrier in EXACT_OWNER_FIELDS.get(operation, {}).items():
        if owner_key in rest:
            if carrier in rest:
                raise ValueError('Use one spelling of the owner edit guard')
            rest[carrier] = rest.pop(owner_key)
    declared = {name for name, _h, _f, _o in route.guards}
    guards = list(route.guards)
    # A guard the audit's verb matrix does not attribute to this operation is still a guard:
    # the grammar's own census names its home, and leaving it in the payload would have the
    # request refused (GRAMMAR.md §4, rule 3).  These are counted in the lane report as
    # `(operation, guard)` pairs mapping.csv does not carry.
    for key in list(rest):
        if key in declared or key not in g.GUARD_NAMES:
            continue
        homes = g.GUARD_NAMES[key]
        form = "text" if key == "before" else (
            "counter" if homes[0] == "authoring-state" else "digest")
        guards.append((key, homes[0], form, True))
    for name, homes, form, _optional in guards:
        if name not in rest:
            continue
        value = rest.pop(name)
        if form == "digest":
            home = homes.split("|")[0].rstrip("?")
            if any(kind.rstrip("?") in covered for kind in homes.split("|")):
                continue
            if isinstance(value, str) and g._HEX.match(value or ""):
                home_id = _home_id_without_token(home, project, target)
                if root is not None and operation == "visual_place" and home == "source-file":
                    from pathlib import Path
                    from laplace.research import visuals_surface
                    path, _source = visuals_surface._selected_target(
                        project, payload.get("section") or payload.get("file"), Path(root))
                    if path is None:
                        raise ValueError("visual placement has no resolved target source file")
                    home_id = "%s::%s" % (project, path.relative_to(Path(root).resolve()).as_posix())
                expected.append(str(g.mint(
                    home, home_id, value)))
            else:
                # Not a digest, so it cannot be a token: it travels as content under the
                # form's one carrier name and the route restores the owner's spelling.
                rest[CARRIERS["text"]] = value
        elif form in ("text", "cursor"):
            rest[CARRIERS[form]] = value
        elif form == "counter":
            rest[CARRIERS["text"]] = value
    rest = g.to_payload(rest)          # the grammar's one rename, owner key -> carrier
    request = g.Request(verb=route.verb, concept=route.concept, target=target,
                        expected=tuple(expected), payload=rest, by=by)
    return route, request


# --------------------------------------------------------------------------- #
# The verb direction: a request becomes the owner call
# --------------------------------------------------------------------------- #
def _span_bytes(root, target: str) -> bytes | None:
    """The addressed prose span, for a caller that sends the token and not the text."""
    try:
        project, _, rest = target.partition("::")
        path, _, lines = rest.rpartition(":")
        start, _, end = lines.partition("-")
        from laplace.projects import artifacts as writing_artifacts
        base = writing_artifacts.project_root(root, project)
        text = (base / path).read_text(encoding="utf-8").splitlines(keepends=True)
        return "".join(text[int(start) - 1:int(end)]).encode()
    except Exception:
        return None


def owner_accepts_expected(route: Route) -> bool:
    """Whether the existing owner doors cover every identity guard of this route.

    The answer is derived from ``identity_doors.DOORS`` rather than maintained here.  Some
    operations have several owner gates (section_change checks plan and source separately),
    so their declared guards are combined before comparing them with the route.
    """
    from laplace.core import identity_doors
    from laplace.native import declarations as writing_declarations
    declaration = writing_declarations.DECLARATIONS.get(route.operation)
    if declaration is not None and not declaration.caller_expected:
        return False
    owned: dict[str, set[str]] = {}
    for shim in identity_doors.DOORS.values():
        if shim.old_operation != route.operation:
            continue
        for name, homes in shim.guard_to_home.items():
            owned.setdefault(name, set()).update(str(homes).split("|"))
    declared = [(name, {kind.rstrip("?") for kind in homes.split("|") if kind.rstrip("?")})
                for name, homes, _form, _optional in route.guards if homes]
    conflicts = [name for name, kinds in declared
                 if name in owned and not kinds <= owned[name]]
    if conflicts:
        raise ValueError("route guard homes disagree with their owner: %s %s"
                         % (route.operation, ", ".join(conflicts)))
    return bool(declared) and all(kinds <= owned.get(name, set()) for name, kinds in declared)


def expected_request_target(request: g.Request, route: Route, project: str) -> str | None:
    """The route-owned target, or None when the supplied target is already consistent.

    Whole-project homes retain the documented empty spelling.  Addressed homes must name
    the exact target derived by the existing route target resolver; aliases are not guessed.
    """
    expected = target_for(project, route.concept, request.payload)
    home = g.HOME_KINDS.get(g.concept_object(route.concept))
    supplied = str(request.target or "")
    if home is not None and home.id_is.strip() == "project":
        return None if supplied in {"", project} else project
    if supplied == expected:
        return None
    if "::" not in expected:
        # The route payload does not independently name the within-project object.  Preserve
        # an explicit target in the bound project and let the owner's canonical gate compare
        # its exact object home; only a cross-project target is decidable at this boundary.
        return None if supplied.startswith(project + "::") else project
    return expected


def expected_scope_error(request: g.Request, route: Route, project: str) -> str | None:
    """Return why canonical scope cannot be erased for a legacy-only owner, if so."""
    tokens = request.tokens()
    if len({token.key for token in tokens}) != len(tokens):
        return "duplicate canonical identities cannot be represented by legacy guard fields"
    allowed = {(kind, home_id_for(kind, request, project))
               for _guard, homes, _form, _optional in route.guards
               for kind in (raw.rstrip("?") for raw in homes.split("|")) if kind}
    wrong = [str(token.home) for token in tokens if token.key not in allowed]
    return ("canonical identity scope is outside the route owner: %s" % ", ".join(wrong)
            if wrong else None)


def to_owner_call(request: g.Request, *, root=None, route: Route | None = None,
                  preserve_expected: bool = False, materialize: bool = True) -> tuple[str, dict]:
    """The exact inverse of ``from_owner_call``.

    ``route`` is passed only by the shim direction, which already knows which route the old
    name selected.  A caller that writes a request by hand passes nothing and ``choose``
    decides -- and refuses to guess when two routes share the pair.  ``preserve_expected``
    is used only when :func:`owner_accepts_expected` proves that the existing owner doors
    cover every route guard; their canonical comparison then keeps token scope authoritative.
    """
    if route is None:
        route = choose(request.verb, request.concept, request.payload)
    payload = dict(request.payload)
    missing = object()
    for path, value in route.lift:
        supplied = _dig(payload,path,missing)
        if supplied is not missing and (type(supplied) is not type(value) or supplied != value):
            raise ValueError("Supplied selector conflicts with the selected route: " + path)
        _put(payload, path, value)
    payload = g.to_owner_payload(payload)   # the same rename, inverted, by the same module
    for owner_key, carrier in EXACT_OWNER_FIELDS.get(route.operation, {}).items():
        if carrier in payload:
            if owner_key in payload:
                raise ValueError('Use one spelling of the owner edit guard')
            payload[owner_key] = payload.pop(carrier)
    tokens = {t.kind: t for t in request.tokens()}
    for name, homes, form, _optional in route.guards:
        if form == "digest":
            token = None
            for home in homes.split("|"):
                token = tokens.get(home.rstrip("?")) or token
            if token is not None:
                if not preserve_expected:
                    payload[name] = token.digest
            elif CARRIERS["text"] in payload and name not in payload:
                payload[name] = payload.pop(CARRIERS["text"])
        elif form in ("text", "cursor"):
            carrier = CARRIERS[form]
            if carrier in payload:
                payload[name] = payload.pop(carrier)
            elif form == "text" and root is not None and materialize:
                # The cure: the caller sent the span token and not the span text.
                home = homes.split("|")[0].rstrip("?")
                token = tokens.get(home)
                raw = _span_bytes(root, request.target) if token is not None else None
                if token is not None and raw is not None and g.digest_bytes(raw) == token.digest:
                    payload[name] = raw.decode("utf-8")
                elif token is not None:
                    # Never fabricate agreement: hand the owner the token so it refuses in
                    # its own house (review_surface.py:1860) with its own sentence.
                    payload[name] = str(token)
        elif form == "counter":
            carrier = CARRIERS["text"]
            if carrier in payload:
                payload[name] = payload.pop(carrier)
            else:
                token = tokens.get("authoring-state")
                if token is not None and materialize:
                    payload[name] = _counter_for(root, request.target, token)
    if preserve_expected and request.expected:
        payload["expected"] = list(request.expected)
    return route.operation, payload


def _counter_for(root, target: str, token: g.Token) -> Any:
    """The ``authoring-state`` home's door compares an integer, not a digest."""
    try:
        from laplace.pipeline import authoring
        project = target.partition("::")[0]
        state = authoring.load(project, root)
        observed = g.identity(g.Home("authoring-state", project), project=project, root=root)
        if g.matches(str(token), observed):
            return state.get("revision")
        g.require([str(token)], [observed])
    except g.Refused as error:
        from laplace.core import identity_doors
        raise identity_doors.IdentityRefused(str(error),error.refusal) from error
    except Exception:
        pass
    return str(token)


class Ambiguous(ValueError):
    """Two routes share a (verb, concept) and the payload does not choose between them."""


def choose(verb: str, concept: str, payload: Mapping[str, Any]) -> Route:
    """The verb door's route selection: the request alone, no discriminator keyword."""
    rows = tuple(r for r in BY_PAIR.get((verb, concept), ()) if r.door == "both"
                 or (r.door == 'http' and (r.method == 'POST' or r.operation=='projection/source') and r.when
                     and all(_dig(payload,key) is not None and (not value or str(_dig(payload,key))==value)
                             for key,value in r.when)))
    if not rows:
        rows = BY_PAIR.get((verb, concept), ())
        if not rows:
            raise ValueError("(%r, %r) is not a declared pair of this dispatch"
                             % (verb, concept))
    if len(rows) == 1:
        return rows[0]
    scored: list[tuple[int, Route]] = []
    for route in rows:
        hits = 0
        if route.keep:
            if not selector_matches(route, payload):
                continue
            hits += 10 * len(route.keep)
        for key, value in route.when:
            present = _dig(payload, key)
            if present is None or (value and str(present) != value):
                hits = -1
                break
            hits += 1
        if hits >= 0:
            scored.append((hits, route))
    scored.sort(key=lambda row: -row[0])
    if not scored:
        raise Ambiguous("no route of %d for (%s, %s) matches this payload; the candidates "
                        "are %r" % (len(rows), verb, concept,
                                    [r.operation + ":" + ",".join(v for _k, v in r.selector)
                                     for r in rows]))
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        raise Ambiguous(
            "(%s, %s) has %d routes and this payload does not choose between %r. The "
            "dispatch refuses to guess: declare the distinguishing payload key in "
            "gen_routes.WHEN with the measurement that shows it."
            % (verb, concept, len(rows),
               [r.operation + ":" + ",".join(v for _k, v in r.selector) for _score, r in scored[:2]]))
    return scored[0][1]


# --------------------------------------------------------------------------- #
# Classification: what every caller path records
# --------------------------------------------------------------------------- #
def classify(operation: str, payload: Mapping[str, Any], *, project: str = "",
             by: str = "", root=None) -> Classified:
    """Rewrite one legacy call into the grammar and check the round trip is exact.

    This is called on EVERY caller path -- direct ``execute``, the HTTP door, the
    provider's turn -- which is the point: the banked row's grain is decided here, once,
    not in the three stores under two field names the owners keep
    (``manuscript_structure.py:150-151``, ``corpus_ingest.py:951``,
    ``pipeline/authoring.py:1120``; synthesis §1.7).
    """
    if not isinstance(payload, Mapping):
        return Classified(None, None, None, False, "payload is not an object")
    try:
        route, request = from_owner_call(operation, payload, project=project, by=by, root=root)
    except ValueError as exc:
        return Classified(None, None, None, False, str(exc)[:200])
    try:
        preserved = bool(payload.get("expected")) and owner_accepts_expected(route)
        back = to_owner_call(request, root=root, route=route, preserve_expected=preserved)
    except ValueError as exc:
        return Classified(route, request, None, False, "round trip: " + str(exc)[:160])
    exact, tolerated = _same_call(operation, dict(payload), back)
    owner_call = back
    if not exact and "expected" in payload:
        exact = _canonical_round_trip(route, request, back, project=project, by=by, root=root)
        if exact:
            # The semantic round trip below proved that the verb door reaches the same route,
            # request payload and ordered identities.  Execute and bank the caller's exact
            # canonical spelling so a classifier never silently replaces its home ids.
            owner_call = (operation, dict(payload))
            tolerated = ("expected=identity_doors.gate canonical/legacy equivalence",)
    reason = "" if exact else _why(dict(payload), back[1])
    door, door_reason = False, route.because or ""
    if route.door == "both" or (route.door == "http"
                                and route in BY_PAIR.get((route.verb,route.concept),())):
        try:
            chosen = choose(route.verb, route.concept, request.payload)
            if chosen.key == route.key:
                door = to_owner_call(request, root=root, preserve_expected=preserved) == back
                if not door:
                    door_reason = "the verb door rebuilt a different call"
            else:
                door_reason = "the verb door chose %s%s" % (
                    chosen.operation, "".join(" " + k + "=" + v for k, v in chosen.lift))
        except ValueError as exc:
            door_reason = str(exc)[:200]
    return Classified(route, request, owner_call, exact, reason, door, door_reason,
                     tuple(tolerated))


def native_example(operation: str, payload: Mapping[str, Any], *, project: str = "",
                   root=None) -> dict:
    """Publish a request only when the existing resolver proves the same owner call.

    Missing identities and shim-only/ambiguous routes stay explicit legacy contracts.
    The request is a render of the route and owner example, not another dispatch table.
    """
    classified = classify(operation, payload, project=project, root=root)
    if not (classified.exact and classified.verb_door and classified.request):
        return {"available": False,
                "why": classified.verb_door_reason or classified.reason
                       or "the exact owner example needs concrete identities"}
    req = classified.request
    covered = {token.kind for token in req.tokens()}
    missing = [homes for _name, homes, form, optional in classified.route.guards
               if form == "digest" and not optional
               and not any(home.rstrip("?") in covered for home in homes.split("|"))]
    if missing:
        return {"available": False,
                "why": "current identity unavailable for " + ", ".join(missing)
                       + "; use the reads in exact help expected rows"}
    return {"available": True, "native_request": {
        "verb": req.verb, "concept": req.concept, "target": req.target,
        "expected": list(req.expected), "payload": dict(req.payload), "by": req.by}}


def _canonical_round_trip(route: Route, request: g.Request, rebuilt: tuple[str, dict], *,
                          project: str, by: str, root=None) -> bool:
    """Did a canonical owner call and its rebuilt owner call mean the same request?

    This is deliberately a second pass through the same adapter, rather than an exact stamp
    inferred from an operation name. Home kind, home id, digest, nonidentity payload,
    writer and selected route must survive. Byte-identical canonical calls were already
    accepted above without erasing scope or duplicates; only an altered representation
    needs this extra proof. Actual currentness and scope are always checked by the owner.
    """
    try:
        rebuilt_route, rebuilt_request = from_owner_call(
            rebuilt[0], rebuilt[1], project=project, by=by, root=root)
    except ValueError:
        return False
    if rebuilt_route.key != route.key:
        return False
    if ((rebuilt_request.verb, rebuilt_request.concept, rebuilt_request.target,
         rebuilt_request.payload, rebuilt_request.by) !=
        (request.verb, request.concept, request.target, request.payload, request.by)):
        return False
    before = request.tokens()
    after = rebuilt_request.tokens()
    if len({token.key for token in before}) != len(before):
        return False
    if len({token.key for token in after}) != len(after):
        return False
    rebuilt_by_home = {token.key: token for token in after}
    return (set(rebuilt_by_home) == {token.key for token in before}
            and all(g.matches(token, rebuilt_by_home[token.key]) for token in before))


def _same_call(operation: str, original: dict, rebuilt: tuple[str, dict]):
    """Is the rebuilt owner call the same call?

    Byte equality, with one declared exception: a guard whose door compares through
    ``core.identity.revision_matches`` (``src/laplace/core/identity.py``)
    accepts the owner's prefixed spelling and the bare one as the same value, and the
    grammar's token normalises to the bare one (GRAMMAR.md §1).  For those guards -- and
    ONLY those, each named with the comparison that makes it true -- the two calls are the
    same call by the owner's own comparator.  A guard whose door compares the string raw is
    not tolerated: the rebuild counts as different and the live call falls through.
    """
    if rebuilt[0] != operation:
        return False, ()
    payload = rebuilt[1]
    if payload == original:
        return True, ()
    if set(payload) != set(original):
        return False, ()
    tolerated = []
    from laplace.core.identity import revision_matches
    for key, value in original.items():
        if payload[key] == value:
            continue
        cite = SPELLING_TOLERANT.get((operation, key))
        if cite and revision_matches(value, payload[key]):
            tolerated.append("%s=%s" % (key, cite))
            continue
        return False, ()
    return True, tuple(tolerated)


def _why(original: dict, rebuilt: dict) -> str:
    lost = sorted(set(original) - set(rebuilt))
    added = sorted(set(rebuilt) - set(original))
    moved = sorted(k for k in set(original) & set(rebuilt) if original[k] != rebuilt[k])
    return "lost=%r added=%r changed=%r" % (lost, added, moved)


# --------------------------------------------------------------------------- #
# The row the system banks, and where
# --------------------------------------------------------------------------- #
#: Banking an act on a caller path that banks nothing today ADDS a file to the workspace,
#: and the campaign's acceptance is differential replay against a tree that does not bank
#: it.  So the write is dialled, the dial has a retirement trigger -- the merge to master,
#: after which both sides bank -- and the row itself is produced on every path regardless
#: and returned in the receipt (GRAMMAR.md §5's ``banked_row``).
BANK_EVERY_PATH_ENV = "LAPLACE_WRITING_BANK_EVERY_PATH"


def bank_every_path() -> bool:
    raw = os.environ.get(BANK_EVERY_PATH_ENV)
    return True if raw is None else raw.strip().lower() not in {"0", "no", "off", "false"}


def shims() -> dict[tuple[str, str], g.Shim]:
    """One ``grammar.Shim`` per route: every old name, each with an expiry.

    GRAMMAR.md §6 rule 2: "a shim with no expiry is the mapping file this grammar refuses",
    and ``Shim.__post_init__`` is the gate -- it refuses an empty expiry, an expiry without a
    date, an expiry that does not name parity, a verb outside the nine, a concept whose
    object is not a home kind, and a guard mapped to something that is not a home.  So
    building these is itself a proof that every route's verb, concept and guard homes are
    legal: the module cannot import a shim it cannot justify.
    """
    out: dict[tuple[str, str], g.Shim] = {}
    for route in ROUTES:
        old_verb = route.operation
        if route.lift or route.keep:
            old_verb = "".join(k + "=" + v + " " for k, v in route.selector).strip()
        guard_to_home = {name: homes for name, homes, _form, _opt in route.guards if homes}
        shim = g.Shim(old_operation=route.operation, old_verb=old_verb, verb=route.verb,
                      concept=route.concept, guard_to_home=guard_to_home,
                      expiry=route.expiry)
        out[(route.operation, old_verb)] = g.register_shim(shim)
    return out


SHIMS = shims()


# --------------------------------------------------------------------------- #
# THE ONE TABLE, read by the contract as well as by the dispatch
# --------------------------------------------------------------------------- #
# Before this synthesis there were two.  `writing_verbs.ROUTES` said what act an operation
# is, by (verb, concept, selector), with the owner line that dispatches it; and every
# `declare(...)` in `writing_declared.py` said it again, by hand, in `verb=`, `concept=`,
# `also=` and `handler=`.  They AGREED on all 73 operations and 104 pairs when the two
# branches were measured (evidence/.../wave1/synth-contract-dispatch/one_table.json), which
# is exactly what a second copy looks like until it drifts -- and the merge made it drift
# inside one commit: `structure_change`'s route said `writing_tools.py:447` while its
# declaration said `:423`, for one fact, because the two lanes edited the file the citation
# names.  So the declaration no longer states them: `writing_declarations.declare` REFUSES
# `verb=`, `concept=`, `also=` and `handler=` and reads them here, and `help` renders what
# the dispatch routes on.
#
# The HTTP door is in the same table.  Its five declarations used to carry their own
# `verb=`/`concept=`/`handler=`, which was the same second copy one door further out.

def routes_for(operation: str) -> tuple[Route, ...]:
    """Every route of one old operation name, in the table's own order."""
    return BY_OPERATION.get(operation, ()) or tuple(
        route for route in HTTP_ROUTES if route.operation == operation)


def pairs_for(operation: str) -> tuple[tuple[str, str], ...]:
    """The distinct (verb, concept) pairs this operation is, its PRIMARY act first.

    The first is the declaration's `verb`/`concept`; the rest are its `also`.  Both used to
    be typed into the declaration by hand.  Which one is primary is `PRIMARY_ACT`, generated
    in mapping.csv's own row order (gen_routes.py: the route that needs no selector, else the
    route whose selector values are the owner's own defaults, else the operation's first row),
    because alphabetical is not an answer: the table's order made `structure_change` --- 26
    routes --- "bind claim-position@section", one of its 18 plan sub-verbs.
    """
    out: list[tuple[str, str]] = []
    first = PRIMARY_ACT.get(operation)
    if first is not None:
        out.append((first[0], first[1]))
    for route in routes_for(operation):
        pair = (route.verb, route.concept)
        if pair not in out:
            out.append(pair)
    if not out:
        raise ValueError("no route declares %r, so no (verb, concept) can be derived for "
                         "it; add its row to tests/grammar_spec/mapping.csv (tool door) or "
                         "tools/writing_verbs/http_routes.csv (HTTP door) and regenerate"
                         % (operation,))
    return tuple(out)


def site_for(operation: str) -> str:
    """The one line that dispatches this operation, as `src/laplace/<file>.py:<n>`.

    Generated by `gen_routes.owner_sites` out of the tree being built, which is why a merge
    that moves the line cannot leave this wrong while a hand-typed `handler=` is right (or
    the reverse, which is what happened here).
    """
    sites = [route.site for route in routes_for(operation) if route.site]
    if not sites:
        raise ValueError("the table names no dispatch line for %r" % (operation,))
    first = sites[0]
    if any(site != first for site in sites):
        raise ValueError("one operation, one dispatch line; %r has %r"
                         % (operation, sorted(set(sites))))
    return first


def old_spelling(route: Route) -> str:
    """How a caller spells this route through the old name, e.g.
    ``structure_change operation=plan op.kind=retitle``."""
    return (route.operation
            + "".join(" " + key + "=" + value for key, value in route.selector))


#: The date in an expiry, for the one-line form `help` publishes.
_DATE = __import__("re").compile(r"\b(20\d\d-\d\d-\d\d)\b")


def acts_for(operation: str) -> list[str]:
    """What `help` publishes about this operation: one LINE per act it can be.

        change plan-section@section <- structure_change operation=plan op.kind=retitle

    One line and not an object, because the price is measured: as objects with a `verb`, a
    `concept`, an `altitude` (which is the text after the `@` --- a fourth copy of it) and
    the whole `expiry` sentence, publishing the 146 acts across the 73 help responses cost
    45,131 characters, help went 140,764 -> 185,895, and this campaign exists partly because
    help was 221k.  As lines it is 11,935.

    A shim act ends with the news a caller is owed --- that the spelling it is being handed
    is going away, by when, and which instrument decides --- and the full condition stays in
    the table (`Route.expiry`, which `grammar.Shim` refuses without a date and the word
    parity, GRAMMAR.md §6 rule 2) and in the deposited shim list.
    """
    rows = []
    for route in routes_for(operation):
        line = "%s %s <- %s" % (route.verb, route.concept, old_spelling(route))
        if route.route:
            line += " (HTTP " + route.route + ")"
        if route.door == "shim":
            date = _DATE.search(route.expiry)
            line += (" [shim: old name only, retire by %s when "
                     "tools/writing_verbs/shim_retirement.py reports RETIRABLE]"
                     % (date.group(1) if date else "the table's date",))
        rows.append(line)
    return rows


def declared_homes(request: g.Request, route: Route | None, project: str
                   ) -> tuple[tuple[str, str, str], ...]:
    """``(guard name, home kind, home id)`` for every guard home the ROUTE declares.

    Read off ``Route.guards`` and not off the request, because the caller who most needs the
    read named is the one who named no token: a first-arrival request. Judged cost of the
    other choice, measured on this branch at `cf5138ef`: a tokenless
    ``create plan-section@section`` came back `said: "structure_change payload requires
    expected_revision"` with ``needed {"expected": []}`` -- the owner's bare field name beside
    an empty resolver, which is exactly the friction report's headline defect ("a door names
    the field it wants and does not name the read the value comes from").
    """
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for name, homes, _form, _optional in (route.guards if route is not None else ()):
        for raw in homes.split("|"):
            kind = raw.rstrip("?")
            if not kind or kind in seen or kind not in g.HOME_KINDS:
                continue
            seen.add(kind)
            out.append((name, kind, home_id_for(kind, request, project)))
    return tuple(out)


def home_id_for(kind: str, request: g.Request, project: str) -> str:
    """The home id to read: ``<project>`` for a project-level home, else the request's own
    target, which already carries ``<project>::<identity>`` (GRAMMAR.md section 1).

    The route target is authoritative here.  A caller token is the value being checked and
    cannot also choose which observed home diagnostic reconstruction reads.
    """
    base = project or str(request.target or "").partition("::")[0]
    target = str(request.target or "")
    if "::" not in target:
        target = target_for(base, request.concept, request.payload)
    return _home_id_without_token(kind, base, target)


def account(request: g.Request, *, root=None, project: str = "", route: Route | None = None
            ) -> tuple[dict, tuple[dict, ...]]:
    """``(needed, homes)`` for a refusal: the resolver, and one row per declared home.

    GRAMMAR.md section 5: ``needed`` IS the resolver, and it is built by the comparison, so it
    cannot be reachable from one caller path only (``retry_instruction`` is set inside
    ``writing_tools.py:1088@706a8204``, inside ``failure_response`` at ``:1049@706a8204``,
    whose two callers are ``:1240@706a8204`` and
    ``writing_provider.py:555@706a8204``; the field itself is deleted in this tree, and
    ``writing_tools.py:1292`` is the comment that records the deletion).  ``needed`` carries the tokens to retry with;
    ``Refusal.homes`` carries, per home, the token AND THE READ it comes from, so a refusal
    names the read even where no token can be minted here (18 of the 58 home kinds, each with
    its own reason -- ``g.HOME_KINDS[kind].closes``).
    """
    if route is None:
        try:
            route = choose(request.verb, request.concept, request.payload)
        except Exception:
            route = None
    expected: list[str] = []
    rows: list[dict] = []
    for guard, kind, home_id in declared_homes(request, route, project):
        home = g.HOME_KINDS[kind]
        row: dict = {"home": "%s:%s" % (kind, home_id), "guard": guard,
                     "read": home.read or "", "current_token": None}
        try:
            token = str(g.identity(g.Home(kind, home_id),
                                   project=project or home_id.partition("::")[0], root=root))
            row["current_token"] = token
            expected.append(token)
        except Exception as error:
            row["why"] = str(error)[:300]
            if not row["read"]:
                row["read"] = home.closes or ("no read is published for %s" % kind)
        rows.append(row)
    return ({"expected": expected} if expected or rows else {}), tuple(rows)


def resolver(request: g.Request, *, root=None, project: str = "", route: Route | None = None
             ) -> dict:
    """``needed`` alone.  ``account`` is the same walk and also returns the per-home rows."""
    return account(request, root=root, project=project, route=route)[0]


# --------------------------------------------------------------------------- #
# THE EDITOR'S HTTP DOORS, THROUGH THE SAME TABLE (WRITING-CONSOLIDATION-W1)
#
# The friction report counted the editor's doors as a separate contract surface with nothing
# published about them at all; the reconciliation then put four of them in this table and
# named the rest a residual (`writing_declared_http.py`'s own scope paragraph).  This is that
# residual closed: the editor's five doors and the comment door are rows of the SAME table,
# so a door's act is read off the table and never typed at the door.
#
# The three functions below are the whole coupling.  `http_act` answers "what act is this
# route?" from the table.  `grammar_request` answers "is this body already a grammar
# request?" --- and when it is, the door never looks at an old discriminator again.  A body
# that is not grammar-shaped is the SHIM path: the old flat payload, served by the same owner
# call, with the old spelling's expiry on record in `identity_doors.EDITOR_EXPIRY`.  One code
# path per door, two spellings into it, which is GRAMMAR.md section 6 rule 1.
# --------------------------------------------------------------------------- #
#: One HTTP door per NAME, and the name's FIRST row is its primary act --- the csv's own
#: order, which is how `pairs_for` already reads a tool operation's primary act.  A door with
#: several acts (the comment door has three, one per altitude) is several rows under one name,
#: so one declaration publishes all of them and every act is routable rather than declared in
#: a comment somewhere; `http_acts` returns them all.
HTTP_BY_NAME: dict[str, Route] = {}
for _route in HTTP_ROUTES:
    HTTP_BY_NAME.setdefault(_route.operation, _route)
del _route

#: The owner's own spelling of each non-digest guard form.  One row beside `CARRIERS`, which
#: holds the grammar's spelling of the same two guards; two tables would be the twenty-names
#: defect at the width of two names, so they sit together and their keys are asserted equal.
_OWNER_OF_CARRIER = {"text": "before", "cursor": "before"}
assert set(_OWNER_OF_CARRIER) == set(CARRIERS), (
    "every non-digest guard form has one owner spelling and one grammar carrier")


def http_act(name: str) -> tuple[str, str, str]:
    """``(verb, concept, altitude)`` of one HTTP door, from the table's own row.

    Raises ``KeyError`` naming the row source, because a door whose act is not in the table
    is a door whose act is typed at the door --- the defect this closes.
    """
    route = HTTP_BY_NAME.get(name)
    if route is None:
        raise KeyError("no HTTP route named %r in the one table; add a row to "
                       "tools/writing_verbs/http_routes.csv and regenerate with "
                       "tools/writing_verbs/gen_routes.py (names: %r)"
                       % (name, sorted(HTTP_BY_NAME)))
    return (route.verb, route.concept, route.altitude)


def http_acts(name: str) -> tuple[tuple[str, str], ...]:
    """Every ``(verb, concept)`` one HTTP door is, in the table's order, primary first."""
    http_act(name)                       # refuses a name the table does not route
    return tuple(dict.fromkeys((route.verb, route.concept) for route in HTTP_ROUTES
                               if route.operation == name))


def http_methods(name: str) -> tuple[str, ...]:
    """Every HTTP method one declared door name accepts, from the generated table."""
    http_act(name)
    return tuple(dict.fromkeys(route.method for route in HTTP_ROUTES
                               if route.operation == name))


def http_source_operation(name: str) -> str:
    """The one existing tool operation an HTTP door derives from, or empty."""
    http_act(name)
    sources = {route.source_operation for route in HTTP_ROUTES
               if route.operation == name and route.source_operation}
    if len(sources) > 1:
        raise ValueError("one HTTP operation cannot inherit from several tool operations: %r"
                         % (sorted(sources),))
    return next(iter(sources), "")


def grammar_request(body: Mapping[str, Any], *, name: str, target: str = "",
                    concept: str = "") -> g.Request | None:
    """The body as a grammar ``Request``, or ``None`` when it is the old flat payload.

    A body is grammar-shaped exactly when it carries a ``concept``.  That is the one
    discriminator, and it is not a guess: ``concept`` is a REQUEST field
    (``Request.FIXED``), a payload may not restate it (``Request.__post_init__``), and no
    recorded row of the corpus carries it --- so the old spelling and the new one cannot be
    confused, and a replay of the corpus never enters this branch.

    ``concept`` overrides the body's own when the door resolves it itself (the comment door
    resolves it from the altitude).  The verb comes from the body when it names one of the
    nine, and from the table otherwise, so a caller may send ``{concept, payload}`` alone.
    """
    if not isinstance(body, Mapping) or not (concept or body.get("concept")):
        return None
    table_verb, table_concept, _altitude = http_act(name)
    verb = str(body.get("verb") or "")
    if verb not in g.VERBS:
        verb = table_verb
    chosen = str(concept or body.get("concept") or table_concept)
    payload = body.get("payload")
    if not isinstance(payload, Mapping):
        payload = {k: val for k, val in body.items() if k not in g.Request.FIXED}
    expected = body.get("expected") or ()
    if isinstance(expected, str):
        expected = (expected,)
    return g.Request(verb=verb, concept=chosen,
                     target=str(target or body.get("target") or ""),
                     expected=tuple(str(t) for t in expected),
                     payload=g.to_owner_payload(dict(payload)),
                     by=str(body.get("by") or ""))


def owner_body(request: g.Request, **old_spelling: Any) -> dict[str, Any]:
    """The owner-shaped body one grammar request becomes, at the door that owns it.

    ``old_spelling`` is the discriminator the EXISTING owner branches on --- the thing a
    shim restores (GRAMMAR.md section 6: a shim rewrites, it never implements).  ``expected``
    rides through untouched because every one of these doors takes it now; the text guards
    travel under the carriers ``CARRIERS`` declares (``before_content`` -> ``before``), so
    one spelling crosses the wire and the owner receives the bytes it always received.
    """
    out: dict[str, Any] = dict(request.payload)
    for form, carrier in CARRIERS.items():                       # text, cursor
        if carrier in out:
            out[_OWNER_OF_CARRIER[form]] = out.pop(carrier)
    out.update(old_spelling)
    if request.expected:
        out["expected"] = list(request.expected)
    if request.by:
        out["by"] = request.by
    return out


def empty_presence_declared(operation: str) -> bool:
    """Does this owner give ``expected: []`` a meaning?  Exactly when the owner's composed schema does
    (``writing_declarations._owner_guard_schema``): the operation has routes that take canonical tokens and none
    of them requires a guard (``research_record`` creation, ``visual_place``).  An owner with a required digest
    guard composes the nonempty guard invariant, and an owner that takes no canonical tokens gives an empty
    array no meaning; both refuse it.  Pure: the generated route table only."""
    eligible = [route for route in routes_for(operation) if owner_accepts_expected(route)]
    return bool(eligible) and not any(not optional for route in eligible for _n, _h, _f, optional in route.guards)
