import { bindDispatchAgent } from './dispatch_gate.mjs'
agent = bindDispatchAgent(agent, () => args?.dispatchAdmissions ?? globalThis.dispatchAdmissions)

export const meta = {
  name: 'voice-from-papers',
  description: 'The SCIENTIFIC voice fold (N36, physics middle): reconstruct a collaborator\'s scientific voice and traits from their PUBLIC papers (OpenAlex titles+abstracts, already on disk). Conjugate of the chat-voice fold: the chats hold how they speak to Gerard; the papers hold how they think in the literature. Observe = a Haiku swarm reads disjoint batches of works and extracts grounded voice observations (every observation cites work ids). Fold = the ONE recursive operator (sonnet) consolidates observations UP into 8-14 voice items, confidence graded by recurrence (low = conjectural grit, kept never dropped). Adjudicate = builder!=judge (sonnet, refute-first) re-reads a sample of the works and judges faithful/confabulated. Public bibliographic data - no seal needed; locators are OpenAlex short ids + years.',
  phases: [
    { title: 'Observe', detail: 'Haiku swarm: disjoint work-batches -> grounded voice observations', model: 'haiku' },
    { title: 'Fold', detail: 'the one recursive operator: observations -> 8-14 voice items', model: 'sonnet' },
    { title: 'Adjudicate', detail: 'builder!=judge, refute-first, against a fresh sample of the works', model: 'sonnet' },
  ],
}

let A = args
if (typeof A === 'string') { try { A = JSON.parse(A) } catch (e) { A = {} } }
A = A || {}
const KEY = A.key || 'bondar'
const NAME = A.name || 'Unknown'
const WORKS_FILE = A.worksFile || `collaborator_corpus/_raw/${KEY}_works.json`
const N_WORKS = A.nWorks || 0              // total works in the file (orchestrator counted)
const PER_BATCH = A.perBatch || 18         // works one observe agent reads (titles+abstracts ~30KB)
const PER_FOLD = A.perFold || 4            // observation-partials one fold agent consolidates

const OBS = {
  type: 'object',
  properties: {
    observations: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          observation: { type: 'string' },
          kind: { type: 'string', description: 'move | style | concern | posture' },
          works: { type: 'array', items: { type: 'string' }, description: 'OpenAlex short ids (W...) + year, of the works exhibiting it' },
        },
        required: ['observation', 'kind', 'works'],
      },
    },
  },
  required: ['observations'],
}

const VOICE = {
  type: 'object',
  properties: {
    voice_items: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          name: { type: 'string', description: 'kebab-case handle' },
          statement: { type: 'string' },
          kind: { type: 'string', description: 'move | style | concern | posture' },
          confidence: { type: 'string', description: 'high (recurs across many works) | medium | low (one-off, conjectural grit)' },
          works: { type: 'array', items: { type: 'string' } },
        },
        required: ['name', 'statement', 'kind', 'confidence', 'works'],
      },
    },
  },
  required: ['voice_items'],
}

const VERDICT = {
  type: 'object',
  properties: {
    faithful: { type: 'integer' }, partial: { type: 'integer' }, confabulated: { type: 'integer' },
    grounded: { type: 'boolean', description: 'every item cites real works from the file' },
    flags: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
  },
  required: ['faithful', 'partial', 'confabulated', 'grounded', 'flags', 'summary'],
}

const WHAT_VOICE_IS = `A SCIENTIFIC VOICE item is how this scientist thinks and writes, not what topics they touch:
- move: a recurring methodological/argumentative move (e.g. "reframes a control problem as a tracking condition", "builds exact mappings before approximating")
- style: how the prose/abstracts argue (e.g. "leads with the physical paradox, then resolves it formally")
- concern: what they persistently care about across topics (e.g. "experimental testability of formal results")
- posture: their epistemic stance (e.g. "rigour-first: theorems before numerics", "unification-seeking across classical/quantum")
Ground EVERY observation in the specific works exhibiting it (short id + year). Topics alone are NOT voice - the contribution atoms already hold topics. Invent nothing; if the abstracts do not show it, do not claim it.`

