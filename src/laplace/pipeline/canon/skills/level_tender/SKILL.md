---
name: level_tender
description: "[EXPERIMENTAL] The level tender - the middle of the knowledge-digestion pipeline. Given a distilled stub, locate the piece of the conceptric it belongs to and judge its SCALE: place it at that level, lower it beneath a node it is a detail of, lift it to a coarser node that spans several clusters, or open a new region. The operational front of the growth rule - move knowledge between scales by judgement. Recommend-only; the_librarian applies."
---
# level_tender

**Status: [EXPERIMENTAL]**

## Purpose
A distilled stub out of [`transcript_digest`](canon://skills/transcript_digest.md) has to be
placed in the conceptric - and *placing* is not only "which cluster", it is "at which **level**".
The level tender is the piece that tends the scale axis: it finds where a stub belongs and
decides whether it sits there, or should move up or down the hierarchy. This is the operational
front of the growth rule (EIGEN_ARCHITECTURE Component 2 - co-activation becomes a layer, and a
layer can be split or merged), made into a per-stub judgement rather than a global re-clustering.

## The four actions
- **place** - the stub sits at the matched cluster's level; wire it in there.
- **lower** - the stub is a detail of, or a near-restatement of, one existing node; attach it
  beneath that node (or merge), rather than adding a sibling.
- **lift** - the stub cuts across several clusters; it is a candidate for a coarser node (an
  existing or new theme) that spans them - the signal that a new layer may be warranted.
- **new** - nothing in the conceptric shares its vocabulary; it opens a new region (place loose,
  propose a cluster).

## What the backing computes, and what stays judgement
`scripts/level_tender.py` reads the conceptric (the corpus `corpus.bib` and its
`keywords.yaml` taxonomy) and computes the **structural signal**: the stub's vocabulary overlap
with each cluster and with each individual reference. From those it reads the action -
*one node dominates* -> lower; *two clusters comparably strong* -> lift; *one cluster clean* ->
place; *nothing* -> new - and reports the top clusters and nearest references with scores. The
**decision is the level tender's to confirm**, and it is **recommend-only**: it never mutates
the store. The structural signal is the prompt, not the verdict - the judgement of whether a
lift truly earns a new layer is the discipline the growth rule defers to research, applied here
one stub at a time with a human-or-eigen gate.

```
python scripts/level_tender.py "<stub text>" corpus/corpus.bib [--cluster <hint>] [--json]
python scripts/level_tender.py --stub-file <f> corpus/corpus.bib --json
```

## Position in the pipeline
[`transcript_digest`](canon://skills/transcript_digest.md) (distil along partitions) ->
**level_tender** (locate + judge the scale) -> [`the_librarian`](canon://agents/the_librarian.yaml)
(apply the recommendation, propose the coupling for approval) -> the conceptric. The level tender
hands the keeper of local knowledge a placed, scale-judged stub rather than a loose fact.

## Guard rails
- **Recommend, never auto-mutate.** A wrong placement compounds, so the gate on what enters and
  *at what level* is deliberate. The level tender proposes; the librarian and the author decide.
- **Lift is a hypothesis, not a promotion.** A cross-cutting stub *suggests* a coarser node; it
  does not create one. Whether the layer is earned is the open growth-rule question.
- **Lower can mean merge.** A near-restatement of an existing node is not new knowledge - tending
  the level includes declining to add a duplicate.
