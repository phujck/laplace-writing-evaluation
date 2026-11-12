import { bindDispatchAgent } from '../dispatch_gate.mjs'
agent = bindDispatchAgent(agent, () => args?.dispatchAdmissions ?? globalThis.dispatchAdmissions)

// THE PARTNER — the gen-4 Phase-B convergence loop as a Workflow script (his ask,
// 2026-07-23: "the partner for running falqon from the top autonomously").
//
// WHAT THIS IS: the dispatch hand the shepherd/judge pair lacks. The Workflow harness
// runs this script deterministically, spawning DISTINCT agent instances per stage —
// builder and judge are separate minds by construction (the superego's judge≠builder
// actor guard is satisfied structurally, never dodged) — serial lanes, journaled,
// PSU-RESUMABLE (resumeFromRunId replays completed rounds free after a trip).
//
// JURISDICTION: this is the COMMISSIONED per-generation loop (his commission
// FB-20260723-133025 + WO-20260723-132951-111576). The STANDING auto-driver
// (WO-20260716-145343) remains author-gated and un-fired — running this script is an
// orchestrator act on his live word, never an always-on organ.
//
// PRECONDITIONS (the invoker asserts before launch): Phase A judged STANDS on the
// realized plan (the A3 re-judge); the scanner live on 8770 with embeddings OFF;
// the repo pushed to master (custody). Storm rules ride every prompt below: no
// embeddings, ONE compile per build round, no browsers except the readability
// stranger's single instance, smallest-transaction writes.
//
export const meta = {
  name: 'falqon-phase-b',
  description: 'Gen-4 Phase B: projection rounds — build, judge, route — until the readability gate and superego both stand',
  phases: [
    { title: 'Round', detail: 'builder packet: realize the next section-front under the register firewall, ONE compile' },
    { title: 'Judge', detail: 'non-builder personas + superego on the built object; verdicts banked contestable' },
    { title: 'Gate', detail: 'the whole-object stranger read + done-criteria, together, before any candidate claim' },
  ],
}

// args: { corpus, maxRounds } — passed by the invoker; no defaults invented. The harness
// may deliver args as JSON TEXT (the banked 2026-07-08 lesson): parse before reading.
const A = typeof args === 'string' ? JSON.parse(args) : (args || {})
const corpus = A.corpus || null
if (!corpus) throw new Error('corpus required — the partner runs a named commission, never a default')
const MAX = A.maxRounds || 6

const STORM = `STORM RULES (absolute): no embeddings; at most ONE latex compile in your whole
packet; no browser unless this packet's brief explicitly grants one; every ledger write through
a sanctioned HTTP door or store module with your actor name; smallest transactions; bank
frictions via POST /corpus/friction as they happen with a chain of custody.`

const BRIEF = `Reconstruct before building (stores and code, never prose renders):
paper_falqon/manuscript/reprojection/gen4_brief.md (LAW P8 register firewall, done-criteria,
the readability gate), the live projection_plan.json, the rounds/ evidence trail, the binding
intro-b3 blocker RW-20260723-135921-571742 (cite the sibling families or reframe to the D9
structural condition — it resolves IN THIS PHASE at render), and the typed-open exclusion rows
(role-typed extensible direction, his evolutionary-shapes law RW-20260723-144332-358598).
HIS ARCHITECTURAL TASTE (profiles/author_architecture.yaml — his papers' measured structural
grain: intro shape, narrative arc, section rhythm, figure placement, closing form; two fields
CONFIRMED-CORRECTED by him 2026-07-22 and carrying his words, the rest RECONSTRUCTED awaiting
his confirmation): structural choices FOLLOW the profile's grain; where a field is unconfirmed
treat it as provisional taste and where you deviate, bank the deviation as a micro-decision
row (it feeds his confirmation). The structure judges compare any freely-derived structure
against this grain — his architecture is a measured input, never an afterthought.`

