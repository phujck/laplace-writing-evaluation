import { bindDispatchAgent } from './dispatch_gate.mjs'
agent = bindDispatchAgent(agent, () => args?.dispatchAdmissions ?? globalThis.dispatchAdmissions)

export const meta = {
  name: 'structural-shard',
  description: 'The top-down structural shard (his architecture 2026-06-11): shard papers by their OWN argumentative structure - a power-law descent from generality to specificity (meta-goal -> approach -> techniques -> results) - instead of atomising semantically and trying to backfill the middle by clustering. The grade ladder is built BY CONSTRUCTION (the paper already has it) rather than discovered. Two stages, conjugate: SHARD (deterministic lens - the SAME structural schema for every paper, intelligence paid once at fold) lays the substrate top-down; UPFOLD cross-links the same-kind pieces across papers (all meta-goals -> the research PROGRAM, the generators that surface as top-level lenses; all techniques -> the shared-method web). Ingestion provides the substrate through deterministic lenses; upfolding re-correlates the individually-decomposed entities so the generator underneath surfaces above. Run on the author McCaul first.',
  phases: [
    { title: 'Shard', detail: 'deterministic structural lens: each paper -> goal/approach/techniques/results ladder', model: 'haiku' },
    { title: 'Upfold', detail: 'cross-link across papers: meta-goals -> the research program (top lenses); techniques -> shared-method web', model: 'sonnet' },
  ],
}

let A = args
if (typeof A === 'string') { try { A = JSON.parse(A) } catch (e) { A = {} } }
A = A || {}
const KEY = A.key || 'mccaul'
const NAME = A.name || 'Gerard McCaul'
const WORKS_FILE = A.worksFile || `collaborator_corpus/_raw/${KEY}_works.json`
const N_WORKS = A.nWorks || 0
const PER_BATCH = A.perBatch || 8       // papers one shard agent reads (title+abstract ~ small)

// the DETERMINISTIC structural lens - the SAME schema for every paper (general -> specific).
// the grade axis is structural (universal); the content is emergent (per-paper). recursion
// (a technique with sub-techniques) is where full text would deepen the floor; abstracts give
// the top of the ladder, which is the part that has been missing (the cliff's empty middle).
const LADDER = {
  type: 'object',
  properties: {
    id: { type: 'string', description: 'OpenAlex short id (W...) + year' },
    title: { type: 'string' },
    meta_goal: { type: 'string', description: 'g-top: the highest aim - what problem in the field/world this paper exists to move. ONE line, general.' },
    approach: { type: 'string', description: 'g-mid: the general strategy by which it pursues the goal (the framing/idea, not yet the method)' },
    techniques: { type: 'array', items: { type: 'object', properties: {
      name: { type: 'string', description: 'kebab-case method handle' },
      statement: { type: 'string', description: 'the specific technique/move' } }, required: ['name', 'statement'] } },
    results: { type: 'array', items: { type: 'object', properties: {
      claim: { type: 'string', description: 'a specific finding/result/claim - the floor, the most specific' } }, required: ['claim'] } },
  },
  required: ['id', 'title', 'meta_goal', 'approach', 'techniques', 'results'],
}
const SHARD = { type: 'object', properties: { ladders: { type: 'array', items: LADDER } }, required: ['ladders'] }

const UPFOLD = {
  type: 'object',
  properties: {
    program: { type: 'array', items: { type: 'object', properties: {
      generator: { type: 'string', description: 'a recurring meta-goal across the papers - a top-level GENERATOR of his research program' },
      why: { type: 'string' },
      papers: { type: 'array', items: { type: 'string', description: 'the W... ids whose meta_goal rolls up here' } } },
      required: ['generator', 'why', 'papers'] } },
    technique_clusters: { type: 'array', items: { type: 'object', properties: {
      technique: { type: 'string', description: 'a method recurring across papers (the shared-method web)' },
      papers: { type: 'array', items: { type: 'string' } } },
      required: ['technique', 'papers'] } },
    note: { type: 'string', description: 'one line: does the program cohere, and how many generators surfaced' },
  },
  required: ['program', 'technique_clusters', 'note'],
}

const WHAT = `Shard each paper TOP-DOWN by its OWN argumentative structure - a descent from GENERALITY to SPECIFICITY:
- meta_goal (most general): the highest aim - what problem in the field this paper exists to move. One line.
- approach: the general strategy/framing that pursues the goal (still general - the idea, not the method).
- techniques: the specific methods/moves used (more specific).
- results: the specific findings/claims (most specific - the floor).
This is NOT a semantic summary and NOT a bag of topics - it is the paper's own GOAL->METHOD->RESULT ladder. The same structural schema for EVERY paper (deterministic); only the content differs. Invent nothing; read it off the title+abstract.`

function batches(n, k) { const out = []; for (let i = 0; i < n; i += k) out.push([i, Math.min(i + k, n)]); return out }

// ---- Shard: the deterministic structural lens, parallel over batches ----
phase('Shard')
const ranges = batches(N_WORKS, PER_BATCH)
log(`structural-shard: ${NAME} <- ${N_WORKS} papers in ${ranges.length} batches`)
const ladders = (await parallel(ranges.map(([a, b], i) => () =>
  agent(`You are a STRUCTURAL SHARDER for ${NAME}'s papers. Read the JSON file ${WORKS_FILE} (Read tool) and consider ONLY works[${a}..${b}) (0-indexed slice of the top-level array; each has title/abstract/year/id). ${WHAT}
Return one ladder per paper in YOUR slice via StructuredOutput {ladders:[...]}.`,
    { label: `shard:${KEY}.${i}`, model: 'haiku', schema: SHARD, phase: 'Shard' }).catch(() => null)
))).filter(Boolean).flatMap(r => r.ladders || [])
log(`sharded: ${ladders.length} paper ladders`)

// ---- Upfold: cross-link the same-kind pieces across papers (the generator surfaces above) ----
phase('Upfold')
// feed the upfold only the GENERAL layers (goal+approach+technique names) - the cross-link is
// at generality, the specifics stay below (descend to recover). bounded input.
const general = ladders.map(l => ({ id: l.id, goal: l.meta_goal, approach: l.approach,
  techniques: (l.techniques || []).map(t => t.name) }))
const upfold = await agent(`You are the UPFOLD for ${NAME}'s research corpus. You receive the GENERAL layer of every paper's structural ladder (its meta-goal, approach, technique handles). CROSS-LINK them:
1. program: cluster the meta-goals into the few recurring GENERATORS of his research program - the top-level lenses his whole corpus descends from. Each generator rolls up the papers (ids) whose goal belongs to it. Aim for the smallest set that covers the corpus (his program has FEW generators, many papers).
2. technique_clusters: the methods that recur across papers (the shared-method web the dream would wire).
This is the conjugate of the shard: the shard split each paper top-down; the upfold re-correlates them so the generator UNDERNEATH surfaces ABOVE. Invent nothing - cluster only what is there.
THE GENERAL LAYER (${general.length} papers):
${JSON.stringify(general)}
Return via StructuredOutput.`,
  { label: `upfold:${KEY}`, model: 'sonnet', schema: UPFOLD, phase: 'Upfold' })

return { key: KEY, name: NAME, n_papers: ladders.length, ladders, upfold }
