import { bindDispatchAgent } from './dispatch_gate.mjs'
agent = bindDispatchAgent(agent, () => args?.dispatchAdmissions ?? globalThis.dispatchAdmissions)

export const meta = {
  name: 'upfold-only',
  description: 'Re-run ONLY the upfold stage of the structural shard from an extracted general layer (ladders already paid for - never re-shard to re-cluster). Born 2026-06-11 from the alanissila friction: a 400-paper corpus upfolded to 4 generators (213 under one node). v1 of this script told the agent to re-read the 466KB shard through tool calls; it gave up partway and FABRICATED 283/300 member ids - caught by mechanical set membership at zero cost. v2: the agent reads a compact INDEXED general-layer .jsonl (no ids in it at all) and returns INTEGER INDICES; the id mapping stays mechanical in the save step. The model writes cluster structure; the mechanics own the identifiers. Args: {key, name, n, branchingNote}.',
  phases: [
    { title: 'Upfold', detail: 'cross-link the indexed general layers into the research program (top lenses)', model: 'sonnet' },
  ],
}

let A = args
if (typeof A === 'string') { try { A = JSON.parse(A) } catch (e) { A = {} } }
A = A || {}
const KEY = A.key
const NAME = A.name || KEY
const N = A.n
const GENERAL_FILE = A.generalFile || `collaborator_corpus/_structural/_general_${KEY}.jsonl`
const NOTE = A.branchingNote || ''

const UPFOLD = {
  type: 'object',
  properties: {
    program: { type: 'array', items: { type: 'object', properties: {
      generator: { type: 'string', description: 'a recurring meta-goal across the papers - a top-level GENERATOR of the research program' },
      why: { type: 'string' },
      papers: { type: 'array', items: { type: 'integer', description: 'the "i" index values (integers) of the papers whose meta_goal rolls up here - indices into the general-layer file, NEVER invented' } } },
      required: ['generator', 'why', 'papers'] } },
    technique_clusters: { type: 'array', items: { type: 'object', properties: {
      technique: { type: 'string', description: 'a method recurring across papers (the shared-method web)' },
      papers: { type: 'array', items: { type: 'integer', description: 'the "i" index values of the papers sharing this technique' } } },
      required: ['technique', 'papers'] } },
    note: { type: 'string', description: 'one line: does the program cohere, and how many generators surfaced' },
  },
  required: ['program', 'technique_clusters', 'note'],
}

phase('Upfold')
log(`upfold-only v2: ${NAME} <- ${GENERAL_FILE} (${N} indexed entries)`)
const upfold = await agent(`You are the UPFOLD for ${NAME}'s research corpus. Read ${GENERAL_FILE} (Read tool; ${N} lines, one JSON entry per line: {"i": <index>, "goal", "approach", "techniques"} - read ALL of it, it takes a few Read calls). These are the GENERAL layers of every paper's structural ladder. CROSS-LINK them:
1. program: cluster the meta-goals into the recurring GENERATORS of the research program - the top-level lenses the whole corpus descends from. Aim for the smallest set that covers the corpus - BUT respect the descent geometry: a generator is a node a reader can descend THROUGH, so no generator should swallow a third of the corpus. ${NOTE}
2. technique_clusters: the methods that recur across papers (the shared-method web).
Reference papers ONLY by their integer "i" index. Every index 0..${N - 1} appears in exactly one program entry. You never see or output paper ids - the index mapping is resolved mechanically afterwards.
Return via StructuredOutput.`,
  { label: `upfold:${KEY}`, model: 'sonnet', schema: UPFOLD, phase: 'Upfold' })

return { key: KEY, name: NAME, upfold }