const VERDICT = {
  type: 'object', additionalProperties: false,
  properties: {
    // THE TELOS TIER (his challenge RW-20260723-155226-306492: "what is this _for_ and how
    // is it failing?") — REQUIRED before any criterion may count. `telos`: what this object
    // is FOR, derived fresh in the judge's own words (who reads it, what changes for them,
    // why they care) — never quoted from the brief. `failure_account`: the STRONGEST honest
    // account of how the object is failing at that purpose (assume failure; the object
    // survives only if this account does not hold). These are the first things his chair
    // reads. A derived-telos vs brief disagreement is a finding against the BRIEF.
    telos: { type: 'string' },
    failure_account: { type: 'string' },
    verdict: { enum: ['STANDS', 'REFUTED'] },
    routed_defects: { type: 'array', items: { type: 'string' } },
    banked_ids: { type: 'array', items: { type: 'string' } },
    // THE STEER CHANNEL (his ruling RW-20260723-154721-984120: "it would be insane if the
    // judgement part didn't want some directional steers on occasion for what it should be
    // aiming for"): a judge may REQUEST the author's direction (aim, audience, ambition,
    // structural intent). Each request is banked by the judge as a kind:"fork" row on the
    // corpus friction ledger (author-owed, desk-visible, contestable) and echoed here.
    steer_requests: { type: 'array', items: { type: 'object', additionalProperties: false,
      properties: { question: { type: 'string' }, why: { type: 'string' },
                    banked_id: { type: 'string' } },
      required: ['question', 'why'] } },
    summary: { type: 'string' },
  },
  required: ['telos', 'failure_account', 'verdict', 'routed_defects', 'banked_ids', 'summary'],
}

// THE TELOS DISCIPLINE — prepended to every judge and gate prompt:
const TELOS_Q = `BEFORE ANY CRITERION (his challenge, verbatim: "what is this _for_ and how
is it failing?"): FIRST state in your own words what this object is FOR — who reads it, what
changes for them after reading, why they would care — derived from the object and the world,
NEVER quoted from the brief. THEN give the strongest honest account of how it is FAILING at
that purpose: assume it fails; find the best failure story; the object survives only if that
story does not hold. Only after both may the personas and criteria count. If your derived
purpose disagrees with the brief's, that is a finding AGAINST THE BRIEF — route it up and
emit a steer request. Your telos and failure_account are the first fields of your verdict.`

// HIS STRUCTURE CHALLENGE (verbatim, banked RW-20260723-154721-984120) — a standing
// principal question for every Phase-B judge, above the round's local questions:
const STRUCTURE_Q = `HIS STANDING CHALLENGE (verbatim): "looking at the conceptric it's pretty
clear the falqon paper doesn't have a very clear target in mind, so I'm curious what the
structure it comes up with would be. Because in general you have a habit of trying to save a
bad structure by small changes that don't affect the massive ones." RULE IT EVERY ROUND: does
the inherited s1..s9 spine SERVE the class thesis, or is it the old instance-paper's skeleton
being rescued by small changes? What structure would the thesis choose FREELY (derive it in
two sentences and compare)? A structural refutation routes a PLAN-grade defect (back to the
plan surface), never a prose patch. If your ruling genuinely wants his direction (aim,
audience, ambition, venue), emit steer_requests — bank each as a kind:"fork" row via POST
/corpus/friction (by: your actor, owning_layer "generation", corpus "${'paper_falqon'}",
node "steer:<slug>", the question + why as the value) so it lands author-owed on his desk;
proceed provisionally on your best reading unless the steer is genuinely blocking.`

const ROUND = {
  type: 'object', additionalProperties: false,
  properties: {
    built: { type: 'array', items: { type: 'string' } },
    compiled: { type: 'boolean' },
    evidence_path: { type: 'string' },
    blockers: { type: 'array', items: { type: 'string' } },
    // micro-decisions surfaced (ids of the banked fork rows) — see MICRO_DECISIONS
    decisions_surfaced: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
  },
  required: ['built', 'compiled', 'evidence_path', 'blockers', 'summary'],
}

// THE MICRO-DECISION DISCIPLINE (his ruling 2026-07-23: "the whole workflow should have
// micro-decision points like this that can be surfaced as they're encountered... it all
// helps accumulate taste"). EVERY stage, builders included: when you hit a genuine fork —
// two defensible readings of the brief, a taste call (tone, figure count, citation form),
// a scope call (drop-or-earn a serve) — bank it SMALL as a kind:"fork" row via POST
// /corpus/friction (by: your actor, owning_layer "generation", corpus per your brief,
// node "decision:<slug>", value = the question + why + the option you took), then PROCEED
// on your best reading — never block on a micro-decision. The row lands author-owed on his
// desk; his answers feed author_proxy's decision frames and the taste retrieval, so every
// ruled fork makes the next similar fork auto-resolvable. Echo banked ids in your return.
const MICRO_DECISIONS = `MICRO-DECISIONS: when you hit a genuine fork (two defensible
readings, a taste call, a scope call), bank it small as a kind:"fork" row via POST
/corpus/friction (by your actor, owning_layer "generation", node "decision:<slug>",
value = question + why + the option you took provisionally), PROCEED on your best reading,
and echo the banked ids in your return. Never block on a micro-decision; never leave one
unsurfaced — his answers accumulate the taste the proxy learns from.`

