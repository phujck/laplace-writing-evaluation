import { bindDispatchAgent } from './dispatch_gate.mjs'
agent = bindDispatchAgent(agent, () => args?.dispatchAdmissions ?? globalThis.dispatchAdmissions)

export const meta = {
  name: 'people-sweep',
  description: 'Promote the waiting chat partners: per person, Haiku floors distil window batches; a Sonnet keeper folds and WRITES the sealed entity (trait/event/who, locator law) + the gerard sidecar, returning COUNTS ONLY (the N33 seal posture: content lands on disk inside the sealed agent, never in the orchestrator).',
  phases: [
    { title: 'Floor', detail: 'Haiku distils batches of ~8 windows into a partial' },
    { title: 'Fold', detail: 'Sonnet folds partials, writes the sealed files, returns counts' },
  ],
}

let A = args
if (typeof A === 'string') { try { A = JSON.parse(A) } catch (e) { A = {} } }
A = A || {}
const PEOPLE = A.people || []
const BASE = 'C:/Users/gerar/VScodeProjects/laplace'
const OUT = `${BASE}/archive/soul_dump/_shard/sweep_folded`
const K = A.k || 8

const SEAL = 'SEAL (non-negotiable): never quote or copy any source text; paraphrase everything; output contains NO verbatim sentences/phrases, not even short ones - if you reach for quotation marks around source words, paraphrase instead; locators are window-file + line-ranges only, never content.'

const VOICE_I = { type: 'object', properties: { trait: { type: 'string' }, note: { type: 'string' }, locator: { type: 'string' } }, required: ['trait', 'locator'] }
const HIST_I = { type: 'object', properties: { event: { type: 'string' }, note: { type: 'string' }, locator: { type: 'string' }, confidence: { type: 'string' } }, required: ['event', 'locator', 'confidence'] }
const REL_I = { type: 'object', properties: { who: { type: 'string' }, note: { type: 'string' }, locator: { type: 'string' } }, required: ['who', 'note'] }
const GEN_I = { type: 'object', properties: { primitive: { type: 'string' }, statement: { type: 'string' }, locator: { type: 'string' }, confidence: { type: 'string' } }, required: ['primitive', 'statement', 'confidence'] }
const PARTY = { type: 'object', properties: { name: { type: 'string' }, voice: { type: 'array', items: VOICE_I }, history: { type: 'array', items: HIST_I }, relations: { type: 'array', items: REL_I } }, required: ['name', 'voice', 'history', 'relations'] }
const FLOOR_SCHEMA = {
  type: 'object',
  properties: {
    person: { type: 'string' },
    partner: PARTY,
    gerard: { type: 'object', properties: { voice: { type: 'array', items: VOICE_I }, history: { type: 'array', items: HIST_I }, relations: { type: 'array', items: REL_I }, generator: { type: 'array', items: GEN_I } }, required: ['voice', 'history', 'relations', 'generator'] },
  },
  required: ['person', 'partner', 'gerard'],
}
const COUNTS = {
  type: 'object',
  properties: {
    name: { type: 'string' }, n_voice: { type: 'number' }, n_history: { type: 'number' },
    n_relations: { type: 'number' }, n_with_locator: { type: 'number' },
    wrote: { type: 'array', items: { type: 'string' } },
  },
  required: ['name', 'n_voice', 'n_history', 'n_relations', 'n_with_locator', 'wrote'],
}

