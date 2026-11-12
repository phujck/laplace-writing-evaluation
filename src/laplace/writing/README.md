# Writing backend owners

These modules implement the shared state and operations behind the human app and
agent tools. Start at the [code overview](../../../docs/writing-code-overview.md)
for the whole system, or the [source map](../../../docs/writing-source-map.md)
for the full owner, storage, lock, lifetime and test tables.

## The authoring domain (this package)

| Owner | Purpose |
|---|---|
| [turn_context.py](turn_context.py) | Select and frame the context delivered to a turn |
| [turn_admission.py](turn_admission.py) | Open and configure sessions; admit a request with its session, Work and original basis; the lifecycle entry (`start_turn`) |
| [turn_jobs.py](turn_jobs.py), [turn_execution.py](turn_execution.py) | Own live jobs and execute one admitted turn |
| [provider.py](provider.py), [provider_catalogue.py](provider_catalogue.py) | Provider transports and the passive provider catalogue |
| [operating.py](operating.py) | The operating brief, session policy and session workspaces |
| [provider_updates.py](provider_updates.py) | Author updates and turn input joined at project tool results |
| [turn_control.py](turn_control.py), [child_hosts.py](child_hosts.py), [dispatch_execution.py](dispatch_execution.py), [dispatch_parent.py](dispatch_parent.py), [dispatch_returns.py](dispatch_returns.py) | Steering, interruption, explicit child execution and dispatch returns |
| [session_projection.py](session_projection.py), [session_reads.py](session_reads.py) | Passive session shapes and the session read model (state, turn detail, failures) |
| [turn_reads.py](turn_reads.py), [mutation_attribution.py](mutation_attribution.py) | Consumed-read baselines and which reads a write affected |
| [reads.py](reads.py), [operations.py](operations.py), [tool_sessions.py](tool_sessions.py), [tool_source.py](tool_source.py), [tool_work.py](tool_work.py) | The read contract and the one operation table (admission, dispatch, pure replay) with its family bodies |
| [delivery.py](delivery.py) | The shared delivery plan and private incoming carrier of one tool call |
| [source_execution.py](source_execution.py) | Optional human-issued Source commission accounting in the existing journal/index; shared admitted-call/app/session limits and finite stop/drain |
| [schemas.py](schemas.py), [stages.py](stages.py), [prepared_work.py](prepared_work.py) | Operation input contracts, writing stages and prepared Work |
| [records/](records/) | Journal reads and the one journal write (`records/_bank.py`), public-body access and derived conversation/history folds |

The owners these call live in their own packages: source application, currentness, reconciliation and documents in
[manuscript/](../manuscript/__init__.py); artifacts and the project lifecycle in [projects/](../projects/__init__.py);
Work delivery and development source in [work/](../work/__init__.py); research in [research/](../research/__init__.py);
Writing's body and representation seams in [representation/](../representation/__init__.py). The doors are
[native/tools.py](../native/tools.py) (the project tool gateway) and [web/authoring.py](../web/authoring.py) with
[web/authoring_http.py](../web/authoring_http.py) (the /authoring HTTP door); no owner imports a door
(`tests/test_core_state_effects.py`, `tests/test_core_runtime_dispatch.py`). The
[Work lifecycle](../../../docs/writing-work-review-lifecycle.md) and
[consulted-read recovery](../../../docs/writing-consulted-read-recovery.md) guides explain the related contracts.

## Change the owner once

Resolve the registered project and selected source through their existing owners.
Read the declared operation and current revision, preserve the role and source
fences, make the change, then inspect its receipt and actual result. Keep native,
HTTP and human consumers aligned. The source map's
[change-and-test route](../../../docs/writing-source-map.md#7-how-to-change-and-test-a-feature)
explains route generation, assets and focused verification.
