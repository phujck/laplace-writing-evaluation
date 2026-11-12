import { bindDispatchAgent } from './dispatch_gate.mjs'
agent = bindDispatchAgent(agent, () => args?.dispatchAdmissions ?? globalThis.dispatchAdmissions)

export const meta = {
  name: 'soul-one-person',
  description: 'Gated single-person distil-fold for the tranche-1 soul pour: fill ONE person\'s gap (e.g. Will Handley 0/63) in a small, ceiling-safe run. Each Haiku floor agent distil-folds a BATCH of ~8 consecutive windows of the one 1:1 conversation; one Sonnet keeper folds the partials into the person\'s entity, carrying Gerard\'s atoms forward for the later tranche-wide apex. No resolve/adjudicate here (those are tranche-wide gates). Agent count = ceil(N/k) + 1, kept far under the per-run ceiling. Seal: agents read sealed shard files; the orchestrator holds only paraphrased distillate; no verbatim content.',
  phases: [
    { title: 'Floor', detail: 'Haiku distil-folds a batch of ~8 windows -> a partial' },
    { title: 'Fold', detail: 'Sonnet keeper folds the partials into one entity' },
  ],
}

let A = args
if (typeof A === 'string') { try { A = JSON.parse(A) } catch (e) { A = {} } }
A = A || {}
const DIR = A.dir || 'archive/soul_dump/_shard/scaled_tranche1'
const PERSON = A.person || 'Unknown'
const K = A.k || 8
const START = A.start || 0  // window-slice offset: a giant too big for one ceiling-safe run is poured in slices [start, start+count)
// File list: explicit `files`, else generated from `prefix` + `count` (+ `start` offset; window i -> `${prefix}_${start+i}.txt`)
const FILES = (A.files && A.files.length) ? A.files
  : (A.prefix && A.count) ? Array.from({ length: A.count }, (_, i) => `${A.prefix}_${START + i}.txt`)
  : []
log(`args: type=${typeof args} person=${PERSON} files=${FILES.length} start=${START} (prefix=${A.prefix ? 'yes' : 'no'})`)
const nick = (p) => p.replace(/WhatsApp Chat with /, '').replace(/\.txt$/, '')

const HIST = { type: 'object', properties: { fact: { type: 'string' }, locator: { type: 'string' }, confidence: { type: 'string' } }, required: ['fact', 'locator', 'confidence'] }
const REL = { type: 'object', properties: { with: { type: 'string' }, nature: { type: 'string' } }, required: ['with', 'nature'] }
const GEN = { type: 'object', properties: { primitive: { type: 'string' }, statement: { type: 'string' }, confidence: { type: 'string' } }, required: ['primitive', 'statement', 'confidence'] }
const PARTY = { type: 'object', properties: { name: { type: 'string' }, voice: { type: 'array', items: { type: 'string' } }, history: { type: 'array', items: HIST }, relations: { type: 'array', items: REL } }, required: ['name', 'voice', 'history', 'relations'] }
const FLOOR_SCHEMA = {
  type: 'object',
  properties: {
    person: { type: 'string' },
    partner: PARTY,
    gerard: { type: 'object', properties: { voice: { type: 'array', items: { type: 'string' } }, history: { type: 'array', items: HIST }, relations: { type: 'array', items: REL }, generator: { type: 'array', items: GEN } }, required: ['voice', 'history', 'relations', 'generator'] },
  },
  required: ['person', 'partner', 'gerard'],
}
const ENTITY = { type: 'object', properties: { name: { type: 'string' }, is_author: { type: 'boolean' }, voice: { type: 'array', items: { type: 'string' } }, history: { type: 'array', items: HIST }, relations: { type: 'array', items: REL }, generator: { type: 'array', items: GEN } }, required: ['name', 'is_author', 'voice', 'history', 'relations'] }

const SEAL = 'SEAL (non-negotiable): never quote or copy any source text; paraphrase everything; output contains NO verbatim sentences/phrases, not even short ones - if you reach for quotation marks around source words, paraphrase instead; locators are line-ranges only, never content.'

function floorPrompt(files) {
  const person = nick(PERSON)
  const list = files.map(f => `${DIR}/${f}`).join('\n')
  return `You are a sealed distiller-keeper in the Laplace soul-ingest pipeline. You read a BATCH of consecutive windows of ONE private WhatsApp 1:1 conversation between Gerard (the author) and ${person}, and return a consolidated relational partial for this batch.
${SEAL}
Read each of these files (Read tool), in order:
${list}
They are WhatsApp export windows (format: [DD/MM/YYYY, HH:MM:SS] Sender: message). Consolidate ACROSS the batch (dedup repeated facts; keep specific detail - history-rich is the core demand). Produce:
- partner: ${person}'s consolidated entity - {name:"${person}", voice (2-8 paraphrased traits), history (rich, paraphrased {fact, locator:"<file>:lines a-b", confidence: high|med|low} - mark uncertain/one-off "low"), relations ({with, nature})}.
- gerard: Gerard's atoms from this batch - {voice, history (his facts/plans/projects revealed here), relations, generator (his taste/judgment in HIS turns: {primitive: stance|move|value|aesthetic|friction, statement (paraphrased), confidence})}.
Invent nothing. Return via StructuredOutput {person, partner, gerard}.`
}

function foldPrompt(partials) {
  return `You are a sealed per-person KEEPER. You receive consolidated partials for ONE person (${nick(PERSON)}) across batches of their WhatsApp conversation with Gerard. Fold into ONE entity.
${SEAL} (inputs are already paraphrased; keep it so.)
Rules: dedup voice (keep characteristic traits); MERGE history into a rich, de-duplicated, roughly chronological set - PRESERVE specific facts, do not summarise them away; union relations; carry low-confidence items forward as conjectural (never drop). Invent nothing.
PARTIALS (each a partner-partial from one batch):
${JSON.stringify(partials)}
Return ONE entity via StructuredOutput: {name:"${nick(PERSON)}", is_author:false, voice[], history[], relations[]}.`
}

// ---- run ----
const batches = []
for (let i = 0; i < FILES.length; i += K) batches.push(FILES.slice(i, i + K))
log(`${nick(PERSON)}: ${FILES.length} windows -> ${batches.length} distil-fold batches (K=${K})`)

phase('Floor')
const floor = (await parallel(batches.map((b, i) => () =>
  agent(floorPrompt(b), { label: `distil:${nick(PERSON)}#${i}`, model: 'haiku', phase: 'Floor', schema: FLOOR_SCHEMA }).catch(() => null)
))).filter(Boolean)
log(`floor: ${floor.length}/${batches.length} batches recovered`)

const partials = floor.map(p => p.partner).filter(Boolean)
const gerardParts = floor.map(p => p.gerard).filter(Boolean)

phase('Fold')
const entity = await agent(foldPrompt(partials), { label: `fold:${nick(PERSON)}`, model: 'sonnet', phase: 'Fold', schema: ENTITY })

return { person: nick(PERSON), n_windows: FILES.length, n_batches: batches.length, n_floor: floor.length, entity, gerardParts }
