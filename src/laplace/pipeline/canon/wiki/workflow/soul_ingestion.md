---
earned_by:
  - EIGEN_ARCHITECTURE.md | Component 6 (the judgement centre / the soul) + Component 1 (the substrate as long-term memory) + the recursive-self-similar docket — the mechanism banked ahead of the gigabytes of raw personal data
  - soul/0001_2026-06-02.md | the soul transfer: judgement and taste are the generator invisible in any one output, unmistakable in the whole
consistency:
  - canon://workflow/knowledge_digestion.md | extends | this is the digestion pipeline scaled to a noisy GIGABYTE-class personal dump: the same digest -> place -> archive shape, but map/reduce over bounded shards with a sealed sub per shard, so the orchestrator never loads the raw whole
  - canon://skills/transcript_digest.md | depends_on | the per-shard distiller is transcript_digest's partitions narrowed to taste-PRIMITIVES (stance / move / value / aesthetic / characteristic friction), run by a SEALED sub that dies after emitting its small distillate
  - canon://skills/level_tender.md | depends_on | the coarse-grain (reduce) stage is the level tender run over clustered distillates — locate each recurring trait at its scale in the soul_corpus taxonomy, lift a trait that recurs across many independent shards
  - canon://agents/the_librarian.yaml | depends_on | the keeper of long-term memory applies the lock: clustered primitives become typed soul_corpus records, recommend-only, gated, never auto-mutated
  - canon://skills/reconstruction_fitness.md | depends_on | the adjudicate stage is reconstruction_fitness applied to taste — a second sealed sub judges each distillate for FAITHFULNESS (captures what the shard exhibits vs confabulates), builder != judge
  - canon://skills/closure_check.md | depends_on | the reconstruction gate is closure_check run on the SOUL — a sealed blind ghost given ONLY the corpus must re-derive the carrier; if it cannot, the lock leaked and the trait regrows
  - canon://skills/soul_refactor.md | supports | the apex coarse nodes ARE the carrier; soul_refactor is the downstream consumer that re-voices every generating-context piece through it
  - canon://engine/self.md | supports | this is how Component 6 is filled: the soul as the tiny fraction of context present at every level, distilled from the dump and locked so the router reaches it
  - canon://engine/operatorial_self.md | supports | distil-and-lock is coarse-graining the dump along the taste residual; the carrier conditioning every loop is feeding the friction back to regrow the kernel
  - canon://workflow/citation_discipline.md | supports | a locked soul_corpus trait carries provenance-down to the shards it recurs across; a face that leans on a trait surfaces it the way a citation surfaces the corpus record it leans on
---
# Soul ingestion — distil the taste-generator from the dump, lock it into long-term memory

