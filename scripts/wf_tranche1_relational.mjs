import { bindDispatchAgent } from './dispatch_gate.mjs'
agent = bindDispatchAgent(agent, () => args?.dispatchAdmissions ?? globalThis.dispatchAdmissions)

export const meta = {
  name: 'soul-tranche-world-scaled-t1',
  description: 'Scaled relational soul pour over a WhatsApp 1:1 tranche, ROBUST design: each Haiku floor agent distil-folds a BATCH of ~8 consecutive windows of one person (cuts ~332 lone agents to ~42, staying far under the per-run agent ceiling that stalled the monolithic version). Then a per-person Sonnet keeper fold, a Gerard apex fold, an Opus cross-person resolve (conservative, groups from real relations), and an Opus builder!=judge adjudication. Seal: agents read sealed shard files; the orchestrator holds only paraphrased distillate; no verbatim content.',
  phases: [
    { title: 'Index' },
    { title: 'Floor', detail: 'Haiku distil-folds a batch of ~8 windows of one person -> a partial' },
    { title: 'Fold', detail: 'per-person Sonnet keeper folds the partials into one entity' },
    { title: 'Apex', detail: 'fold Gerard\'s atoms across all batches into his hub entity + generator' },
    { title: 'Resolve', detail: 'Opus cross-person keeper: resolve conservative, group from relations', model: 'opus' },
    { title: 'Adjudicate', detail: 'Opus builder!=judge: faithful/partial/confab + seal + no-wrong-merge', model: 'opus' },
  ],
}

const DIR = (typeof args === 'object' && args && args.dir) ? args.dir : 'archive/soul_dump/_shard/scaled_tranche1'
const K = (typeof args === 'object' && args && args.k) ? args.k : 8
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
const MAP_SCHEMA = {
  type: 'object',
  properties: {
    entities: { type: 'array', items: { type: 'object', properties: { canonical_name: { type: 'string' }, merged_surface_names: { type: 'array', items: { type: 'string' } }, is_author: { type: 'boolean' }, voice: { type: 'array', items: { type: 'string' } }, history: { type: 'array', items: HIST }, relations: { type: 'array', items: REL } }, required: ['canonical_name', 'merged_surface_names', 'is_author', 'voice', 'history', 'relations'] } },
    groups: { type: 'array', items: { type: 'object', properties: { name: { type: 'string' }, members: { type: 'array', items: { type: 'string' } }, basis: { type: 'string' } }, required: ['name', 'members', 'basis'] } },
    author_generator: { type: 'array', items: GEN },
    conjectural: { type: 'array', items: { type: 'string' } },
    notes: { type: 'string' },
  },
  required: ['entities', 'groups', 'author_generator', 'conjectural', 'notes'],
}
const VERDICT_SCHEMA = {
  type: 'object',
  properties: { verdict: { type: 'string' }, faithful: { type: 'integer' }, partial: { type: 'integer' }, confabulated: { type: 'integer' }, seal_clean: { type: 'boolean' }, wrong_merges: { type: 'array', items: { type: 'string' } }, substrate_present: { type: 'boolean' }, history_rich: { type: 'boolean' }, flags: { type: 'array', items: { type: 'string' } }, summary: { type: 'string' } },
  required: ['verdict', 'faithful', 'partial', 'confabulated', 'seal_clean', 'wrong_merges', 'substrate_present', 'history_rich', 'flags', 'summary'],
}

const SEAL = 'SEAL (non-negotiable): never quote or copy any source text; paraphrase everything; output contains NO verbatim sentences/phrases, not even short ones - if you reach for quotation marks around source words, paraphrase instead; locators are line-ranges only, never content.'

function floorPrompt(b) {
  const person = nick(b.person)
  const list = b.files.map(f => `${DIR}/${f}`).join('\n')
  return `You are a sealed distiller-keeper in the Laplace soul-ingest pipeline. You read a BATCH of consecutive windows of ONE private WhatsApp 1:1 conversation between Gerard (the author) and ${person}, and return a consolidated relational partial for this batch.
${SEAL}
Read each of these files (Read tool), in order:
${list}
They are WhatsApp export windows (format: [DD/MM/YYYY, HH:MM:SS] Sender: message). Consolidate ACROSS the batch (dedup repeated facts; keep specific detail - history-rich is the core demand). Produce:
- partner: ${person}'s consolidated entity - {name:"${person}", voice (2-8 paraphrased traits), history (rich, paraphrased {fact, locator:"<file>:lines a-b", confidence: high|med|low} - mark uncertain/one-off "low"), relations ({with, nature})}.
- gerard: Gerard's atoms from this batch - {voice, history (his facts/plans/projects revealed here), relations, generator (his taste/judgment in HIS turns: {primitive: stance|move|value|aesthetic|friction, statement (paraphrased), confidence})}.
Invent nothing. Return via StructuredOutput {person, partner, gerard}.`
}

function foldPrompt(person, partials) {
  return `You are a sealed per-person KEEPER. You receive consolidated partials for ONE person (${nick(person)}) across batches of their WhatsApp conversation with Gerard. Fold into ONE entity.
${SEAL} (inputs are already paraphrased; keep it so.)
Rules: dedup voice (keep characteristic traits); MERGE history into a rich, de-duplicated, roughly chronological set - PRESERVE specific facts, do not summarise them away; union relations; carry low-confidence items forward as conjectural (never drop). Invent nothing.
PARTIALS (each a partner-partial from one batch):
${JSON.stringify(partials)}
Return ONE entity via StructuredOutput: {name:"${nick(person)}", is_author:false, voice[], history[], relations[]}.`
}

