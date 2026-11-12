# Engine Domain Axioms

The domain of the engine's OWN machinery — the conceptric→storyboard→projection
pipeline, its ledgers, gates, briefs, dispatch, and operators. Added 2026-07-08
(the infrastructure deep-dive) so operational goals route here instead of
mis-inferring a content domain.

1. **There is one thing.** Every act enters by reconstruction — local views of
   a global conceptric. An agent prompt is `reconstruct(node, goal)` compiled
   by [dispatch](canon://operations/briefs_and_dispatch), never `read(file)`.
2. **Two ledgers, one engine, one transaction.** All state changes are
   append-only records on the [two-ledger system](canon://operations/two_ledger_system);
   dual-ledger writes ride one transaction or they do not land.
3. **The plan is downstream.** Substrate first, placement second, prose third —
   [the operators](canon://operations/pipeline_operators) enforce the order and
   the [restructure how-to](canon://operations/restructure_howto) carries the
   declarative arc.
4. **Claims → gates.** Every operational surface backs its claim with an
   executable check ([gate registry](canon://operations/gate_registry));
   unknown checks hard-fail; rendered docs cannot drift from the code that
   generates them.
5. **Object, not artefact.** Policy configures generators through fenced
   channels and handles; a policy sentence in an output is the defect
   ([the schema](canon://operations/projection_plan_schema) carries the
   channel contract).
6. **The up-operator closes every session.** Work that does not fold back into
   the global — canon node, embedding, orient reachability — does not pass
   (`scripts/sewup.py`).
