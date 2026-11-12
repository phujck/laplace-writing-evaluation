# Knowledge digestion — from raw transcript to the conceptric

A mental digestion engine. Raw experience (recorded conversations, trip notes, working
sessions) arrives as transcripts, and the engine has to turn that into knowledge located at the
right place and the right scale of its conceptric, then keep the raw record for provenance. This
node names that pipeline - the structure the author asked for - and wires its stages together.

## The pipeline

```
raw transcript
   -> digest        (transcript_digest)  distil along partitions -> candidate stubs + archival manifest
   -> distil        (host/agent)         turn concept candidates into accurate stubs
   -> tend the level (level_tender)       locate in the conceptric; place / lower / lift / new
   -> keep          (the_librarian)       recommend the coupling; the keeper of local knowledge applies
   -> conceptric    (corpus + canon)      the stub wired in at its judged level
   -> archive       (archive/transcripts) the raw transcript rests, immutable, for historic provenance
```

Each stage is a node that already has a home, so the pipeline is an orchestration, not a new
monolith.

This pipeline runs **forward only** - it digests and places, but never checks that the placement
held. Its inverse, the **assess** half, is
[`reconstruction_fitness`](canon://skills/reconstruction_fitness.md): reconstruct the object from
the digest alone, judge the ghost against the archived original, and read the gap as the fitness on
both the memory and the level tender's neighbour-wiring. The archive (stage 5) is precisely the
immutable ground truth that assess scores against. Together they close the orient -> synthesize ->
execute -> **assess** loop for memory.

## The stages

1. **Digest** - [`transcript_digest`](canon://skills/transcript_digest.md) distils the transcript
   along several **partitions** at once (concepts, decisions, forks, todos, author-voice,
   retention), because one transcript carries several typed streams. It emits a bounded skeleton
   of candidates and an immutable manifest, and moves the raw transcript to archival storage. It
   does not distil the meaning - that is judgement.

2. **Distil** - the concept candidates are read into accurate stubs (a claim plus an essential
   summary), the same grounded judgement the corpus demands - a wrong primitive poisons every
   citing face, so the stub is host-distilled, never auto-generated.

3. **Tend the level** - [`level_tender`](canon://skills/level_tender.md) locates each stub in the
   conceptric and judges its **scale**: place it at the matched level, **lower** it beneath a node
   it is a detail of, **lift** it to a coarser node that spans several clusters, or open a **new**
   region. This is the operational front of the growth rule - moving knowledge between scales by
   judgement, one stub at a time, rather than a global re-clustering.

4. **Keep** - [`the_librarian`](canon://agents/the_librarian.yaml), the keeper of local knowledge,
   receives the placed, scale-judged stubs and recommends the couplings (the corpus record, its
   cluster, its typed relations) for approval. It does not auto-mutate the store.

5. **Archive** - once the knowledge is digested and located, the raw transcript rests in
   `archive/transcripts/` (immutable, with its manifest), kept in case a distilled stub ever needs
   to be tested against its historic provenance. This is the firewall pattern - the raw stays
   archived, only the distilled stubs surface into the working conceptric.

## Where it sits in the architecture

This is Component 2 (the growth rule) and Component 4 (the budget - what is worth keeping, at what
access cost) made operational for *raw experience*. The
[corpus](canon://skills/corpus_librarian.md) is the long-term memory the stubs land in; the
[generative loop](canon://engine/generative_loop.md) is the discipline they are distilled under;
the [self](canon://engine/self.md) is what decides, through the level tender's judgement, where a
piece of knowledge belongs. The fully **endogenous** version of the level tender - re-clustering
the whole conceptric on its own statistics, not one stub at a time with a gate - is the deferred
growth-rule analyser, and this pipeline is the host-mediated, recommend-only path that accumulates
the history that analyser will one day read.

## What is built, and what waits

Built: `transcript_digest` and `level_tender` with their backings, the librarian handoff, and the
`archive/transcripts/` convention - proven end-to-end on a synthetic transcript. Waiting: the real
trip transcripts (ingested when they arrive), the voice-corpus routing of the `author_voice`
partition, and the endogenous re-clustering. The mechanism is banked ahead of the data, on purpose -
un-digested experience is the loss that compounds.