function apexPrompt(gerardParts) {
  return `You are a sealed KEEPER consolidating GERARD's apex entity from atoms harvested across every batch of his WhatsApp relational world.
${SEAL}
Fold into: his consolidated voice; his history (dedup, rich, the facts/plans/projects across relationships); the relations he holds; and his GENERATOR - consolidate the taste/judgment atoms into a small coherent set of his primitives (preserve his actual stance/move/value/aesthetic/friction; impose no template). Carry low-confidence as conjectural. Invent nothing.
GERARD ATOMS (across batches):
${JSON.stringify(gerardParts)}
Return ONE entity via StructuredOutput: {name:"Gerard", is_author:true, voice[], history[], relations[], generator[]}.`
}

function resolvePrompt(personEntities, gerard) {
  return `You are the sealed cross-person KEEPER (the upward operator at the relational grade). You receive the folded person-entities of tranche-1 of Gerard's relational world (his WhatsApp 1:1s) and Gerard's own apex entity. Build the grade-2 relational map.
${SEAL}
RULES (a wrong merge corrupts where a miss recovers):
- Resolve entities CONSERVATIVELY: merge two surface-names only when the atoms clearly establish them as the same person; when uncertain, keep SPLIT and say so. Record merged_surface_names.
- Gerard is the network HUB (is_author:true) - carry his consolidated entity.
- Derive grade-2 GROUPS ONLY from the actual relations present (e.g. a family circle, a research/collaborator circle); invent NO group/membership the relations don't support; state each group's basis.
- Consolidate Gerard's generator into a small coherent set of his primitives (preserve his actual taste; no template).
- Keep history RICH on each entity (do not summarise the facts away). Carry low-confidence into conjectural[] (grit, never dropped).
- There is no AI/assistant entity here (WhatsApp); there must be none.
PERSON-ENTITIES:
${JSON.stringify(personEntities)}
GERARD (apex):
${JSON.stringify(gerard)}
Return the map via StructuredOutput: {entities[], groups[], author_generator[], conjectural[], notes}.`
}

function adjPrompt(map, sourceEntities) {
  return `You are a sealed ADJUDICATOR (builder != judge) for the relational soul-pour. You did NOT build this map. Judge it against the folded entities it was built from.
${SEAL}
Check: (1) faithful/partial/confabulated counts across entities+groups; (2) seal_clean - any verbatim source content leaked? (3) wrong_merges - any two distinct people merged? list them; (4) substrate_present - any AI/assistant entity that shouldn't exist? (5) history_rich - did the fold preserve specific facts rather than summarising them away? (6) flags - invented groups/relations, dropped conjectural grit, attribution bleed.
A GOOD 'partial' (recurs, thin-but-true) is the target band, not an error.
THE MAP:
${JSON.stringify(map)}
SOURCE ENTITIES:
${JSON.stringify(sourceEntities)}
Return the verdict via StructuredOutput.`
}

// ---- run ----
phase('Index')
const idx = await agent(
  `Read ${DIR}/_manifest.json and return EVERY row as {file, person}. Return all rows, do not truncate.`,
  { label: 'manifest', model: 'haiku', phase: 'Index', schema: { type: 'object', properties: { rows: { type: 'array', items: { type: 'object', properties: { file: { type: 'string' }, person: { type: 'string' } }, required: ['file', 'person'] } } }, required: ['rows'] } }
)
const rows = (idx && idx.rows) ? idx.rows : []
const byP = {}
for (const r of rows) (byP[r.person] ||= []).push(r.file)
const batches = []
for (const [person, files] of Object.entries(byP)) for (let i = 0; i < files.length; i += K) batches.push({ person, files: files.slice(i, i + K) })
log(`tranche: ${rows.length} windows / ${Object.keys(byP).length} people -> ${batches.length} distil-fold batches (K=${K})`)

phase('Floor')
const DRAIN = 24
const floor = []
for (let i = 0; i < batches.length; i += DRAIN) {
  const slice = batches.slice(i, i + DRAIN)
  const res = await parallel(slice.map(b => () =>
    agent(floorPrompt(b), { label: `distil:${nick(b.person)}`, model: 'haiku', phase: 'Floor', schema: FLOOR_SCHEMA }).catch(() => null)
  ))
  floor.push(...res)
  log(`floor: ${floor.filter(Boolean).length}/${batches.length} batches`)
}
const partials = floor.filter(Boolean)

// group partner-partials by person; collect Gerard atoms across all batches
const byPerson = {}
const gerardParts = []
for (const p of partials) {
  (byPerson[p.person] ||= []).push(p.partner)
  if (p.gerard) gerardParts.push(p.gerard)
}

phase('Fold')
const personEntities = (await parallel(Object.entries(byPerson).map(([person, ps]) => () =>
  agent(foldPrompt(person, ps), { label: `fold:${nick(person)}`, model: 'sonnet', phase: 'Fold', schema: ENTITY }).catch(() => null)
))).filter(Boolean)
log(`fold: ${personEntities.length} person-entities`)

phase('Apex')
const gerard = await agent(apexPrompt(gerardParts), { label: 'fold:Gerard', model: 'sonnet', phase: 'Apex', schema: ENTITY })

phase('Resolve')
const map = await agent(resolvePrompt(personEntities, gerard), { label: 'cross-person-keeper', model: 'opus', phase: 'Resolve', schema: MAP_SCHEMA })

phase('Adjudicate')
const verdict = await agent(adjPrompt(map, personEntities.concat([gerard])), { label: 'adjudicator', model: 'opus', phase: 'Adjudicate', schema: VERDICT_SCHEMA })

return { n_windows: rows.length, n_batches: batches.length, n_floor: partials.length, n_people: Object.keys(byP).length, n_entities: personEntities.length, map, verdict }
