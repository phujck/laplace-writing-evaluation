import { bindDispatchAgent } from './dispatch_gate.mjs'
agent = bindDispatchAgent(agent, () => args?.dispatchAdmissions ?? globalThis.dispatchAdmissions)

export const meta = {
  name: 'soul-wire-tranche2',
  description: 'The WIRING step for tranche-2: the second intelligent operation (the inter-grade/cross-thread semantic link). Resolves the poured 1:1 nodes into the relational world - merges the +44 crisis-thread into Alicia (same person, two phone threads), builds the gaming-group CIRCLE node from the deferred group distillate (members as relations, NOT flattened into a person), and lays the grade-3 tranche-2 relational map (groups, Gerard the hub, cross-links noted to the existing world for the dream to fold). Opus builder; a separate Opus builder!=judge adjudicates. Seal: agents read sealed files; the orchestrator holds only paraphrased distillate.',
  phases: [
    { title: 'Resolve', detail: 'merge +44->Alicia; build the gaming circle node', model: 'opus' },
    { title: 'Map', detail: 'lay the grade-3 tranche-2 relational map with cross-link notes', model: 'opus' },
    { title: 'Adjudicate', detail: 'Opus builder!=judge: merges right, circle not a person, seal', model: 'opus' },
  ],
}

const DIR = 'archive/soul_dump/_shard/scaled_tranche2_folded'
const SEAL = 'SEAL (non-negotiable): never quote or copy source text; paraphrase everything; output contains NO verbatim sentences/phrases; locators are line-ranges only, never content.'

const HIST = { type: 'object', properties: { fact: { type: 'string' }, locator: { type: 'string' }, confidence: { type: 'string' } }, required: ['fact', 'locator', 'confidence'] }
const REL = { type: 'object', properties: { with: { type: 'string' }, nature: { type: 'string' } }, required: ['with', 'nature'] }
const XLINK = { type: 'object', properties: { to: { type: 'string' }, corpus: { type: 'string' }, basis: { type: 'string' } }, required: ['to', 'corpus', 'basis'] }
const ENTITY = { type: 'object', properties: { name: { type: 'string' }, is_author: { type: 'boolean' }, merged_surface_names: { type: 'array', items: { type: 'string' } }, voice: { type: 'array', items: { type: 'string' } }, history: { type: 'array', items: HIST }, relations: { type: 'array', items: REL }, conjectural: { type: 'array', items: { type: 'string' } }, cross_links: { type: 'array', items: XLINK } }, required: ['name', 'is_author', 'voice', 'history', 'relations'] }
const CIRCLE = { type: 'object', properties: { name: { type: 'string' }, kind: { type: 'string' }, members: { type: 'array', items: { type: 'object', properties: { name: { type: 'string' }, note: { type: 'string' } }, required: ['name', 'note'] } }, character: { type: 'array', items: { type: 'string' } }, history: { type: 'array', items: HIST }, conjectural: { type: 'array', items: { type: 'string' } } }, required: ['name', 'kind', 'members', 'character'] }
const MAPENT = { type: 'object', properties: { canonical_name: { type: 'string' }, kind: { type: 'string' }, merged_surface_names: { type: 'array', items: { type: 'string' } }, node_file: { type: 'string' }, summary: { type: 'string' }, cross_links: { type: 'array', items: XLINK } }, required: ['canonical_name', 'kind', 'node_file', 'summary'] }
const MAP = { type: 'object', properties: { entities: { type: 'array', items: MAPENT }, groups: { type: 'array', items: { type: 'object', properties: { name: { type: 'string' }, members: { type: 'array', items: { type: 'string' } }, basis: { type: 'string' } }, required: ['name', 'members', 'basis'] } }, author_hub: { type: 'array', items: REL }, conjectural: { type: 'array', items: { type: 'string' } }, notes: { type: 'string' } }, required: ['entities', 'groups', 'author_hub', 'notes'] }
const VERDICT = { type: 'object', properties: { verdict: { type: 'string' }, faithful: { type: 'integer' }, partial: { type: 'integer' }, confabulated: { type: 'integer' }, seal_clean: { type: 'boolean' }, plus44_is_alicia_correct: { type: 'boolean' }, other_wrong_merges: { type: 'array', items: { type: 'string' } }, circle_not_flattened: { type: 'boolean' }, members_distinct: { type: 'boolean' }, flags: { type: 'array', items: { type: 'string' } }, summary: { type: 'string' } }, required: ['verdict', 'faithful', 'partial', 'confabulated', 'seal_clean', 'plus44_is_alicia_correct', 'other_wrong_merges', 'circle_not_flattened', 'members_distinct', 'flags', 'summary'] }

