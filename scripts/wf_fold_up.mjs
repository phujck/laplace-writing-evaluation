import { bindDispatchAgent } from './dispatch_gate.mjs'
agent = bindDispatchAgent(agent, () => args?.dispatchAdmissions ?? globalThis.dispatchAdmissions)

export const meta = {
  name: 'soul-fold-up',
  description: 'The tranche-1 relational gate by ONE recursive operator. Leaves: a Sonnet keeper reads one sealed shard file and folds its contents to a partial entity. Reduce: the SAME fold, applied recursively - pack the partials into context-sized batches, fold each, recur on the results until one remains. Depth is emergent from size, never a hardcoded chunk count: 11 windows or 11 million, the operator is identical. Person-entities and Gerard\'s apex are both fold-ups; the resolve is the grade-link to the relational map; an Opus builder!=judge adjudicates. Seal: agents read sealed files; the orchestrator holds only paraphrased distillate.',
  phases: [
    { title: 'Leaves', detail: 'Sonnet folds one sealed shard file -> a partial entity' },
    { title: 'Reduce', detail: 'the same fold, recurring over partials until one remains' },
    { title: 'Resolve', detail: 'Opus grade-link: person-entities -> the relational map', model: 'opus' },
    { title: 'Adjudicate', detail: 'Opus builder!=judge: faithful/partial/confab + seal + no-wrong-merge', model: 'opus' },
  ],
}

let A = args
if (typeof A === 'string') { try { A = JSON.parse(A) } catch (e) { A = {} } }
A = A || {}
const DIR = A.dir || 'archive/soul_dump/_shard/scaled_tranche1_folded'
const PARTIALS = A.partials || []      // [{person, file}] - each a sealed per-person partials file
const GCHUNKS = A.gerardChunks || []   // [file, ...] - sealed gerard atom-window shards
const WILL = A.willFile || 'will_handley.json'  // pre-folded Will entity (sealed)
const MAXCHARS = A.maxChars || 140000  // ~35k tokens of partials per fold agent

const HIST = { type: 'object', properties: { fact: { type: 'string' }, locator: { type: 'string' }, confidence: { type: 'string' } }, required: ['fact', 'locator', 'confidence'] }
const REL = { type: 'object', properties: { with: { type: 'string' }, nature: { type: 'string' } }, required: ['with', 'nature'] }
const GEN = { type: 'object', properties: { primitive: { type: 'string' }, statement: { type: 'string' }, confidence: { type: 'string' } }, required: ['primitive', 'statement', 'confidence'] }
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

const SEAL = 'SEAL (non-negotiable): never quote or copy source text; paraphrase everything; output contains NO verbatim sentences/phrases, not even short ones; locators are line-ranges only, never content.'

// pack items greedily into context-sized batches (handles both "too many" and "too big")
function pack(items, maxChars) {
  const batches = []; let cur = [], n = 0
  for (const it of items) {
    const s = JSON.stringify(it).length
    if (cur.length && n + s > maxChars) { batches.push(cur); cur = []; n = 0 }
    cur.push(it); n += s
  }
  if (cur.length) batches.push(cur)
  return batches
}

// THE ONE OPERATOR: fold a list of partial entities into one, recurring when a level is too big.
async function recur(items, { name, isAuthor, label, phase }) {
  items = items.filter(Boolean)
  if (items.length === 0) return null
  if (items.length === 1) return items[0]
  const batches = pack(items, MAXCHARS)
  const prompt = (b) => `You are a sealed KEEPER. Fold these already-paraphrased partial entities for ${name} into ONE.
${SEAL}
Rules: dedup voice (keep characteristic traits); MERGE history into a rich, de-duplicated, roughly chronological set - PRESERVE specific facts, never summarise them away; union relations; ${isAuthor ? 'consolidate the generator into a small coherent set of his actual primitives (impose no template); ' : ''}carry low-confidence items forward as conjectural (never drop). Invent nothing.
PARTIALS:
${JSON.stringify(b)}
Return ONE entity via StructuredOutput: {name:"${name}", is_author:${isAuthor}, voice[], history[], relations[]${isAuthor ? ', generator[]' : ''}}.`
  if (batches.length === 1) return agent(prompt(batches[0]), { label, model: 'sonnet', schema: ENTITY, phase }).catch(() => null)
  const partials = (await parallel(batches.map((b, i) => () =>
    agent(prompt(b), { label: `${label}.${i}`, model: 'sonnet', schema: ENTITY, phase }).catch(() => null)
  ))).filter(Boolean)
  log(`reduce ${name}: ${items.length} -> ${partials.length} partials, recurring`)
  return recur(partials, { name, isAuthor, label: `${label}^`, phase })
}