function floorPrompt(p, files) {
  const list = files.map(f => `${p.dir}/${f}`).join('\n')
  return `You are a sealed distiller-keeper in the Laplace soul-ingest pipeline. You read a BATCH of consecutive windows of ONE private WhatsApp 1:1 conversation between Gerard (the author) and ${p.person}, and return a consolidated relational partial for this batch.
${SEAL}
Read each of these files (Read tool), in order:
${list}
They are WhatsApp export windows (format: [DD/MM/YYYY, HH:MM:SS] Sender: message). Consolidate ACROSS the batch (dedup repeated facts; keep specific detail - history-rich is the core demand). Locator format: "<window file name>:lines a-b". Produce:
- partner: ${p.person}'s consolidated entity slice - {name:"${p.person}", voice (2-8 items {trait (paraphrased), note?, locator}), history (rich, paraphrased {event, note?, locator, confidence: high|med|low} - mark uncertain/one-off "low"), relations ({who, note, locator?})}.
- gerard: Gerard's atoms from this batch - {voice, history (his facts/plans/projects revealed here), relations, generator (his taste/judgment in HIS turns: {primitive: stance|move|value|aesthetic|friction, statement (paraphrased), locator?, confidence})}.
Invent nothing. Return via StructuredOutput {person, partner, gerard}.`
}

function foldPrompt(p, partials, gerardParts) {
  return `You are a sealed per-person KEEPER. You receive consolidated partials for ONE person (${p.person}) across batches of their WhatsApp conversation with Gerard. Fold them into ONE entity and WRITE it to disk yourself - the orchestrator must never hold the content (only your counts rise).
${SEAL} (inputs are already paraphrased; keep it so.)
Fold rules: dedup voice (keep characteristic traits, dict-shaped {trait, note?, locator}); MERGE history into a rich, de-duplicated, roughly chronological set - PRESERVE specific facts, never summarise them away ({event, note?, locator, confidence}); union relations ({who, note, locator?}); carry low-confidence items forward (never drop); every item carries its locator where one exists (the locator law - a missing locator is an honest null, never an invented one). Invent nothing.
Then, with the Write tool:
1. Write the entity JSON to ${OUT}/${p.stem}.json with EXACTLY this shape: {"name": "${p.person}", "is_author": false, "summary": "<2-3 sentence paraphrased portrait>", "voice": [...], "history": [...], "relations": [...]}.
2. Write the Gerard sidecar (his atoms from this conversation, merged across the batches below, same item shapes, NO "name" key) to ${OUT}/_gerard/${p.stem}.json as {"is_author_sidecar": true, "person": "${p.person}", "voice": [...], "history": [...], "relations": [...], "generator": [...]}.
Finally return ONLY counts via StructuredOutput: {name, n_voice, n_history, n_relations, n_with_locator, wrote: [the two paths]}.
PARTNER PARTIALS (one per batch):
${JSON.stringify(partials)}
GERARD PARTIALS (one per batch):
${JSON.stringify(gerardParts)}`
}

// ---- run: people sequential (readable progress), floors parallel within each ----
const results = []
for (const p of PEOPLE) {
  const files = Array.from({ length: p.count }, (_, i) => `${p.prefix}_${i}.txt`)
  const batches = []
  for (let i = 0; i < files.length; i += K) batches.push(files.slice(i, i + K))
  log(`${p.person}: ${files.length} windows -> ${batches.length} floor batches`)
  const floor = (await parallel(batches.map((b, i) => () =>
    agent(floorPrompt(p, b), { label: `distil:${p.stem}#${i}`, model: 'haiku', phase: 'Floor', schema: FLOOR_SCHEMA }).catch(() => null)
  ))).filter(Boolean)
  const partials = floor.map(f => f.partner).filter(Boolean)
  const gerardParts = floor.map(f => f.gerard).filter(Boolean)
  if (!partials.length) { results.push({ person: p.person, error: 'no floor partials recovered' }); continue }
  try {
    const counts = await agent(foldPrompt(p, partials, gerardParts),
      { label: `fold:${p.stem}`, model: 'sonnet', phase: 'Fold', schema: COUNTS })
    results.push({ person: p.person, windows: files.length, floors: floor.length, counts })
    log(`${p.person}: folded - ${counts ? counts.n_voice + 'v/' + counts.n_history + 'h/' + counts.n_relations + 'r' : 'null'}`)
  } catch (e) {
    results.push({ person: p.person, error: 'fold failed: ' + (e && e.message) })
  }
}
return results
