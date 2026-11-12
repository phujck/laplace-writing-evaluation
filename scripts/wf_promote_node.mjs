import { bindDispatchAgent } from './dispatch_gate.mjs'
agent = bindDispatchAgent(agent, () => args?.dispatchAdmissions ?? globalThis.dispatchAdmissions)

export const meta = {
  name: 'promote-node',
  description: 'Materialise the missing middle inside ONE flat (enrich-mode) generator: the closure gate found its essence describes internal structure (branches/envelope) that its floor does not carry as rungs - the same fix-type as the superoscillations promotion. One agent reads the gate verdict + the ladders, promotes the named branches to rungs with response-function essences, and assigns every member paper to exactly one rung.',
  phases: [
    { title: 'Promote', detail: 'one generator: branches -> rungs with essences + exhaustive paper assignment', model: 'sonnet' },
  ],
}

let A = args
if (typeof A === 'string') { try { A = JSON.parse(A) } catch (e) { A = {} } }
A = A || {}
const VERDICTS = A.verdictsFile || 'collaborator_corpus/_structural/mccaul_closure_v3.json'
const VIDX = A.verdictIdx === undefined ? 7 : A.verdictIdx
const GEN = A.generator || 'Open quantum systems: exact dynamics from equilibrated initial states'
const REGRADED = A.regradedFile || 'collaborator_corpus/_structural/mccaul_regraded.json'
const STRUCT = A.structFile || 'collaborator_corpus/_structural/mccaul.json'

const PROMOTED = { type: 'object', properties: {
  generator_essence: { type: 'string', description: 'the generator response-function essence, rewritten so its pull-clauses route to the NEW rungs by name: (a) what the programme IS, (b) which rung a goal pulls + when, (c) what returns upward.' },
  rungs: { type: 'array', items: { type: 'object', properties: {
    name: { type: 'string', description: 'kebab-case rung handle' },
    essence: { type: 'string', description: 'the rung response-function essence: what it IS / what a goal arriving pulls below + when / what returns upward. Minimal and sufficient.' },
    papers: { type: 'array', items: { type: 'string', description: 'W... ids; EVERY member paper of the generator assigned to exactly ONE rung' } } },
    required: ['name', 'essence', 'papers'] } },
  note: { type: 'string' } },
  required: ['generator_essence', 'rungs', 'note'] }

phase('Promote')
log(`promote-node: ${GEN}`)
const out = await agent(`You are the MIDDLE-PROMOTER for ONE flat generator of Gerard McCaul's structural ladder: "${GEN}".
Read ${VERDICTS} (Read tool): in "results", the entry with idx=${VIDX} is the closure gate's verdict on this generator. Its "gap" names the internal structure the essence claims but the floor does not materialise - implement that spec EXACTLY: promote the named branches (and the envelope/linking node, if the gap names one) to explicit RUNGS.
Read ${REGRADED}: find the generator with label "${GEN}" - its "papers" array is the member list. Read ${STRUCT}: ladders[] holds each paper's goal/approach/techniques/results. Work only from these files; invent nothing.
Emit: (1) a rewritten generator essence whose pull-clauses route to the new rungs BY NAME; (2) one response-function essence per rung - (a) what it IS at its grade, (b) what a goal arriving pulls below + under what conditions, (c) what returns upward; minimal (shorter than its floor) and sufficient (a blind reader re-derives the children). (3) EVERY member paper assigned to exactly ONE rung (a linking/envelope paper goes in the rung whose role it carries, named as such in that rung's essence).
Return via StructuredOutput.`,
  { label: 'promote:open-quantum-systems', model: 'sonnet', schema: PROMOTED, phase: 'Promote' })
return { generator: GEN, ...out }