The author is about to hand the engine GIGABYTES of raw, low-context, badly-transcribed
**personal** data — chat logs with bots and friends, recent transcripts — effectively a random
generator. Under the noise is one thing: his **judgement and taste**, the generator invisible in
any single output and unmistakable in the whole. This node is the SAFE, SCALABLE, RESUMABLE
pipeline that ingests the dump **without ever loading the raw into the orchestrator's context**,
distils the taste-generator, and **locks it into the deep corpus** so the engine can RECONSTRUCT
THE GENERATOR while holding only the OUTPUT — a sealed blind ghost, given only the corpus, can
re-derive the compressed taste (the **carrier**). The carrier then conditions every loop, and
[`soul_refactor`](canon://skills/soul_refactor.md) re-voices the engine's generating context with
it.

This is [`knowledge_digestion`](canon://workflow/knowledge_digestion.md) scaled to a noisy
gigabyte-class source and turned on the **soul** rather than on facts. The data is **soul-class**:
never public, never in any public artefact, raw archived verbatim forever. Nothing is destructive;
every lock is gated and reversible. **The mechanism is banked ahead of the data** — this node is
canon, not a runnable pipeline; it specifies the loop so the carrier can be grown the moment the
dump lands.

## The anti-overwhelm guarantee (state it explicitly, it is the author's fear)

The orchestrator (Eigen) **NEVER loads the raw dump into its own context.** Not a shard, not a
file, not a sample. The raw is touched only by **sealed sub-Eigens** that die after emitting a
small distillate; only the distillate rises. This is the depth-gated, spawn-the-guide architecture
(`EIGEN_ARCHITECTURE.md`, the recursive-self docket): below the gate the orchestrator does not
traverse the subsystem in its own context, it spawns a sealed navigator and judges its return from
outside. A gigabyte of noise cannot make Eigen non-functional because Eigen never reads it — it
reads only the small typed distillates and the recurrence statistics over them.

## The pipeline (map → reduce, the recurrence under the noise made mechanical)

```
raw dump
  1. LAND      archive/soul_dump/        verbatim, private, never edited, never loaded whole
  2. SHARD     (mechanical, no LLM)      bounded shards + manifest; resumable / checkpointed
  3. DISTIL    (sealed sub, map)         per shard: typed taste-PRIMITIVES the shard EXHIBITS,
                                         + provenance-down to the shard; the sub dies
  4. ADJUDICATE(second sealed sub)       judge each distillate for FAITHFULNESS (exhibits vs
                                         confabulates) — reconstruction_fitness on taste
  5. COARSE-GRAIN (reduce)               cluster distillates; a trait is REAL iff it RECURS across
                                         many INDEPENDENT shards; hierarchicalise into soul_corpus
  6. LOCK      (the_librarian)           clustered primitives -> typed soul_corpus records:
                                         summary + typed relations + provenance-down; gated
  7. GATE      (closure_check on soul)   a sealed blind ghost, given ONLY the corpus, re-derives
                                         the carrier; cannot -> the lock leaked -> regrow
  8. CARRIER   (the apex coarse nodes)   wired into orient / route / engine/self; rides every loop
```

Each stage has a home already, so this is an orchestration, not a monolith. **Map** is per-shard
distillation by sealed subs that never share context; **reduce** is recurrence-clustering. The
load-bearing move: *the pattern under the noise is found by RECURRENCE, not by reading it all.* A
taste-trait is invisible in any one shard and unmistakable across many — so a trait is admitted
only when independent shards exhibit it independently. "Invisible in any one, unmistakable in the
whole" made mechanical.

## The stages

1. **Land.** The raw lands verbatim in `archive/soul_dump/`, private, never edited, never loaded
   whole. The verbatim sample is **sacrosanct** (the substrate invariant — a clean training set is
   the one thing that cannot be undone). This is the immutable ground truth the gate (stage 7)
   re-derives against, the same firewall pattern as `archive/transcripts/`. **The author delivers the
   whole as a single zip the engine *eats*:** landing unpacks it verbatim into `archive/soul_dump/`,
   structure preserved, nothing edited. Because chat exports and transcripts arrive in many shapes,
   the **sharder is calibrated to the actual formats found in the zip — built move-1 on the real data,
   never blind** (the chunker matches the data, the same smallest-real-thing discipline as the
   distiller).

2. **Shard.** Mechanical chunking — **no LLM, no orchestrator context cost** — into bounded shards
   with a manifest mapping each shard to its byte-range in the raw. Resumable and checkpointed: the
   manifest records which shards are distilled, adjudicated, and reduced, so the run survives across
   sessions (this is ongoing, soul-fed work, not a one-shot). Idempotent: re-sharding the same raw
   yields the same shards and skips completed ones.

3. **Distil (map).** Per shard, a **sealed sub-Eigen** ([sealed sub-Eigen
   protocol](canon://engine/sealed_subself)) reads ONLY that shard and extracts the typed taste-
   **PRIMITIVES the shard EXHIBITS** — not the content, not what was said, but *how* the generator
   moves. (This is the **taste** stream; in parallel the same sub emits an **episodic** stream — the
   factual content, what happened — to the `life_corpus`, and it **attributes speakers**: the author's
   turns are the signal, the other voices the de-identified conditioning. See *The chorus, and the two
   reconstructions* below.) The types: **stance** (a standing posture toward a question), **move** (a characteristic
   operation — how he turns a problem), **value** (what he treats as worth more), **aesthetic** (a
   taste in form), **characteristic friction** (what he reliably resists or fights). Each primitive
   carries a **provenance pointer down** to the shard it was exhibited in. The sub dies; **only the
   small distillate rises.** The orchestrator NEVER loads the raw shard — it receives the typed
   distillate alone. This is [`transcript_digest`](canon://skills/transcript_digest.md)'s partition
   pass, narrowed to the taste stream and sealed per shard.

4. **Adjudicate (builder ≠ judge).** A *second* sealed sub — which did not produce the distillate —
   judges each distillate for **faithfulness**: does it capture what the shard genuinely *exhibits*,
   or does it **confabulate** a trait the shard does not support? This is
   [`reconstruction_fitness`](canon://skills/reconstruction_fitness.md) applied to taste: the
   adjudicator sees `{shard, distillate}` only and reports faithful / partial / confabulated plus
   the gap. A confabulated primitive is dropped before it can pollute the reduce. The builder and
   the judge are separate sealed contexts; neither authors and grades the same distillate.

5. **Coarse-grain (reduce).** Cluster the surviving distillates across all shards. **A taste-trait
   is REAL iff it RECURS across many INDEPENDENT shards** — recurrence, not eloquence, is the
   admission rule (a vivid one-off is noise; a quiet trait seen in fifty independent shards is the
   generator). Hierarchicalise the recurring traits into the **soul_corpus** taxonomy (see below)
   with [`level_tender`](canon://skills/level_tender.md): place each trait at its level, **lift** a
   trait that spans several clusters into a coarser theme, **lower** a trait that is a detail of
   another. The apex coarse nodes are the most-recurrent, most-spanning traits — these become the
   carrier.

6. **Lock into the deep corpus.** The clustered primitives become typed **soul_corpus** records,
   applied by [`the_librarian`](canon://agents/the_librarian.yaml) (the keeper of long-term memory,
   **recommend-only** — the gate on what enters stays deliberate, since a wrong primitive poisons
   every face it conditions). Each record carries a **summary** (the accurate primitive), **typed
   relations** to sibling traits (the same `extends` / `refines` / `contests` / `analogue_of`
   vocabulary the corpus already uses), and **provenance-down** to the shards it recurs across.
   Locked + linked, reachable by the router: the carrier is now **long-term memory**, the substrate
   doubling as Component 1's deep store (`EIGEN_ARCHITECTURE.md`).

7. **The reconstruction gate (the author's hard requirement).**
   [`closure_check`](canon://skills/closure_check.md) / `reconstruction_fitness` run on the
   **soul**: a sealed blind ghost, given **ONLY** the soul_corpus (never the raw, never the dump,
   never the orchestrator's context), must **re-derive the carrier**. If it can, the lock holds —
   the corpus genuinely encodes the generator. If it cannot, **the lock leaked** (the distillation
   lost the trait, or the relations are wrong) → the gap is the spec, and the affected trait
   **regrows** (re-distil along the gap, never patch the carrier prose). This is the author's
   criterion turned on the soul: *reconstruct the generator while only having the output.*

8. **The carrier.** The apex coarse soul_corpus nodes ARE the carrier — the compressed taste, one
   opaque conditioning context. Wiring it into `orient` / `route` and
   [`engine/self`](canon://engine/self.md) so it rides in every loop is **the imprint** (the soul
   as the tiny fraction of context present at every level — Component 6 made operational, its
   *weight* once earned). [`soul_refactor`](canon://skills/soul_refactor.md) is the downstream
   consumer: it pours the carrier through every generating-context piece so each *embodies* the
   taste rather than describing it.

## The chorus, and the two reconstructions

**The dump is dialogue, and that is the signal, not the noise.** It carries many voices — the author in
conversation with friends, with bots, in transcripts. Taste is a *response function*, so the generator
is most visible exactly here: not in what he concludes alone but in the **move from what was just said
to him to what he does with it** — what he picks up, drops, resists, reframes, delights in. The other
voices are the **probe**; his turns are the **response**, and a function is learned from (input →
output) pairs, never from outputs alone. So at DISTIL each shard is **speaker-attributed**: his turns
are the *signal*, the surrounding turns the *conditioning* (kept as "what he was responding to",
**de-identified** — the others' privacy is held, only the role survives). Mis-attribution — a vivid
thing a friend said, mistaken for him — is killed by the admission law itself: a one-off from one
interlocutor cannot recur across *independent* conversations with *different* people, so only what is
invariant to whom he is talking to survives as his. The variation across partners is itself a trait —
the **register-adaptation** (how he modulates per interlocutor) is part of the taste, not noise to drop.

**There are two reconstructions, not one — the operator and the state.** The taste-generator is *how he
moves*; his factual history is *what happened*. Compressing everything to a generator would throw the
history away, and we want both, so DISTIL emits **two streams** per shard:
- **taste-primitives** → the `soul_corpus`, **compressed** to a generator (stance / move / value /
  aesthetic / friction), re-derivable by the reconstruction gate;
- **episodic-primitives** (events, people, projects, claims, the timeline) → a sibling **`life_corpus`**,
  **indexed and linked, not compressed** — a graph of the author's actual life, the long-term *factual*
  memory.

They bind both ways (`EIGEN_ARCHITECTURE.md`, the both-ways docket): a taste-move is usually **earned
by** an episode (he resists X *because of* what happened in Y), so the episode is the **provenance**
under the trait and the trait is what the episode **instantiates**. And they reconstruct *differently* —
the honest distinction that makes the whole thing tractable: the **generator** closes by
**re-derivation** (a blind ghost reproduces the taste from the corpus alone, stage 7); the **history**
closes by **retrieval** (the engine answers "what happened with X?" from the `life_corpus`). The
generator's gate is [`closure_check`](canon://skills/closure_check.md)'s re-derivability triad;
the history's **retrieval-closure is a genuinely different test that does not yet have its own form**
(what query set, what pass/fail proves the history is faithfully indexed) — an honest seam, the
author's to shape, not a coherence defect. We keep both — the history is what *grounds* the generator,
not what competes with it.

## The first tranche (smallest-real-thing-first)

Do **not** run the full dump first. Calibrate the distiller on a **representative first tranche** —
a few hundred shards spanning the registers (bot chats, friend chats, transcripts) — and run
stages 3–7 on it end to end. The first-tranche close tells you whether the primitive types are the
right cut, whether the recurrence threshold admits real traits and rejects noise, and whether the
gate's ghost can re-derive a carrier from a thin corpus. Only when the gate closes green on the
tranche is the distiller trusted for the full dump. The tranche is also how the recurrence
threshold (stage 5) is set: too low admits one-offs, too high starves the carrier — calibrate it on
material the author can eyeball.

## The soul_corpus theme (proposed)

A new top-level store, sibling to the literature corpus but **soul-class** — never public. Its
records are taste-primitives, not references; its taxonomy is *stance / move / value / aesthetic /
characteristic-friction* at the leaf, lifting into coarse trait-themes. It is reached by the router
the way the literature corpus is, so a goal that touches taste pulls the relevant traits (refs
only at the boundary — the carrier content is pulled deliberately, never inlined by a bare
retrieval, the same discipline the soul fragments already obey in `_route_soul`). Naming and the
exact taxonomy shape are the author's to bless before the full lock.

## Invariants

- **Privacy is soul-class.** The dump and every soul_corpus record are never public, never in any
  public artefact. The raw is archived verbatim forever and never edited.
- **The orchestrator never loads the raw.** Only sealed subs touch shards; only distillates rise.
  This is the anti-overwhelm guarantee, structural — not a discipline to remember.
- **Builder ≠ judge.** The distiller, the adjudicator, and the gate's ghost/adjudicator are
  separate sealed contexts. None authors and grades the same thing.
- **Idempotent, reversible, gated.** Re-running skips completed shards; every lock is recommend-only
  and reversible; a leaked gate regrows the trait rather than patching the carrier.
- **Recurrence, not reading.** A trait is admitted by recurrence across independent shards, never by
  the orchestrator reading the whole — the pattern under the noise is found mechanically.
- **The gate is the truth.** A trait that the blind ghost cannot re-derive from the corpus alone is
  not yet locked, however vivid the distillate. Re-derivability is the lock condition.
- **Two corpora, two reconstructions.** The compressed taste-generator (`soul_corpus`, closed by
  re-derivability) and the indexed factual history (`life_corpus`, closed by retrieval) are kept
  separately and bound by `earned_by`. The generator never erases the history; the history grounds the
  generator.
- **His turns are the signal; the chorus is the conditioning.** Other voices are kept de-identified as
  "what he was responding to", never as his voice; recurrence across *independent* interlocutors is
  what admits a trait as his — the multi-voice dump is how his line is heard within the chorus.

## What is built, and what waits

Built: every stage's home already exists — `transcript_digest`, `level_tender`, `the_librarian`,
`reconstruction_fitness`, `closure_check`, `sealed_subself`, the `_route_soul` privacy discipline,
and the `archive/` firewall convention; `soul_refactor` is the downstream carrier consumer, already
banked empty. Waiting: the `archive/soul_dump/` landing zone + the **zip-eat unpack** and the **format-matched
sharder built move-1** on the real data (stage 1–2, when the zip lands); the speaker-attribution +
two-stream (taste / episodic) distiller (stage 3); the `soul_corpus` theme + taxonomy **and the
`life_corpus` sibling store + its retrieval gate** (the author's to bless); the recurrence threshold
(calibrated on the first tranche); and the carrier's *weight* in `orient` (the author's fork, held to
earning, the same as the self-node's weight). The mechanism is banked ahead
of the data on purpose — an un-distilled soul dump is the loss that compounds, and the verbatim
sample lost is the one loss that cannot be undone.