// leaf: read ONE sealed file and fold its contents to a partial entity (same operator, base case)
function leafPerson(p) {
  return agent(`You are a sealed per-person KEEPER. Read ${DIR}/_partials/${p.file} (Read tool): a JSON {person, partials:[partner-partial entities across windows of ${p.person}'s WhatsApp 1:1 with Gerard]}. Fold the partials into ONE entity for ${p.person}.
${SEAL} (inputs already paraphrased; keep so.)
Dedup voice; merge history rich + de-duplicated + roughly chronological (preserve specific facts); union relations; carry low-confidence as conjectural. Focus on ${p.person}; treat any third party mentioned as a relation, not the subject. Invent nothing.
Return via StructuredOutput: {name:"${p.person}", is_author:false, voice[], history[], relations[]}.`,
    { label: `fold:${p.person}`, model: 'sonnet', schema: ENTITY, phase: 'Leaves' }).catch(() => null)
}
function leafGerard(file) {
  return agent(`You are a sealed KEEPER consolidating GERARD's atoms from one shard. Read ${DIR}/_gerard_chunks/${file} (Read tool): a JSON {gerard_atoms:[{voice,history,relations,generator} per window]}. Fold into ONE partial Gerard entity for this shard.
${SEAL} (inputs already paraphrased.)
Dedup voice; merge history rich (his facts/plans/projects); union relations; consolidate generator (his stance|move|value|aesthetic|friction) preserving his actual taste. Invent nothing.
Return via StructuredOutput: {name:"Gerard", is_author:true, voice[], history[], relations[], generator[]}.`,
    { label: `gerard-leaf:${file}`, model: 'sonnet', schema: ENTITY, phase: 'Leaves' }).catch(() => null)
}

// ---- run ----
log(`fold-up: ${PARTIALS.length} people + Gerard(${GCHUNKS.length} shards) + Will(pre-folded) -> relational map`)

phase('Leaves')
const personLeaves = await parallel(PARTIALS.map(p => () => leafPerson(p)))
const gerardLeaves = await parallel(GCHUNKS.map(c => () => leafGerard(c)))

phase('Reduce')
// persons: 1 file each -> already folded; reduce only collapses any people that needed >1 shard (none here)
const personEntities = personLeaves.filter(Boolean)
const gerard = await recur(gerardLeaves, { name: 'Gerard', isAuthor: true, label: 'gerard-reduce', phase: 'Reduce' })

phase('Resolve')
const map = await agent(`You are the sealed cross-person KEEPER (the upward operator at the relational grade). You receive the folded person-entities of tranche-1 of Gerard's WhatsApp relational world, plus Gerard's apex. ALSO Read ${DIR}/${WILL} (Read tool): a pre-folded entity {entity:{...Will Handley...}} - use its .entity as one more person-entity. Build the grade-2 relational map.
${SEAL}
RULES (a wrong merge corrupts where a miss recovers):
- Resolve entities CONSERVATIVELY: merge two surface-names only when atoms clearly establish the same person; when uncertain keep SPLIT and say so. Record merged_surface_names.
- Gerard is the network HUB (is_author:true) - carry his consolidated entity + generator.
- Derive grade-2 GROUPS ONLY from actual relations present (e.g. a family circle, a research/collaborator circle); invent NO group/membership the relations don't support; state each group's basis.
- Keep history RICH per entity (do not summarise facts away). Carry low-confidence into conjectural[] (grit, never dropped).
- There is no AI/assistant entity here (WhatsApp); there must be none.
PERSON-ENTITIES (Will is in the file above; these are the rest):
${JSON.stringify(personEntities)}
GERARD (apex):
${JSON.stringify(gerard)}
Return the map via StructuredOutput: {entities[], groups[], author_generator[], conjectural[], notes}.`,
  { label: 'cross-person-keeper', model: 'opus', schema: MAP_SCHEMA, phase: 'Resolve' })

phase('Adjudicate')
const verdict = await agent(`You are a sealed ADJUDICATOR (builder != judge) for the relational soul-pour. You did NOT build this map. Judge it against the folded entities it was built from.
${SEAL}
Check: (1) faithful/partial/confabulated counts across entities+groups; (2) seal_clean - any verbatim source content leaked? (3) wrong_merges - any two distinct people merged? list them; (4) substrate_present - any AI/assistant entity that shouldn't exist? (5) history_rich - did the fold preserve specific facts rather than summarising them away? (6) flags - invented groups/relations, dropped conjectural grit, attribution bleed.
A GOOD 'partial' (recurs, thin-but-true) is the target band, not an error.
THE MAP:
${JSON.stringify(map)}
SOURCE ENTITIES (Gerard apex + the rest; Will additionally in the map):
${JSON.stringify(personEntities.concat([gerard]))}
Return the verdict via StructuredOutput.`,
  { label: 'adjudicator', model: 'opus', schema: VERDICT_SCHEMA, phase: 'Adjudicate' })

return { n_people: personEntities.length, n_gerard_shards: GCHUNKS.length, map, verdict }
