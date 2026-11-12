import { bindDispatchAgent } from './dispatch_gate.mjs'
agent = bindDispatchAgent(agent, () => args?.dispatchAdmissions ?? globalThis.dispatchAdmissions)

export const meta = {
  name: 'refine-essences',
  description: 'Round-2 of the insert-middle loop: apply the closure gate\'s residuals (mccaul_closure_v2.json) to the drifting nodes. The drift KIND changed between rounds - round 1 residuals were MISSING MID-GRADES (structural), round 2 residuals are ESSENCE PRECISION (directionality, named deliverables, scope clauses, boundary sharpening) plus ONE recovered structural insert (superoscillations wants its two sub-floors promoted to rungs - the gate finding the NEXT missing middle inside a closing node; the loop never terminates). Each agent implements its node\'s gap verbatim, keeping the response-function contract: what the node IS at its grade / what a goal arriving pulls below, under what conditions / what it returns upward. Minimal AND sufficient.',
  phases: [
    { title: 'Refine', detail: 'per drifting node: rewrite the essence to the gap spec; superoscillations: promote the two sub-floors to rungs', model: 'sonnet' },
  ],
}

const VERDICTS = 'collaborator_corpus/_structural/mccaul_closure_v2.json'
const LABELS = 'collaborator_corpus/_structural/_closure_labels_v2.json'
const REGRADED = 'collaborator_corpus/_structural/mccaul_regraded.json'
const STRUCT = 'collaborator_corpus/_structural/mccaul.json'

// the 8 drifting nodes + the 1 structural promotion the gate recovered inside a closer
const NODES = [
  { idx: 0, key: 'kvn-operator-route', kind: 'essence' },
  { idx: 3, key: 'forward-prescriptive-control', kind: 'essence' },
  { idx: 5, key: 'imaginary-time-to-unitary-mapping', kind: 'essence' },
  { idx: 9, key: 'photonic-feature-space-ml', kind: 'essence' },
  { idx: 10, key: 'gen-unification', kind: 'essence' },
  { idx: 11, key: 'gen-open-quantum-systems', kind: 'essence' },
  { idx: 12, key: 'gen-laser-control', kind: 'essence' },
  { idx: 15, key: 'gen-reservoir-ml', kind: 'essence' },
  { idx: 13, key: 'gen-superoscillations-promote', kind: 'promote' },
]

const REFINED = { type: 'object', properties: {
  idx: { type: 'integer' },
  new_essence: { type: 'string', description: 'the rewritten response-function essence implementing the gap EXACTLY: (a) what this node IS at its grade, (b) what a goal arriving here pulls below + under what conditions, (c) what it returns upward. Minimal (shorter than its floor) and sufficient (a blind reader re-derives the children).' },
  rungs: { type: 'array', items: { type: 'object', properties: {
    name: { type: 'string' }, essence: { type: 'string' },
    papers: { type: 'array', items: { type: 'string' } } },
    required: ['name', 'essence', 'papers'] },
    description: 'ONLY for the promote node: the two sub-floors promoted to rungs, every member paper assigned to exactly one.' },
  note: { type: 'string' } },
  required: ['idx', 'new_essence', 'rungs', 'note'] }

phase('Refine')
log(`refine-essences: ${NODES.length} nodes (8 essence rewrites + 1 rung promotion)`)
const out = await parallel(NODES.map(n => () =>
  agent(`You are the ESSENCE REFINER for ONE node of Gerard McCaul's regraded structural ladder.
Read ${VERDICTS} (Read tool): in "results", find the entry with idx=${n.idx}. Its "gap" is the closure adjudicator's residual - the precise spec of what the stated essence must ADD, REMOVE, or REARRANGE so a blind up-fold reproduces it. Read ${LABELS}: the entry with idx=${n.idx} holds the CURRENT stated essence ("stated").
${n.kind === 'promote'
  ? `MODE = PROMOTE (this node CLOSED but its gap recovered an internal structure): rewrite the generator essence AND promote its two named sub-floors (waveform-generation/phase-optimisation; deployment) to explicit rungs with pull-conditions and upward returns. Read ${REGRADED} for the generator's member papers and ${STRUCT} ladders for their content; assign EVERY member paper to exactly one rung. Also execute the gap's floor audit (attosecond/HHG/quantum-field-control papers): report the finding in note - do not move papers across generators.`
  : `MODE = ESSENCE: rewrite the stated essence implementing the gap EXACTLY - neither more nor less. Structure stays as is (no rungs, no paper moves); rungs MUST be [].`}
KEEP THE RESPONSE-FUNCTION CONTRACT: (a) what the node IS at its grade, (b) what a goal arriving here pulls below + when, (c) what returns upward. Minimal and sufficient. Invent nothing.
Return via StructuredOutput with idx=${n.idx}.`,
    { label: `refine:${n.key}`, model: 'sonnet', schema: REFINED, phase: 'Refine' })
    .catch(() => null)
))
const ok = out.filter(Boolean)
log(`refined: ${ok.length}/${NODES.length}`)
return { refined: ok }
