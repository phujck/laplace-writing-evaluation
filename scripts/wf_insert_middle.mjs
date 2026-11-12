import { bindDispatchAgent } from './dispatch_gate.mjs'
agent = bindDispatchAgent(agent, () => args?.dispatchAdmissions ?? globalThis.dispatchAdmissions)

export const meta = {
  name: 'insert-middle',
  description: 'Insert the missing mid-grade the closure test specified (his 2026-06-11: the drift IS the spec). For each generator: implement its gap verbatim — split the drifters into their named rungs, enrich the closers to act-sufficiency — and emit a RESPONSE-FUNCTION ESSENCE per node (goal-conditioned: what to pull below, what to return up; minimal AND sufficient), NOT a static summary. The essences are the network being built: the model writes SYMBOLS (essences, memberships, proposed moves); interaction strengths are computed MECHANICALLY afterward from shared-child structure, never asserted by a model. Output feeds the rung-grade + generator-grade closure re-test (the deposit gate). Generalised by key 2026-06-11 (wave 2): pass {structFile, gens, name, closureFile:null} — with no closure verdicts the spec is the POWER-LAW BREAK (a generator sitting directly on its papers wants a rung grade at branching ~3-6).',
  phases: [
    { title: 'Regrade', detail: 'per generator: implement the closure gap — rungs + response-function essences + paper assignment', model: 'sonnet' },
  ],
}

let A = args
if (typeof A === 'string') { try { A = JSON.parse(A) } catch (e) { A = {} } }
A = A || {}
const STRUCT = A.structFile || 'collaborator_corpus/_structural/mccaul.json'
// closureFile: undefined => the mccaul default; null/'' => NO closure verdicts (mechanical spec)
const CLOSURE = A.closureFile === undefined ? 'collaborator_corpus/_structural/mccaul_closure.json' : (A.closureFile || null)
const NAME = A.name || "Gerard McCaul"

// default: the six mccaul generators, in mccaul_closure.json verdicts[] order; mode read off the banked verdict
const GENS = A.gens || [
  { idx: 0, mode: 'split',  key: 'unification' },
  { idx: 1, mode: 'enrich', key: 'open-quantum-systems' },
  { idx: 2, mode: 'split',  key: 'laser-control' },
  { idx: 3, mode: 'enrich', key: 'superoscillations' },
  { idx: 4, mode: 'split',  key: 'quantum-algorithms' },
  { idx: 5, mode: 'split',  key: 'reservoir-ml' },
]

const REGRADE = { type: 'object', properties: {
  generator: { type: 'string', description: 'the original generator label, verbatim from the upfold' },
  generator_essence: { type: 'string', description: 'the generator RESPONSE-FUNCTION essence: 1-3 sentences — what this program IS at its grade, what a goal arriving here should pull from below (which rungs/papers, under what conditions), what it returns upward. Minimal (shorter than its floor) and sufficient (a blind reader could re-derive the children).' },
  rungs: { type: 'array', items: { type: 'object', properties: {
    name: { type: 'string', description: 'kebab-case rung handle' },
    essence: { type: 'string', description: 'the rung response-function essence, same contract as the generator essence, one grade more specific' },
    papers: { type: 'array', items: { type: 'string', description: 'W... ids assigned to this rung (every member paper to exactly one rung)' } } },
    required: ['name', 'essence', 'papers'] },
    description: 'the mid-grade. EMPTY for enrich-mode generators (no rung inserted).' },
  moves: { type: 'array', items: { type: 'object', properties: {
    paper: { type: 'string' }, from: { type: 'string' }, to: { type: 'string' }, why: { type: 'string' } },
    required: ['paper', 'from', 'to', 'why'] },
    description: 'PROPOSED cross-cluster paper moves the gap spec directed you to check. Propose, never silently move.' },
  note: { type: 'string' } },
  required: ['generator', 'generator_essence', 'rungs', 'moves', 'note'] }

function gapSpec(g) {
  if (CLOSURE) return `Read ${CLOSURE} (Read tool): verdicts[${g.idx}] is YOUR generator. Its "gap" field is the precise, banked spec of what is missing — implement it EXACTLY, neither more nor less.`
  return `No closure verdicts exist for this corpus — the mechanical gate ran CLEAN at the generator grade. The spec is the POWER-LAW BREAK: the generator sits directly on its member papers (a grade is missing when branching exceeds ~6). ` + (g.mode === 'split'
    ? `Insert the missing mid-grade: split the members into coherent rungs at branching ~3-6 papers per rung, read off the papers' OWN ladders — shared techniques, shared goals, one program-thread per rung; never an arbitrary slice, never a rung named for a paper.`
    : `This generator is small enough to stay flat (no rung inserted): rewrite its essence to act-sufficiency — promote the load-bearing mid-grade machinery (the shared techniques and what discriminates the members) into the essence itself.`)
}

phase('Regrade')
const nSplit = GENS.filter(g => g.mode === 'split').length
log(`insert-middle [${NAME}]: ${GENS.length} generators (${nSplit} split + ${GENS.length - nSplit} enrich) <- ${CLOSURE || 'mechanical power-law spec (no closure file)'}`)
const out = await parallel(GENS.map(g => () =>
  agent(`You are the MIDDLE-INSERTER for ONE generator of ${NAME}'s structural ladder.
${gapSpec(g)}
Read ${STRUCT}: the program list (top-level "program" or nested "upfold.program") — entry [${g.idx}]${g.label ? ` ("${g.label}")` : ''} is YOUR generator, with its member papers (W... ids); "ladders" holds every paper's own goal/approach/techniques/results ladder. Work ONLY from these files.

MODE = ${g.mode.toUpperCase()}.
- SPLIT: insert the mid-grade rungs. Assign EVERY member paper to exactly ONE rung. Emit a response-function essence for the generator AND for each rung.
- ENRICH: no rung is inserted (rungs: []). Rewrite the generator essence to act-sufficiency (promote the named mid-grade machinery into it).

THE ESSENCE CONTRACT (both grades): a RESPONSE FUNCTION, not a summary. 1-3 sentences stating (a) what this node IS at its grade, (b) what a goal arriving here should PULL from below — which children, under what goal-conditions, and (c) what it RETURNS upward. MINIMAL: genuinely shorter than its floor, no inlining of children. SUFFICIENT: a blind reader holding only the essence could re-derive which children belong under it. Invent nothing — read it off the ladders.

If the spec directs a cross-cluster check (e.g. papers silently absorbed into another cluster, or an outlier to flag), DO the check against the program list and record findings in moves[] as PROPOSALS — never silently reassign across generators.
Return via StructuredOutput.`,
    { label: `regrade:${g.key}`, model: 'sonnet', schema: REGRADE, phase: 'Regrade' })
    .then(r => ({ ...r, _idx: g.idx, _mode: g.mode, _key: g.key }))
    .catch(() => null)
))
const ok = out.filter(Boolean)
log(`regraded: ${ok.length}/${GENS.length} generators (${ok.filter(r => r._mode === 'split').length} split, ${ok.filter(r => r._mode === 'enrich').length} enriched); rungs: ${ok.reduce((n, r) => n + r.rungs.length, 0)}; proposed moves: ${ok.reduce((n, r) => n + r.moves.length, 0)}`)
return { regraded: ok }
