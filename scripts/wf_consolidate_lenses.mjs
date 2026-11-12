import { bindDispatchAgent } from './dispatch_gate.mjs'
agent = bindDispatchAgent(agent, () => args?.dispatchAdmissions ?? globalThis.dispatchAdmissions)

export const meta = {
  name: 'soul-consolidate-lenses',
  description: 'A consolidating dream: the upward operator at the CROSS-CORPUS grade. For each person who lives in more than one current lens (the tranche-1 relational map + the collaborator corpus + the life/physics corpus), a sealed Opus keeper resolves their representations into ONE cross-world node - conservative (a wrong merge corrupts where a miss recovers), preserving the relational voice, the rich history, and the research contributions, with provenance per corpus. An Opus builder!=judge adjudicates. This links the friend-world to the work-world through the shared people, so the next tranche (the giants - Alicia is already a collaborator node) lands on linked ground. Seal: agents read sealed + public nodes; the orchestrator persists; no verbatim.',
  phases: [
    { title: 'Resolve', detail: 'Opus keeper folds one person across corpora -> one cross-world node', model: 'opus' },
    { title: 'Adjudicate', detail: 'Opus builder!=judge: faithful/partial/confab + seal + no-wrong-merge', model: 'opus' },
  ],
}

let A = args
if (typeof A === 'string') { try { A = JSON.parse(A) } catch (e) { A = {} } }
A = A || {}
const MAP = A.map || 'archive/soul_dump/_shard/scaled_tranche1_folded/_RELATIONAL_MAP.json'
const PEOPLE = A.people || []  // [{name, relational_name, files:[...]}]

const HIST = { type: 'object', properties: { fact: { type: 'string' }, locator: { type: 'string' }, confidence: { type: 'string' } }, required: ['fact', 'locator', 'confidence'] }
const REL = { type: 'object', properties: { with: { type: 'string' }, nature: { type: 'string' } }, required: ['with', 'nature'] }
const CONTRIB = { type: 'object', properties: { contribution: { type: 'string' }, confidence: { type: 'string' } }, required: ['contribution', 'confidence'] }
const XNODE = {
  type: 'object',
  properties: {
    canonical_name: { type: 'string' },
    merged_surface_names: { type: 'array', items: { type: 'string' } },
    corpora_present: { type: 'array', items: { type: 'string' } },
    voice: { type: 'array', items: { type: 'string' } },
    history: { type: 'array', items: HIST },
    research: { type: 'array', items: CONTRIB },
    relations: { type: 'array', items: REL },
    conjectural: { type: 'array', items: { type: 'string' } },
    provenance_note: { type: 'string' },
  },
  required: ['canonical_name', 'merged_surface_names', 'corpora_present', 'voice', 'history', 'research', 'relations', 'conjectural', 'provenance_note'],
}
const VERDICT = {
  type: 'object',
  properties: { verdict: { type: 'string' }, faithful: { type: 'integer' }, partial: { type: 'integer' }, confabulated: { type: 'integer' }, seal_clean: { type: 'boolean' }, wrong_merges: { type: 'array', items: { type: 'string' } }, cross_world_sound: { type: 'boolean' }, flags: { type: 'array', items: { type: 'string' } }, summary: { type: 'string' } },
  required: ['verdict', 'faithful', 'partial', 'confabulated', 'seal_clean', 'wrong_merges', 'cross_world_sound', 'flags', 'summary'],
}

const SEAL = 'SEAL (non-negotiable): never quote or copy source text; paraphrase everything; output contains NO verbatim sentences/phrases; locators are file/line refs only, never content.'

function resolvePrompt(p) {
  return `You are a sealed cross-corpus KEEPER (the upward operator at the person grade, linking lenses). Resolve ${p.name} into ONE cross-world node from their representations across corpora.
${SEAL}
Read these sources (Read tool):
- The relational map: ${MAP} - find the entity whose canonical_name matches "${p.relational_name}" (the WhatsApp relational world: voice + history + relations).
${p.files.map(f => `- ${f}`).join('\n')}
RULES (a wrong merge corrupts where a miss recovers):
- Resolve CONSERVATIVELY: merge only when the sources clearly establish the SAME person (cross-join on shared facts - co-authored papers, institution, timeline, name). If a source is ambiguous, keep it OUT and say so in provenance_note. Record merged_surface_names + corpora_present.
- Preserve the relational VOICE (how they talk, from the map) and the rich HISTORY (relational + life facts, paraphrased, dated where known). Put research/physics contributions in research[] (from the collaborator/papers nodes).
- relations: who they relate to and how (esp. to Gerard). Carry low-confidence into conjectural[] (grit, never dropped).
- Invent nothing; add no fact a source doesn't support. A thin true node beats an embellished one.
Return the cross-world node via StructuredOutput.`
}

function adjPrompt(nodes) {
  return `You are a sealed ADJUDICATOR (builder != judge) for a cross-corpus consolidation. You did NOT build these nodes. Judge them.
${SEAL}
Check: (1) faithful/partial/confabulated counts; (2) seal_clean - any verbatim content leaked? (3) wrong_merges - any node fusing two DISTINCT people (e.g. a different same-surname person)? list them; (4) cross_world_sound - is each merge justified by a real shared join (co-authorship/institution/timeline), not just a name coincidence? (5) flags - invented facts, dropped grit, a research contribution attributed wrongly, relational/work attribution bleed.
A GOOD 'partial' (thin-but-true, conservative non-merge disclosed) is the target band, not an error.
THE CROSS-WORLD NODES:
${JSON.stringify(nodes)}
Return the verdict via StructuredOutput.`
}

// ---- run ----
log(`consolidate-lenses: cross-resolving ${PEOPLE.length} shared people across corpora`)

phase('Resolve')
const nodes = (await parallel(PEOPLE.map(p => () =>
  agent(resolvePrompt(p), { label: `xresolve:${p.name}`, model: 'opus', schema: XNODE, phase: 'Resolve' }).catch(() => null)
))).filter(Boolean)
log(`resolved ${nodes.length}/${PEOPLE.length} cross-world nodes`)

phase('Adjudicate')
const verdict = await agent(adjPrompt(nodes), { label: 'adjudicator', model: 'opus', schema: VERDICT, phase: 'Adjudicate' })

return { n_resolved: nodes.length, nodes, verdict }