let converged = false
const rounds = []
for (let r = 1; r <= MAX && !converged; r++) {
  phase('Round')
  log(`round B${r}: builder packet fires (serial lane)`)
  const build = await agent(
    `You are the gen-4 BUILDER, actor "gen4-builder-B${r}", corpus ${corpus}, round B${r}.
${BRIEF}
${STORM}
Realize the next unrealized section-front of the plan into prose through the staged/dispatch
machinery (the plan's own order: the intro+bg front first, then forward), the register
firewall enforced at realization (physics register; custody struck). Resolve the intro-b3
binding blocker when you reach it (cite via the standing scholar permission, or reframe to
D9 — record which, with evidence). ${MICRO_DECISIONS}
ONE compile at the end to see the object. Bank round
evidence under paper_falqon/manuscript/reprojection/rounds/B${r}_build_evidence.md.
Return the structured round record.`,
    { label: `build:B${r}`, phase: 'Round', model: 'opus', schema: ROUND })
  if (!build) { log(`round B${r}: builder died — the journal holds; resume replays`); break }
  rounds.push(build)

  phase('Judge')
  const judge = await agent(
    `You are the NON-BUILDER JUDGE, actor "gen4-judge-B${r}" (builder was gen4-builder-B${r};
you defend nothing it made). Corpus ${corpus}, round B${r}. ${BRIEF}
${STORM}
Read the built object (${build.evidence_path} + the compiled artifact + the changed sections).
Rule as the three personas (stranger physicist front-to-back on the BUILT PROSE; referee vs
the done-criteria; register auditor vs LAW P8 on the rendered text), then the superego above
them (station wave-close, builder gen4-builder-B${r}; bank via superego.bank_verdict + the
personas via author_proxy.bank_ruling under YOUR actor). ${TELOS_Q}
${STRUCTURE_Q}
STANDS only if your honest answers carry it. Return the structured verdict with routed
defects named for a REFUTED and any steer_requests banked + echoed.`,
    { label: `judge:B${r}`, phase: 'Judge', model: 'opus', schema: VERDICT })
  if (!judge) { log(`round B${r}: judge died — resume replays the build free`); break }

  if (judge.verdict === 'REFUTED') {
    log(`round B${r} REFUTED: ${judge.routed_defects.length} defects route to B${r + 1}`)
    continue
  }

  phase('Gate')
  const gate = await agent(
    `You are the READABILITY GATE, actor "gen4-stranger-gate", a stranger holding none of the
project's graph. Corpus ${corpus}. ${STORM} One browser granted if the compiled PDF needs it;
prefer reading the built artifact directly. Read the WHOLE object front to back and answer
the chair questions (gen4_brief.md section 5): would you keep reading; where did you stop;
what is the story; is it self-contained. Then check the done-criteria (section 4) together
with your read. ${TELOS_Q}
${STRUCTURE_Q}
Bank your verdict via superego.bank_verdict (station candidate-lock, builder
gen4-builder-B${r}, actor gen4-stranger-gate). A FAIL blocks candidate lock regardless of
round verdicts. Return the structured verdict.`,
    { label: `gate:B${r}`, phase: 'Gate', model: 'opus', effort: 'high', schema: VERDICT })
  if (gate && gate.verdict === 'STANDS') {
    converged = true
    log(`PHASE B CONVERGED at round B${r} — the gate and the round judges stand together`)
  } else if (gate) {
    log(`gate REFUTED at B${r}: ${gate.routed_defects.join(' · ')} — routing back`)
  }
}

return {
  converged,
  rounds: rounds.length,
  note: converged
    ? 'candidate stands at the gate — the WO consume + his chair remain HIS acts, never this script\'s'
    : 'not converged — the journal holds every completed round; resume continues from the kill point',
}
