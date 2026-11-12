import { bindDispatchAgent } from './dispatch_gate.mjs'
agent = bindDispatchAgent(agent, () => args?.dispatchAdmissions ?? globalThis.dispatchAdmissions)

export const meta = {
  name: 'soul-fold-person',
  description: 'The per-person APEX fold for a giant, by the ONE recursive operator. A giant is poured to grade-1 slice-entities (disjoint time-spans) by wf_one_person.mjs in ceiling-safe runs; this folds those slices UP into one grade-2 apex. The fold agent READS the sealed slice files directly and consolidates (big input, bounded output - no re-emit truncation); when a person has more slices than fit one agent, the SAME fold recurs over the batch-partials. The fold is GRADE-UP: union voice/relations, consolidate history to the distinct salient handle. Full granular detail is RETAINED in the slice shards below and recoverable on descent - the apex is a handle, not an exhaustive ledger (distillation-recoverable-not-surface). An Opus builder!=judge adjudicates the apex against its slices. Seal: agents read sealed files; the orchestrator holds only paraphrased distillate.',
  phases: [
    { title: 'Fold', detail: 'fold agent reads slice files and consolidates UP; recurs if too many slices' },
    { title: 'Adjudicate', detail: 'Opus builder!=judge: faithful-as-consolidation + seal + detail-recoverable', model: 'opus' },
  ],
}

let A = args
if (typeof A === 'string') { try { A = JSON.parse(A) } catch (e) { A = {} } }
A = A || {}
const DIR = A.dir || 'archive/soul_dump/_shard/scaled_tranche2_folded'
const PERSON = A.person || 'Unknown'
const SLICES = A.sliceFiles || []          // [filename, ...] under ${DIR}/_slices/, each a grade-1 ENTITY
const PER_FOLD = A.perFold || 6            // slice files one fold agent reads at once (~50KB each -> safe under context)

const HIST = { type: 'object', properties: { fact: { type: 'string' }, locator: { type: 'string' }, confidence: { type: 'string' } }, required: ['fact', 'locator', 'confidence'] }
const REL = { type: 'object', properties: { with: { type: 'string' }, nature: { type: 'string' } }, required: ['with', 'nature'] }
const ENTITY = { type: 'object', properties: { name: { type: 'string' }, is_author: { type: 'boolean' }, voice: { type: 'array', items: { type: 'string' } }, history: { type: 'array', items: HIST }, relations: { type: 'array', items: REL }, conjectural: { type: 'array', items: { type: 'string' } }, slice_shards: { type: 'array', items: { type: 'string' } } }, required: ['name', 'is_author', 'voice', 'history', 'relations'] }
const VERDICT_SCHEMA = {
  type: 'object',
  properties: { verdict: { type: 'string' }, faithful: { type: 'integer' }, partial: { type: 'integer' }, confabulated: { type: 'integer' }, seal_clean: { type: 'boolean' }, detail_recoverable: { type: 'boolean' }, wrong_merges: { type: 'array', items: { type: 'string' } }, history_salient: { type: 'boolean' }, flags: { type: 'array', items: { type: 'string' } }, summary: { type: 'string' } },
  required: ['verdict', 'faithful', 'partial', 'confabulated', 'seal_clean', 'detail_recoverable', 'wrong_merges', 'history_salient', 'flags', 'summary'],
}

const SEAL = 'SEAL (non-negotiable): never quote or copy source text; paraphrase everything; output contains NO verbatim sentences/phrases, not even short ones; locators are line-ranges only, never content.'

function chunk(items, k) { const out = []; for (let i = 0; i < items.length; i += k) out.push(items.slice(i, i + k)); return out }

const GRADE_UP = `The full granular history is RETAINED in the slice shards below and recoverable on descent, so the apex is a HANDLE, not an exhaustive ledger:
- voice: union the characteristic traits; dedup to a coherent set; keep what is distinctive.
- relations: union by partner; merge natures.
- history: consolidate to the DISTINCT, salient facts - merge duplicates and near-duplicates across slices, fold repetitive trivia into representative statements, keep every MEANINGFUL distinct fact with its locator; roughly chronological. You need NOT reproduce every minor instance (those live in the slices).
- carry genuinely low-confidence / one-off items into conjectural[] (grit, never dropped, never promoted to fact).
Invent nothing. Conflate no two distinct people.`