function chunk(n, k) { const out = []; for (let i = 0; i < n; i += k) out.push([i, Math.min(i + k, n)]); return out }

// ---- Observe: a Haiku swarm over disjoint slices of the works file ----
phase('Observe')
const ranges = chunk(N_WORKS, PER_BATCH)
log(`voice-from-papers: ${NAME} <- ${N_WORKS} works in ${ranges.length} batches`)
const obs = (await parallel(ranges.map(([a, b], i) => () =>
  agent(`You are a voice OBSERVER for the scientist ${NAME}. Read the JSON file ${WORKS_FILE} (Read tool) and consider ONLY works[${a}..${b}) (0-indexed slice of the top-level array; each work has title/abstract/year/id). ${WHAT_VOICE_IS}
From YOUR slice only, extract 3-8 grounded voice observations via StructuredOutput.`,
    { label: `observe:${KEY}.${i}`, model: 'haiku', schema: OBS, phase: 'Observe' }).catch(() => null)
))).filter(Boolean).flatMap(r => r.observations || [])
log(`observed: ${obs.length} raw observations`)

// ---- Fold: the one recursive operator over observation-partials ----
phase('Fold')
async function recur(items, label) {
  items = items.filter(Boolean)
  if (items.length === 0) return null
  if (items.length === 1) return items[0]
  const batches = []
  for (let i = 0; i < items.length; i += PER_FOLD) batches.push(items.slice(i, i + PER_FOLD))
  const partials = (await parallel(batches.map((b, i) => () =>
    b.length === 1 ? Promise.resolve(b[0]) :
    agent(`You are the KEEPER folding scientific-voice partials for ${NAME} GRADE-UP into one consolidated set. ${WHAT_VOICE_IS}
Merge items describing the SAME move/style/concern/posture (union their works lists - recurrence across batches RAISES confidence); keep distinct items distinct; carry one-off low-confidence items as confidence "low" (conjectural grit - never drop, never promote). Aim for the smallest faithful set.
PARTIALS:
${JSON.stringify(b)}
Return ONE consolidated {voice_items} via StructuredOutput.`,
      { label: `${label}.${i}`, model: 'sonnet', schema: VOICE, phase: 'Fold' }).catch(() => null)
  ))).filter(Boolean)
  log(`recur ${NAME}: ${items.length} -> ${partials.length}`)
  return recur(partials, `${label}^`)
}
// seed: wrap raw observations as one-work voice items for the fold
const seed = []
for (let i = 0; i < obs.length; i += 24) {
  seed.push({ voice_items: obs.slice(i, i + 24).map(o => ({
    name: '', statement: o.observation, kind: o.kind, confidence: 'low', works: o.works || [] })) })
}
const folded = await recur(seed, `fold:${KEY}`)
const items = (folded && folded.voice_items) || []
log(`folded: ${items.length} voice items`)

// ---- Adjudicate: builder!=judge, refute-first, against a fresh sample ----
phase('Adjudicate')
const verdict = await agent(`You are a sealed ADJUDICATOR (builder != judge) - you did NOT build this voice profile. REFUTE-FIRST: assume each item is confabulated until the works support it. Read ${WORKS_FILE} yourself (Read tool; spot-check the works each item cites by id, plus a random sample of others). ${WHAT_VOICE_IS}
Judge each item of THE PROFILE below: faithful (the cited works clearly exhibit it) / partial (gestures at something real but overstated or thinly grounded) / confabulated (the works do not show it). Check grounded: do the cited ids exist in the file? Flag topic-restatement masquerading as voice.
THE PROFILE (${NAME}):
${JSON.stringify(items)}
Return the verdict via StructuredOutput.`,
  { label: `adjudicate:${KEY}`, model: 'sonnet', schema: VERDICT, phase: 'Adjudicate' })

return { key: KEY, name: NAME, n_works: N_WORKS, n_observations: obs.length, voice_items: items, verdict }
