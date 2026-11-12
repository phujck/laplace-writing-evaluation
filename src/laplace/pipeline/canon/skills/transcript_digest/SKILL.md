---
name: transcript_digest
description: "[EXPERIMENTAL] The mouth of the knowledge-digestion pipeline. Distil a raw transcript along several partitions (concepts, decisions, forks, todos, author-voice, retention) into a bounded skeleton of candidate stubs, write an immutable archival manifest, and move the raw transcript to archival storage. The judged distillation is host-run; the script does the mechanical partitioning. Feeds level_tender, then the_librarian."
---
# transcript_digest

**Status: [EXPERIMENTAL]**

## Purpose
Raw transcripts (recorded conversations, trip notes, working sessions) carry knowledge
in a form the conceptric cannot ingest directly. This is the first stage of the
**knowledge-digestion pipeline** ([the structure](canon://workflow/knowledge_digestion.md)):

> raw transcript -> **digest** (here) -> [`level_tender`](canon://skills/level_tender.md)
> (locate + lift/lower) -> [`the_librarian`](canon://agents/the_librarian.yaml)
> (recommend couplings) -> the conceptric. The raw transcript is archived for provenance.

**There are two mouths now, not one.** Since 2026-08-20 a *recorded call* takes a different road:
`scripts/ingest_otter.py` normalises an Otter export zip into
`evidence/intake_queue/call_<date>_<slug>/` carrying the raw transcript, the raw summary, and a stub
`extraction.md`, from which a session reconstructs a judged extraction into the contract stores. It
never calls digest.py and never touches the partitions below. Route by source: recorded calls take
the intake-queue road to the contract rows; documents, working sessions and soul material take the
digest road to `level_tender` and `the_librarian`. Sending a call transcript down this pipe puts
meeting content into the conceptric stub stream, which is the wrong store for it.

It distils a transcript along several **partitions** at once - the same information read
through different lenses - because one pass produces several typed streams, not one
summary.

## The partitions
- **concepts** - the substantive declarative residue, the candidate knowledge stubs that
  become conceptric / corpus entries (the stream `level_tender` then locates).
- **decisions** - what was settled, the author's calls.
- **forks** - what was deferred or left open (recorded open, not lost).
- **todos** - next moves and actions.
- **author_voice** - first-person reflective material, the raw self signal (routes toward
  `soul/` and the voice corpus, never laundered).
- **retention** - outcomes (kept / rewritten-to-the-line / bypassed - `survived != earned`).

## What the backing does, and what it refuses
`scripts/digest.py` is **mechanical**, the digestion counterpart of `deep_corpus_scout`'s
skeleton: it segments the transcript into turns (carrying speaker attribution), classifies
each line into the partitions by marker heuristics, and emits a **bounded skeleton** of
candidate stubs per partition - plus an **immutable archival manifest** (id, sha256, bytes,
lines, turns, date, partition counts). With `--archive` it copies the raw transcript
verbatim to archival storage (the firewall pattern: raw stays archived, only distilled
stubs surface into the working conceptric). It will **not** distil a stub itself - distilling
the meaning of a candidate is an act of grounded judgement, host-run, never the script's
guess. Truncation is always stated, never silent.

```
python scripts/digest.py <transcript.md> --out <digest-dir> --archive archive/transcripts --id <id>
```

## The flow after digest
The concept candidates are distilled (host/agent) into stubs - each a claim plus an
essential summary - then handed to [`level_tender`](canon://skills/level_tender.md) to find
where in the conceptric each belongs and whether it sits at that level or should move up or
down. The keeper of local knowledge, [`the_librarian`](canon://agents/the_librarian.yaml),
applies the result and recommends the couplings. Only then, with the knowledge digested, does
the raw transcript rest in [archival storage](canon://workflow/knowledge_digestion.md) - kept
in case we ever need to test a distilled stub against its historic provenance.

## Relation to siblings
- `deep_corpus_scout` maps an unknown raw *document tree*; this digests a *transcript* of
  talk into typed partitions. Both emit a skeleton for judged distillation, never the
  distillation itself.
- `voice_corpus_reader` reads source material into the voice corpus by register; the
  `author_voice` partition here is the transcript's feed into that.
- `corpus_librarian` holds the distilled store the concept stubs land in.
