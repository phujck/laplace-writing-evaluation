# Dispatch — the one path from work to agents

(Reworked 2026-07-09 by the staged-generation rebuild: the typed section BRIEF
is retired with the condemned generating layer; the prose worker now compiles
from the closed narrative packet. The dispatch LAW is unchanged — one
compiler, one prompt path. See
[staged_generation](canon://operations/staged_generation) for the stage
architecture this dispatch surface serves.)

## compile_dispatch — the dispatch law, mechanical

`pipeline.dispatch.compile_dispatch(target, goal, worker)` is the ONLY path
from a work item to an agent prompt. Worker families:

- **Node workers** (`derive`/`mint`, and `figure`/`simulate` without a named
  generator): the prompt opens with the graded-node kernel
  ([graded_node](canon://engine/graded_node) — the whole, the piece, the law),
  then the node-local OBJECT at depth, then POLICY as canon HANDLES
  (`schema.POLICY_HANDLES` — never copied rules; a standard change propagates
  because nothing is duplicated).
- **Staged planning workers** (`structure`, `narrative`): kernel + POLICY +
  an OBJECT carrying the stage's inputs (contract skeletons + reader-state
  graph; section contract + pinned nodes + settled figure specs + equation
  ledger). Their outputs are ARTIFACTS (`section_contracts.json`,
  `narrative/<sid>.json`), each validated by its own gate before anything
  downstream may run.
- **The prose realiser** (`prose`): NO kernel, NO policy handles — the clean
  stage preamble (`schema.PROSE_STAGE_PREAMBLE`), the versioned voice profile
  (`profiles/voice/` — the ONLY seat besides the weld where voice exists),
  the CLOSED narrative packet, and the output contract (fragment with
  `% PLAN`/`% NODES` markers + a prose-provenance sidecar). Engine framing in
  a prose context is the scaffolding-leak class the mandate's §1.8 catalogues;
  the packet is everything the realiser may see (context isolation, §13).
- **Script-backed workers** (`figure`/`simulate` with a provenance-named
  generator; `render` always): the dispatch is the script call, never an
  agent — mechanical work stays mechanical.

`<sid>_dispatch.md` files are materialised under the `dispatches/` stage dir
(one producer, `compile_section_dispatches`). Every compile logs `execute`
telemetry for the skills it rides: the dispatch path itself feeds the fitness
loop.

An agent prompt is `reconstruct(node, goal)`, never `read(file)`. Hand-written
briefs are the flatten reflex one level up; none remain — and the brief as an
artifact class is gone with the layer that leaked through it.

## The leak boundary

Configuration text surfacing in prose is the leak
([object_not_artefact](canon://workflow/object_not_artefact)); the `meta_leak`
gate scans compiled tex against the schema lexicon AND echo-scans 6-word
shingles of every configuration source: compiled dispatch POLICY channels, the
prose stage preamble, and the voice profile itself. The voice failure-pattern
detector (`verify.check_voice`, `schema.VOICE_FAILURE_PATTERNS`) guards the
catalogued failure classes at the same boundary. The
[welder](canon://skills/welder) remains the global backstop for narrative
leaks no lexicon can name.

## The consumer loop

`storyboard.rebuild` (expensive mode) validates, checks narrative freshness
(the §7.2 validator doubles as the staleness check), compiles prose
dispatches for covered sections, and cuts `dispatches/dispatch_manifest.json`
(`plan_mtime_ns` freshness — one producer, self-invalidating).
`project-staged` consumes the manifest: narrative planners for stale sections,
prose realisers from their compiled dispatches, the mechanical validation
boundary (fidelity + voice detector + meta_leak; a failing section re-renders
ONCE from the SAME spec), then the [welder](canon://skills/welder) ONCE over
the assembled draft — voice last, at the weld. Judgement and the
`project-fixedpoint` convergence loop run only AFTER the first weld (his
sequencing, 2026-07-09). Every flag — mechanical and judged — lands through
the ONE feedback door (`whitepaper/feedback/feedback.jsonl`, typed +
node-routed). A panel round and the author's review propagate identically:
[propagate](canon://operations/pipeline_operators) reads the same door and
routes each kind to its owning stage (`schema.KIND_TO_WORK` +
`schema.WORK_TO_LAYER` — a downstream layer never compensates for an upstream
defect).