// leaf fold: an agent READS a batch of sealed slice files and consolidates them grade-up into one entity
function foldFiles(files, label) {
  const list = files.map(f => `${DIR}/_slices/${f}`).join('\n')
  return agent(`You are a sealed KEEPER performing a GRADE-UP consolidation for ${PERSON}. Read each of these grade-1 slice-entity files (Read tool) - each is a JSON ENTITY for a disjoint time-span of ${PERSON}'s 1:1 with Gerard:
${list}
Fold them into ONE consolidated entity.
${SEAL} (the files are already paraphrased; keep it so.)
${GRADE_UP}
Return ONE entity via StructuredOutput: {name:"${PERSON}", is_author:false, voice[], history[], relations[], conjectural[]}.`,
    { label, model: 'sonnet', schema: ENTITY, phase: 'Fold' }).catch(() => null)
}

// THE ONE OPERATOR (grade-up): fold in-memory partials, recurring when a level is too big
async function recur(items, label) {
  items = items.filter(Boolean)
  if (items.length === 0) return null
  if (items.length === 1) return items[0]
  const batches = chunk(items, PER_FOLD)
  const prompt = (b) => `You are a sealed KEEPER performing a GRADE-UP consolidation for ${PERSON}. You receive already-consolidated, already-paraphrased partial entities. Fold them into ONE.
${SEAL}
${GRADE_UP}
PARTIALS:
${JSON.stringify(b)}
Return ONE entity via StructuredOutput: {name:"${PERSON}", is_author:false, voice[], history[], relations[], conjectural[]}.`
  const partials = (await parallel(batches.map((b, i) =>
    () => (b.length === 1 ? Promise.resolve(b[0]) : agent(prompt(b), { label: `${label}.${i}`, model: 'sonnet', schema: ENTITY, phase: 'Fold' }).catch(() => null))
  ))).filter(Boolean)
  log(`recur ${PERSON}: ${items.length} -> ${partials.length}`)
  return recur(partials, `${label}^`)
}

// ---- run ----
log(`fold-person: ${PERSON} <- ${SLICES.length} slices (perFold=${PER_FOLD}) -> grade-2 apex`)

phase('Fold')
let apex
if (SLICES.length <= PER_FOLD) {
  apex = await foldFiles(SLICES, `apex:${PERSON}`)        // one agent reads all slices -> apex
} else {
  const batches = chunk(SLICES, PER_FOLD)                 // too many slices: fold each batch (reads its files), then recur
  const partials = (await parallel(batches.map((b, i) => () => foldFiles(b, `fold:${PERSON}.${i}`)))).filter(Boolean)
  log(`fold ${PERSON}: ${SLICES.length} slices -> ${partials.length} batch-partials, recurring`)
  apex = await recur(partials, `apex:${PERSON}`)
}
if (apex && !apex.slice_shards) apex.slice_shards = SLICES.map(f => `_slices/${f}`)

phase('Adjudicate')
const verdict = await agent(`You are a sealed ADJUDICATOR (builder != judge) for a giant's APEX fold. You did NOT build this apex. Judge it against the grade-1 slice-entities it was consolidated from - Read them yourself: ${SLICES.map(f => `${DIR}/_slices/${f}`).join(', ')}.
${SEAL}
This is a GRADE-UP consolidation: the apex is a handle; the slices below hold the full granular detail and are recoverable. So do NOT penalise the apex for not inlining every minor fact - that is correct grading. Check:
(1) faithful/partial/confabulated counts across the apex's voice+history+relations;
(2) seal_clean - any verbatim source content leaked into the apex?
(3) detail_recoverable - is slice_shards present, and do the slices genuinely hold the granular detail the apex coarsened?
(4) wrong_merges - any distinct people conflated into ${PERSON} or into one relation? list them;
(5) history_salient - did the consolidation keep the DISTINCT meaningful facts (not drop important ones, not invent), folding only duplicates/trivia?
(6) flags - invented facts/relations, dropped grit, attribution bleed, or over-summarisation that loses a distinct fact with NO slice to recover it.
THE APEX:
${JSON.stringify(apex)}
Return the verdict via StructuredOutput.`,
  { label: `adjudicator:${PERSON}`, model: 'opus', schema: VERDICT_SCHEMA, phase: 'Adjudicate' })

return { person: PERSON, n_slices: SLICES.length, apex, verdict }
