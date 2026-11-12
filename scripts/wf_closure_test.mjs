import { bindDispatchAgent } from './dispatch_gate.mjs'
agent = bindDispatchAgent(agent, () => args?.dispatchAdmissions ?? globalThis.dispatchAdmissions)

export const meta = {
  name: 'closure-test',
  description: 'The fixed-point / dead-end test on a structural ladder (his 2026-06-11: DOWN = the constraint, UP = the generator; the fixed point is where the generator recovered going up reproduces the constraint found going down). For each upfolded generator, a BLIND agent re-derives the generator from ONLY its papers floor (results + technique handles, in _closure_floors.json; the generator label lives in a SEPARATE file it never reads) - the UP direction. A judge then reads the stated label (_closure_labels.json) and compares: CLOSES (the floor folds back up to the generator => the route runs both ways, a fixed point), DRIFTS (recovers a real but different program => the label is off), or DEAD-END (cannot recover / does not cohere). The disagreement IS the operatorial residual - the spec for what to ADD or REARRANGE. builder != judge: the upfold built the generators; a blind re-folder re-derives them; a third compares.',
  phases: [
    { title: 'Recover', detail: 'blind: re-derive the generator from its floor only (the UP direction)', model: 'sonnet' },
    { title: 'Adjudicate', detail: 'compare recovered vs stated: closes / drifts / dead-end + the gap', model: 'sonnet' },
  ],
}

let A = args
if (typeof A === 'string') { try { A = JSON.parse(A) } catch (e) { A = {} } }
const N = (A && A.n) || 6
const FLOORS = (A && A.floorsFile) || 'collaborator_corpus/_structural/_closure_floors.json'
const LABELS = (A && A.labelsFile) || 'collaborator_corpus/_structural/_closure_labels.json'
// indices: run on exactly these entry idxs (the flagged extremes); default = first N
const items = (A && A.indices ? A.indices : Array.from({ length: N }, (_, i) => i)).map(i => ({ idx: i }))

const RECOVERED = { type: 'object', properties: {
  recovered: { type: 'string', description: 'the single research program (one line) that GENERATES these papers' },
  coheres: { type: 'boolean', description: 'do these papers genuinely cohere as ONE program?' },
  confidence: { type: 'string' }, note: { type: 'string' } },
  required: ['recovered', 'coheres', 'confidence'] }

const VERDICT = { type: 'object', properties: {
  closes: { type: 'boolean', description: 'does the blind-recovered generator match the stated one (the floor folds back up to it)?' },
  status: { type: 'string', description: 'closes | drifts | dead-end' },
  gap: { type: 'string', description: 'the residual: precisely what to ADD or REARRANGE so the up-fold reproduces the down-constraint' },
  severity: { type: 'string', description: 'none | minor | major' } },
  required: ['closes', 'status', 'gap', 'severity'] }

phase('Recover')
log(`closure-test: ${N} generators - blind up-recovery vs stated`)
const out = await pipeline(items,
  // UP: blind generator recovery - the agent reads ONLY the floors file (labels live elsewhere)
  (it) => agent(`You are a BLIND generator-recovery agent. Read ${FLOORS} (Read tool) and take the entry with idx=${it.idx}. Its "floor" is the CHILDREN of one node in a physicist's research ladder, shown WITHOUT the node's label - either papers (RESULTS + TECHNIQUE handles) or child-node essences (the entry's "kind" says which). You are NOT told what the node is (the label is not in this file).
Fold the children UP: what is the SINGLE program/operator (one line) that would GENERATE them - the thing that, run forward, produces exactly these children? And do they genuinely cohere as ONE program, or is this two things stapled together?
Return via StructuredOutput.`,
    { label: `recover:${it.idx}`, model: 'sonnet', schema: RECOVERED, phase: 'Recover' })
    .then(r => ({ idx: it.idx, recovered: r })).catch(() => null),
  // compare blind-recovered vs the stated label (judge reads the labels file; recoverer never did)
  (rr) => {
    if (!rr) return null
    return agent(`You are the CLOSURE ADJUDICATOR. Frame: DOWN = the constraint, UP = the generator; a cluster is a FIXED POINT when the generator recovered by folding its floor UP reproduces the program the descent assigned.
Read ${LABELS} (Read tool), entry idx=${rr.idx}: that is the STATED generator (and its rationale) the descent assigned.
The BLIND-RECOVERED generator (folded up from the floor alone, by an agent that never saw the label) is: "${rr.recovered.recovered}" (coheres=${rr.recovered.coheres}, confidence=${rr.recovered.confidence}).
Judge: does it CLOSE (recovered reproduces stated => route runs both ways, a fixed point), DRIFT (recovers a real but DIFFERENT/narrower/broader program => the label is off), or DEAD-END (cannot recover / does not cohere => no single operator under the label)?
Give the GAP: precisely what to ADD or REARRANGE so the up-fold reproduces the down-constraint (split the generator, rename it, move papers between clusters, collapse duplicate version-twins, add a missing mid-grade).
Return via StructuredOutput.`,
      { label: `judge:${rr.idx}`, model: 'sonnet', schema: VERDICT, phase: 'Adjudicate' })
      .then(v => ({ idx: rr.idx, recovered: rr.recovered.recovered, coheres: rr.recovered.coheres, ...v }))
      .catch(() => null)
  }
)
return { tested: N, results: out.filter(Boolean) }