// ---- run ----
phase('Resolve')
const [alicia, circle] = await parallel([
  () => agent(`You are a sealed KEEPER resolving one person across two phone threads. Read ${DIR}/alicia_magann.json (her WhatsApp giant apex) AND ${DIR}/plus44_7540.json (the "+44 7540 983126" thread). These are the SAME person, Alicia Magann, across two numbers/periods: the +44 thread is the crisis chapter (Oct 2023-Jun 2024 - the van-life/homelessness period, the estrangement, the Feb-2024 block). Confirm the identity from the shared facts (Christian as partner, quantum-device domain, sister-figure framing) before merging - if the facts did NOT establish the same person you would keep them split, but here they do.
${SEAL}
Merge into ONE enriched Alicia entity: union voice; MERGE history (her apex history + the crisis-chapter facts from the +44 thread), roughly chronological, preserve distinct facts (the crisis chapter is a real, important period - do not summarise it away, but it is a grade-up handle so trivia may fold); record merged_surface_names:["+44 7540 983126"]; carry low-confidence as conjectural; add cross_links to her presence in OTHER corpora for the dream to fold: {to:"Alicia Magann", corpus:"collaborators/papers", basis:"co-authored quantum papers with Gerard and Denys"}. Invent nothing.
Return ONE entity via StructuredOutput: {name:"Alicia Magann", is_author:false, merged_surface_names[], voice[], history[], relations[], conjectural[], cross_links[]}.`,
    { label: 'resolve:alicia+44', model: 'opus', schema: ENTITY, phase: 'Resolve' }).catch(() => null),
  () => agent(`You are a sealed KEEPER building a CIRCLE node (a group, NOT a person). Read ${DIR}/_deferred_group/cruesetder_A.json and ${DIR}/_deferred_group/cruesetder_B.json - these are floor distillate of the friend-GROUP chat (gaming-renamed "Pub Pals"), where the 1:1 prompt mislabelled the whole group under one fake "Cruesetder Kings" entity.
${SEAL}
Build ONE circle node. The members are DISTINCT people (do NOT fold them into one person): Jonathan Perkins (barrister; wife Ruby; daughter Freya b. 2 Aug 2022 - the slice-A "barrister+Ruby" facts are HIS), Josh McNamee, Callum Tait, Grant Lodge, +any others the distillate supports. Gerard is a member, not the hub of this circle.
- members: each {name, note} - a short paraphrased who-they-are from the distillate.
- character: the group's shared character (Counter-Strike 5-stacks, banter/renaming rituals, tech/hardware talk, food opinions, home-improvement, life-milestones).
- history: salient GROUP-level facts (events the group shared); attribute member-specific facts to the member in the fact text.
- conjectural: anything uncertain (e.g. whether a fact belongs to a specific member).
Invent nothing. Return via StructuredOutput: {name:"The gaming group (ex–Pub Pals)", kind:"circle", members[], character[], history[], conjectural[]}.`,
    { label: 'build:gaming-circle', model: 'opus', schema: CIRCLE, phase: 'Resolve' }).catch(() => null),
])

phase('Map')
const map = await agent(`You are a sealed KEEPER laying the grade-3 TRANCHE-2 relational map (the wiring). You receive the resolved tranche-2 nodes. Read the small ones yourself for accuracy: ${DIR}/guy_skinner.json, ${DIR}/james_mccaul.json, ${DIR}/sam.json. The enriched Alicia and the gaming circle are given below.
${SEAL}
Build the map as an INDEX over the node files (handles, NOT re-inlined histories):
- entities: one MAPENT per node - {canonical_name, kind:"person"|"circle", merged_surface_names, node_file (the path), summary (2-4 sentence paraphrase of who they are to Gerard), cross_links (to OTHER corpora/the existing world, for the dream to fold)}. Node files: alicia_magann.json (person, +44 merged), guy_skinner.json (person), james_mccaul.json (person), sam.json (person), and the gaming circle (kind:"circle", node_file:"cruesetder_group.json").
- groups: derive ONLY from real relations - e.g. {family: [James McCaul]}, {close friends: [Guy Skinner, Sam, the gaming circle]}, {collaborators: [Alicia Magann]}. State each basis. Invent no membership.
- author_hub: Gerard's relation to each entity (he is the hub).
- cross_links to the EXISTING world for the dream: Alicia -> collaborator node (Denys/Juan co-authorship); James McCaul -> the tranche-1 family relations (mother, father, sister Mary). Note these, do not fold them here.
- conjectural: cross-links you suspect but cannot confirm (e.g. Sam's Michigan "Josh and Perky" possibly == the gaming circle's Josh - flag, do not assert).
ENRICHED ALICIA:
${JSON.stringify(alicia)}
GAMING CIRCLE:
${JSON.stringify(circle)}
Return the map via StructuredOutput.`,
  { label: 'wire:tranche2-map', model: 'opus', schema: MAP, phase: 'Map' })

phase('Adjudicate')
const verdict = await agent(`You are a sealed ADJUDICATOR (builder != judge) for the tranche-2 WIRING. You did NOT build it. Judge the merge + circle + map against the source nodes - Read them: ${DIR}/alicia_magann.json, ${DIR}/plus44_7540.json, ${DIR}/guy_skinner.json, ${DIR}/james_mccaul.json, ${DIR}/sam.json, ${DIR}/_deferred_group/cruesetder_A.json, ${DIR}/_deferred_group/cruesetder_B.json.
${SEAL}
Check:
(1) plus44_is_alicia_correct - do the +44 thread facts genuinely establish the same person as the Alicia giant (Christian partner, quantum-device domain, sister-figure, the crisis timeline)? TRUE only if the merge is right.
(2) other_wrong_merges - any OTHER distinct people conflated? (esp. inside the circle - Jonathan vs Josh vs Callum vs Grant must stay distinct). List them.
(3) circle_not_flattened - is the gaming group represented as a CIRCLE with distinct members, NOT as a single fake person?
(4) members_distinct - are the circle members kept as separate people with their own notes?
(5) faithful/partial/confabulated across the enriched-Alicia history + circle + map summaries.
(6) seal_clean; flags (invented facts/groups/cross-links, attribution bleed, the crisis chapter summarised away).
THE ENRICHED ALICIA: ${JSON.stringify(alicia)}
THE GAMING CIRCLE: ${JSON.stringify(circle)}
THE MAP: ${JSON.stringify(map)}
Return the verdict via StructuredOutput.`,
  { label: 'adjudicator:wiring', model: 'opus', schema: VERDICT, phase: 'Adjudicate' })

return { alicia, circle, map, verdict }
