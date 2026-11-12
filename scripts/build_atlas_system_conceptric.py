#!/usr/bin/env python
"""Build the ATLAS-SYSTEM conceptric — the mutable source of truth for how the engine
stores and reconstructs itself, authored as a conceptric-class object rather than as
design prose (his standing ruling, 2026-07-21: "you're making all these design plans as
prose markdowns that rot ... they might benefit from a _conceptric_?").

The house form and the record shape are taken verbatim from the precedent,
``scripts/build_design_conceptric.py`` + ``corpus_friction/design-interface.jsonl``:
a corpus friction ledger of typed rewire records

    {id, ts, kind:add-node|add-edge, node, target, value, by, status,
     parent, node_kind, essence, ref}

which ``corpus_ingest.corpus_network`` reconstructs into the {nodes, reach, ...} the
existing DOWN operators serve. No parallel format.

DIFFERENCE FROM THE PRECEDENT: the design conceptric PARSES its sources (a design doc, a
promise ledger, contract yaml). This one cannot — its source is the running system, read
by two dispatched readers whose file:line dossiers were then re-verified against the code.
So the literals live IN THIS SCRIPT, exactly as the task ordered ("keep it simple — the
ledger literals live in the script"), and the script is the one place they may be edited.
The ledger is a projection of the tables below; edit the tables, re-emit, never hand-edit
the .jsonl.

THE THREE-REGISTER LAW (the author's explicit ask). Every node's essence opens with its
register and nothing blurs them:

  * RUNNING   — in the code today; the ref is file:line, numbers are measured.
  * DESIGNED  — in a doc or a work order, not in code; the ref is the doc.
  * MIGRATION — the bridge between the two, including what waits on the house GPU.

Today's engine is CPU-only end to end: clustering is sklearn spectral behind a PSU guard,
the embedder is ONNX-CPU bge-small. Nothing in the RUNNING register touches a GPU. A GPU
appears only under DESIGNED / MIGRATION, and is labelled so.

MATHEMATICS REFS: the mathematics cluster refs the companion note by SUBSECTION,
``MATHEMATICS:§n.m``, which is the note's own convention — it writes a bare ``§n`` only when
it means a whole top-level section, and every claim a math node makes is subsection-level.
Each entry in ``_MATH`` below was checked against the note's actual ``###`` headers, not
against an assumed numbering; ``--check-math`` re-verifies that every cited subsection
exists in the note, so this contract cannot rot silently.

DETERMINISM / IDEMPOTENCE: records are emitted in a fixed order with stable ids
(``AS-NNNN``) and a fixed ts, so two runs produce a BYTE-IDENTICAL ledger. Non-build
records already on the ledger (a human deposit through /corpus/friction) are preserved
ahead of the rebuilt block, mirroring the precedent's replayability discipline.

    python3 build_atlas_system_conceptric.py --ledger atlas-system.jsonl
    python3 build_atlas_system_conceptric.py --ledger atlas-system.jsonl --check
    python3 build_atlas_system_conceptric.py --check-math
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# constants — the one place names/paths live
# ---------------------------------------------------------------------------

CORPUS = "atlas-system"                      # the /conceptric ?corpus= name
BUILD_TAG = "build:atlas-system-conceptric"  # our records' `by`; others are preserved
FIXED_TS = "2026-08-16T00:00:00"             # the authoring date — stable across runs
LEDGER = f"corpus_friction/{CORPUS}.jsonl"   # in-repo home once this lands

ROOT = "paper://"                            # atomise_paper's apex (base leaf)
GOAL = "goal:atlas-system"

ESSENCE_CAP = 320                            # the authored bound, asserted at emit

REGISTERS = ("RUNNING", "DESIGNED", "MIGRATION")
# The three-register law is MECHANICAL here: every node's essence must open with one of the
# three registers, except the handful of scaffold nodes that carry no claim about the system
# (the three register definitions themselves and the cluster that holds them). build_records
# raises if any other node is untagged, so the law cannot rot into prose.
_SCAFFOLD = {"cluster:registers", "register:running", "register:designed", "register:migration"}

# the logical-kind each atlas-system type projects onto (corpus_ingest.LOGICAL_KINDS — the
# add-node gate's taxonomy; the native type rides the id prefix + essence).
KIND = {
    "goal": "goal",
    "cluster": "support",
    "stage": "derivation-step",   # a pipeline stage IS a step
    "fact": "support",
    "math": "definition",         # a mathematical object
    "site": "technique",          # an intelligence site is a reusable move
    "cost": "result",             # a measured wall / flat cost
    "register": "definition",
    "law": "postulate",
    "seam": "support",
    "organ": "technique",         # a designed loop organ
    "fork": "postulate",          # an author-reserved decision
}

# ---------------------------------------------------------------------------
# the mathematics numbering — the contract with MATHEMATICS.md
#
# Each `sec` is a SUBSECTION of the companion note, verified against its `###` headers.
# The note's top-level sections are: 1 the embedding map, 2 the affinity and the spectral
# split, 3 tree combinatorics, 4 incremental assignment, 5 complexity, 6 the mechanical
# gate, 7 the wake projection, 8 what is designed. `--check-math` asserts every `sec` here
# resolves to a real header in the note.
# ---------------------------------------------------------------------------

_MATH: list[tuple[str, str, str]] = [
    # (node id suffix, subsection number, essence body)
    ("embedding-map", "1.1",
     "The embedding map: text to a 384-dim unit vector under bge-small-en-v1.5, run as "
     "ONNX on CPU. One bounded handle string per node, capped at 480 chars for bge's "
     "512-token window. The whole geometry the system reasons in is this map's image."),
    ("cosine", "1.2",
     "Cosine similarity. Vectors are unit-normalised, so cosine is a bare dot product, and "
     "clustering, descent and the wire gate score exactly that. The router is the exception: "
     "a trained metric M rides the query, so its scores are a bilinear form, off the cosine "
     "scale by up to 8 percent."),
    ("quantisation", "1.3-1.4",
     "Int8 quantisation: each float vector stored as base64 bytes plus one float scale. "
     "The lossy compression that turns a 96MB float store into a 15.7MB served one; the "
     "error it introduces is below the thresholds any consumer discriminates at."),
    ("affinity", "2.1",
     "The affinity matrix A = (X Xt + 1)/2 over unit rows, diagonal forced to 1 — cosine "
     "rescaled from [-1,1] to [0,1] so it is a valid non-negative affinity. Dense and "
     "n-by-n: this matrix is the reason the full fold costs what it costs."),
    ("spectral", "2.2",
     "Spectral clustering on the precomputed affinity: eigenvectors of the graph "
     "Laplacian, then kmeans in that embedding. Applied recursively top-down, so the "
     "concept tree is a hierarchy of spectral cuts rather than one flat partition."),
    ("silhouette", "2.3",
     "Silhouette score as the model-selection rule for k. k is swept over [2, min(8,n-1)] "
     "and the best silhouette wins. Chosen over the eigengap because the eigengap is "
     "degenerate on dense bge geometry — measured, not assumed."),
    ("centroid", "4.2-4.3",
     "The cluster centroid: unit-normalised mean of direct leaf members. A cluster with no "
     "direct leaves banks none and its centroid is DERIVED at read time as the "
     "leaf-count-weighted mean of its children's centroids, recursively."),
    ("grade-height", "3.3",
     "Grade as structural height: a leaf is grade 0, an internal node is 1 + max(child "
     "grades). Not a judgement and not a depth — a coarseness coordinate computed bottom-up "
     "in one pass. The live tree tops out at a single grade-10 apex."),
    ("beam-search", "5.3",
     "Level-synchronous beam search over the tree: score the frontier by cosine against "
     "centroids, keep the top beam, materialise only the kept clusters' leaves, expand "
     "children as the next frontier. Bounded work per query, independent of corpus size."),
    ("path-heat", "5.5",
     "Path-inherited heat in the router: g = max(own score, 0.9 x parent heat). A child of a "
     "hot parent stays warm even when its own handle scores poorly, so the descent does not "
     "amputate a good subtree on one bad summary line."),
    ("decision-band", "6.1-6.2",
     "The three-way decision band on cosine: at or above 0.70 wire, at or below 0.50 noise, "
     "the middle escalates. Validated at AUC 0.978 on 118 banked verdicts with zero "
     "false positives and zero real edges lost. An F1 knob, tunable, not a constant of nature."),
    ("content-hash", "1.5",
     "Content-hash identity: a node re-embeds only when the sha1 of its handle text moves, "
     "and a cluster id is the sha1 of its sorted member ids. Both give idempotence — an "
     "unchanged thing keeps its name and costs nothing to refold."),
    ("drift-fraction", "4.4",
     "The drift metrics that decide incremental versus full: dirty fraction "
     "(added+changed+removed)/|residue| against a 0.20 threshold, and lens reshuffle as the "
     "symmetric difference of the banked lens_pairs set. Cheap scalars gating an expensive fold."),
    ("keyword-promotion", "3.5",
     "Keyword recurrence promotion: a keyword appearing in at least 2 children ascends to "
     "the parent, capped at 12, with a deterministic count-desc/keyword-asc tie-break so the "
     "result does not depend on hash seed. How a coarse handle acquires its vocabulary."),
    ("budget-displacement", "7.1",
     "Budget displacement: a payload bounded by a character count, kept under bound by "
     "evicting oldest-ingested items first and replacing each with a descend handle. "
     "Truncation is never silent — what left is named and remains reachable."),
]

# ---------------------------------------------------------------------------
# the nodes — (id, type, parent, essence body, ref)
# ---------------------------------------------------------------------------

_CLUSTERS: list[tuple[str, str]] = [
    ("cluster:write-side",
     "RUNNING — the write half: everything that turns files, records and papers into "
     "handles and vectors, before any folding happens."),
    ("cluster:fold",
     "RUNNING — the fold: clustering the residue into concepts, building the graded tree, "
     "persisting it, draining the wire frontier, reindexing by name."),
    ("cluster:read-side",
     "RUNNING — the read half: the two consumers of the persisted tree, query descent and "
     "the wake's tree-only semantic projection."),
    ("cluster:mathematics",
     "RUNNING — one node per mathematical object the system actually computes. Sections of "
     "the companion MATHEMATICS note; the numbering here is the contract with that file."),
    ("cluster:intelligence-sites",
     "RUNNING — the exact places where a model, rather than a rule, decides. Three of them, "
     "and the law that keeps the count at three."),
    ("cluster:scaling",
     "RUNNING — the cost structure: the walls that grow with corpus size, and the costs "
     "that stay flat. Measured numbers only."),
    ("cluster:registers",
     "The three-register discipline itself: RUNNING, DESIGNED and MIGRATION as first-class "
     "nodes, so a reader can never mistake a plan for a fact."),
    ("cluster:laws",
     "RUNNING — the standing structural laws this system holds itself to. Each was paid for "
     "by a failure and each is enforced at a named place in the code."),
    ("cluster:seams",
     "RUNNING — the open seams: five places where the system is honestly unfinished or "
     "unexplained, carried named rather than smoothed over."),
    ("cluster:restructuring",
     "DESIGNED — the closure sweep (DESIGN_2026-08-11_the-structuring-loop.md): the loop "
     "that would let descent residuals reshape the fold's geometry. Instrument-before-write; "
     "the fitness signal and phi stay HIS (F23)."),
]

_NODES: list[tuple[str, str, str, str, str]] = [
    # ---------------- write side -----------------------------------------
    ("stage:shard", "stage", "cluster:write-side",
     "RUNNING — shard_repo walks every tracked and untracked-not-ignored file and emits one "
     "handle per file: name, kind, one-line essence, up to 12 keywords, spine count, edges. "
     "Pure regex and json.loads, no model. 21,420 nodes live, 8-20s.",
     "src/laplace/self_shard.py:281-292"),
    ("stage:lenses", "stage", "cluster:write-side",
     "RUNNING — the lens phase unions extra leaf sources over the file shards: concept "
     "atoms, collaborators, the verbatim record floor, transcripts, structural ladders. "
     "Lens leaves bypass the text-extension gate because their readers open them directly.",
     "src/laplace/keeper.py:366-378"),
    ("stage:ledger-door", "stage", "cluster:write-side",
     "RUNNING — ingest() appends one grade-tagged, kind-tagged entry to CONCEPTRIC_LEDGER.md. "
     "Append-only; a retire entry drops a prior item from the READ while it stays on disk. "
     "This store is separate from the graded tree and is read only by reconstruct_self.",
     "src/laplace/self_corpus.py:358-375"),
    ("stage:paper-atomiser", "stage", "cluster:write-side",
     "RUNNING — atomise_paper walks main.tex and its inputs, cutting sections, labelled "
     "equations, figures with captions and bib entries into leaves plus an edge index. The "
     "finished-paper pipeline, parallel to the self pipeline, feeding the same tree builder.",
     "src/laplace/corpus_ingest.py:91-178"),
    ("stage:embed", "stage", "cluster:write-side",
     "RUNNING — ensure_embeddings embeds only nodes whose handle hash moved, storing int8 "
     "vectors in .self_embeddings.json. Every node, leaf and internal, is embedded from its "
     "HANDLE, never from raw content. The one model in the write path.",
     "src/laplace/embed_router.py:348-418"),
    ("fact:two-pipelines", "fact", "cluster:write-side",
     "RUNNING — there are two ingestion pipelines, not one: self/directory (shard, build_self, "
     "embed, driven by scripts/reembed.py) and finished-paper (atomise, build_tree, build_reach). "
     "keeper_ring calls build_self only as a cold-path fallback when no tree is on disk.",
     "src/laplace/keeper_ring.py:550"),
    ("fact:grade-duality", "fact", "cluster:write-side",
     "RUNNING — two unrelated things are called grade. The sharder's 0/1/2 is projection "
     "DEPTH per query (handle, spine, source) and is never stored. The keeper's grade is "
     "structural HEIGHT in the tree and is stored. Conflating them misreads the whole store.",
     "src/laplace/keeper.py:104-111"),

    # ---------------- fold ------------------------------------------------
    ("fold:upfold-incremental", "stage", "cluster:fold",
     "RUNNING — the default fold: new or changed residue leaves are assigned to their nearest "
     "existing cluster centroid by cosine. O(delta x clusters), no eigen anything, 9.5-16.8s "
     "measured. This path never runs spectral clustering.",
     "src/laplace/meaning_upfold.py:444-521"),
    ("fold:upfold-spectral", "stage", "cluster:fold",
     "RUNNING — the full rebuild: recursive spectral clustering over the whole residue, k "
     "chosen by silhouette, recursed until a subcluster is under 10 members or depth 6. Fires "
     "only on a structural move and only behind the PSU/deps gate.",
     "src/laplace/meaning_upfold.py:184-276"),
    ("fold:full-triggers", "fact", "cluster:fold",
     "RUNNING — five conditions escalate incremental to full: no or incompatible prior tree; "
     "version or backend mismatch; lens reshuffle past 0.20; dirty fraction past 0.20; a "
     "cluster emptied or breached the 10-member leaf cap. Otherwise incremental holds.",
     "src/laplace/meaning_upfold.py:500-519"),
    ("fold:spectral-gate", "fact", "cluster:fold",
     "RUNNING — the PSU guard. The full spectral branch runs only if LAPLACE_ALLOW_SPECTRAL "
     "is set or the box is the remote container, AND scipy and sklearn import. Otherwise the "
     "prior tree is kept and the skip is printed. His 2026-06-14 ruling: the box crashes otherwise.",
     "src/laplace/meaning_upfold.py:400-419"),
    ("fold:tree-build", "stage", "cluster:fold",
     "RUNNING — build_tree assembles the graded conceptric bottom-up from leaves plus a parent "
     "function that prefers the meaning cluster, then the lens parent, then the directory. "
     "Grade is height; keywords ascend by recurrence. Fully mechanical, O(n), 0.29-0.70s.",
     "src/laplace/keeper.py:104-190"),
    ("fold:persist", "stage", "cluster:fold",
     "RUNNING — write_tree_local writes .self_graded.json, 18.6MB, gitignored. This file is "
     "exactly what the next wake's load_network reads; the committed SELF_GRADED_INDEX.md is "
     "a separate upper-grade skeleton written only by keeper.main. 0.25-0.86s.",
     "src/laplace/keeper.py:289-292"),
    ("fold:wire-drain", "stage", "cluster:fold",
     "RUNNING — the cross-link drain. Dedupe the proposal frontier, recompute cosine against "
     "current embeddings, apply the three-way band, bank every verdict to .wire_verdicts.jsonl, "
     "fold accepted query tokens into learned keywords, write briefs for the escalate band.",
     "scripts/drain_proposals.py:33-45"),
    ("fold:wire-gate-a", "fact", "cluster:fold",
     "RUNNING — Gate A: if the deduped proposal frontier is empty the whole wire phase is "
     "skipped and no wire ledger is touched, logged as a deliberate skip. Four of five banked "
     "timing rows took this path at 0.0002s; the nonempty row cost 1.68s.",
     "scripts/reembed.py:126-137"),
    ("fold:reindex", "stage", "cluster:fold",
     "RUNNING — rewrite the committed SELF_SHARD_INDEX.md, the by-name lookup trace, distinct "
     "from the graded store. It exists because build_self historically never touched it, so "
     "new files landed in the tree yet did not surface by name. 7.3-37.9s measured.",
     "scripts/reembed.py:146-151"),

    # ---------------- read side -------------------------------------------
    ("read:descent", "stage", "cluster:read-side",
     "RUNNING — Descender.descend runs a level-synchronous beam search: embed the query, score "
     "frontier clusters against centroids, keep the top beam, materialise only those clusters' "
     "leaves from source text, recurse. Default beam 4; every precondition failure refuses loudly.",
     "src/laplace/recursive_read.py:488-597"),
    ("read:beam-bench", "fact", "cluster:read-side",
     "RUNNING — the banked beam bench, 1,982 clusters and 12,299 leaves over 40 queries: beam 2 "
     "top1 0.500; beam 4 top1 0.850 at 38.6 leaves and 1.45s; beam 8 top1 0.950 at 100.9 leaves; "
     "beam 16 top1 1.000. Brute oracle is 1.000 at 12,295 leaves in 0.015s.",
     "src/laplace/recursive_read.py:50-62"),
    ("read:wake-projection", "stage", "cluster:read-side",
     "RUNNING — top_of_map builds the wake's semantic block from the tree's SHAPE only: parse "
     "the tree with floats dropped and centroids collapsed to booleans, then split the heaviest "
     "cluster repeatedly until 8 handles are covered. No embedder, no numpy, no network.",
     "src/laplace/recursive_read.py:175-252"),

    # ---------------- intelligence sites ----------------------------------
    ("intel:law", "law", "cluster:intelligence-sites",
     "DESIGNED — the law over the sites below, stated 2026-08-16 and not yet in any doc: put "
     "intelligence only where geometry or ambiguity make it irreplaceable, and ledger its "
     "verdicts so they become tomorrow's thresholds. Three sites qualify today.",
     "MATHEMATICS:§6.2"),
    ("intel:embedder", "site", "cluster:intelligence-sites",
     "RUNNING — the embedder as INSTRUMENT, not judge. bge-small runs as fixed local ONNX "
     "inference over handle text; it produces coordinates and takes no decisions. Vendored "
     "in-repo and unpacked to a local cache, so there is zero network egress at fold time.",
     "src/laplace/embed_router.py:47-115"),
    ("intel:wire-jury", "site", "cluster:intelligence-sites",
     "RUNNING — the wire jury: a deferred cheap model judging only the ambiguous middle band "
     "the mechanical gate refuses. It returns wire, grit or noise into the same verdict sink "
     "with method=jury. This is the ONE model-judgement site in the whole pipeline.",
     "scripts/drain_proposals.py:48-60"),
    ("intel:ledger-grade-kind", "site", "cluster:intelligence-sites",
     "RUNNING — the caller-supplied grade and kind at the ledger door. Nothing computes them: "
     "the writer decides at which grade a fact was missing and what kind it is. A human or "
     "model judgement frozen into an append-only record and read back mechanically forever.",
     "src/laplace/self_corpus.py:358-375"),
    ("intel:thresholds-from-verdicts", "fact", "cluster:intelligence-sites",
     "RUNNING — the law's own proof: the 0.70/0.50 band was not chosen a priori. It was fitted "
     "against 118 banked jury and mechanical verdicts and reported at AUC 0.978 with zero "
     "corruption. Yesterday's judgements literally became today's constants.",
     "src/laplace/embed_router.py:674-680"),

    # ---------------- scaling ---------------------------------------------
    ("scale:wall-spectral", "cost", "cluster:scaling",
     "RUNNING — the dominant wall. The full spectral fold is roughly O(n^2) in memory and worse "
     "in time: a dense n-by-n affinity plus a fit per candidate k per level. Measured 488.92s "
     "at n=21,420 and 1224.70s at n=21,339, against 9.5-16.8s for the incremental path.",
     "src/laplace/meaning_upfold.py:138-164"),
    ("scale:wall-tree-open", "cost", "cluster:scaling",
     "RUNNING — the open cost of reading. .meaning_tree.json is 21MB on disk; a full parse for "
     "descent costs about 0.28s and 29MB resident before a single query is answered. This is "
     "per-process, not per-query, and it grows with the corpus.",
     "src/laplace/recursive_read.py:118-127"),
    ("scale:wall-vector-caches", "cost", "cluster:scaling",
     "RUNNING — the vector stores, narrowed 2026-08-20 (MV-1). .self_embeddings.json: 22,994 int8 "
     "vectors, 15.7MB (raw float ~96MB). The fold's 123MB of float64 decimal text for float32 data "
     "became a .f32.npy + .index.json pair at 24.1MB: 80.4% smaller, bit-identical, 0.10s vs 2.49s.",
     "src/laplace/meaning_upfold.py:52-56"),
    ("scale:wall-reindex", "cost", "cluster:scaling",
     "RUNNING — the reindex wall: rewriting SELF_SHARD_INDEX.md measured 7.27s, 11.22s, 11.60s "
     "and 37.94s at near-identical n. Linear in nodes, but the spread is five-fold and is not "
     "explained by the code; it is the second-largest phase whenever the fold stays incremental.",
     "scripts/reembed.py:146-151"),
    ("scale:flat-descent", "cost", "cluster:scaling",
     "RUNNING — the flat cost: a query descent is bounded by beam times depth, not by corpus "
     "size. At beam 8 it touches 101 of 12,295 vectors, 0.8 percent, in about 1.4s. The trade "
     "is 100x latency for 120x fewer resident vectors — a bargain only where the corpus does not fit.",
     "src/laplace/recursive_read.py:50-58"),
    ("scale:flat-wake", "cost", "cluster:scaling",
     "RUNNING — the other flat cost: the wake's semantic block reads the tree shape in 0.12s and "
     "7MB, against 0.28s and 29MB for the full parse, by dropping every float at parse time. The "
     "wake pays a constant to see the top of a map of any size.",
     "src/laplace/recursive_read.py:121-125"),

    # ---------------- registers -------------------------------------------
    ("register:running", "register", "cluster:registers",
     "The RUNNING register: a claim is RUNNING only if it is in the code today and can be cited "
     "at file and line, with numbers that were measured rather than estimated. Everything in the "
     "write-side, fold, read-side, scaling and laws clusters is RUNNING.",
     "MATHEMATICS.md:7-14"),
    ("register:designed", "register", "cluster:registers",
     "The DESIGNED register: a claim written down in a design doc or an open work order and not "
     "yet in code. Cited to the doc, never to a file:line, because there is no line. A DESIGNED "
     "number is a target, not a measurement.",
     "DESIGN_2026-08-01_the-atlas.md:541-545"),
    ("register:migration", "register", "cluster:registers",
     "The MIGRATION register: the bridge — work that is partly built, or built but not wired, or "
     "waiting on hardware the house does not yet run. Every MIGRATION node names what it waits on.",
     "OPEN_STACK.md:2319-2333"),
    ("register:cpu-truth", "fact", "cluster:registers",
     "RUNNING — the CPU truth. Clustering is sklearn spectral on CPU behind a PSU guard; the "
     "embedder is ONNX-CPU bge-small. No GPU is used anywhere today. On the local box the "
     "serving-path embed budget defaults to 0, meaning OFF, because the drip crashed the PSU.",
     "src/laplace/embed_router.py:289-313"),
    ("register:gpu-boundary", "fact", "cluster:registers",
     "MIGRATION — where a GPU would enter, if it entered. Only two places are GPU-shaped: the "
     "dense affinity and repeated spectral fits of the full fold, and bulk re-embedding of the "
     "whole corpus. Neither is written today, and no code path currently selects a device.",
     "src/laplace/meaning_upfold.py:201-209"),
    ("register:atlas-instrument", "fact", "cluster:registers",
     "RUNNING — Phases 1-3 (exporter, segmentation+seal, bench v2, Tier-1 arms, RAPTOR "
     "comparator, incumbent's honest number) built, judge-CONFIRMED (phase1/2/3-r2). The "
     "organs, Phases 4-7, are deferred to 2026-08-22 — the release machine, not the build.",
     "contract/judged_verdicts.jsonl:23-28"),
    ("register:migration-open", "fact", "cluster:registers",
     "MIGRATION — open bridge items: the full spectral fold needs a bigger box or a GPU to stop "
     "costing 20 minutes; the atlas snapshot bridge (atlas_bridge.py, DESIGNED the-atlas.md:417) "
     "is unbuilt; the content-grade digest v2 is a deferred parallel generation; architecture "
     "docs lag the code.",
     "OPEN_STACK.md:2319-2333"),
    ("register:naming-collision", "fact", "cluster:registers",
     "MIGRATION — a flagged naming collision to hold in mind: the atlas of WO-20260801b is the "
     "sealable instrument-machine, a snapshot plus benchmark, and is NOT diagrams/, the conjugate "
     "view landed 2026-08-15. Distinct objects sharing one word.",
     "OPEN_STACK.md:2319-2333"),

    # ---------------- laws -------------------------------------------------
    ("law:loud-degrade", "law", "cluster:laws",
     "RUNNING — degrade gracefully but never silently. Every fallback prints what became "
     "unavailable and why; the descent raises rather than returning a thin result. Written "
     "after three deposits shipped with zero concept nodes behind a silent empty return.",
     "src/laplace/meaning_upfold.py:291-303"),
    ("law:seal-at-sharder", "law", "cluster:laws",
     "RUNNING — the soul seal binds at the SHARDER, the earliest possible point. A sealed path "
     "yields a handle whose content was never opened, so no later stage can leak what it never "
     "held. The one carve-out reads text transiently at fold and persists only a vector.",
     "src/laplace/self_shard.py:250-262"),
    ("law:handles-not-copies", "law", "cluster:laws",
     "RUNNING — store the trace, not the text. Grades 1 and 2 are never stored; they re-read the "
     "source on demand. The record floor stores character offsets, not chunks. Every vector is "
     "computed from a bounded handle. The store is a map of the corpus, never a second copy of it.",
     "src/laplace/self_shard.py:9-19"),
    ("law:append-only", "law", "cluster:laws",
     "RUNNING — ledgers are append-only and the READER filters. A retired ingest entry stays on "
     "disk and drops out of the read; a superseded verdict is banked beside its predecessor. "
     "Nothing is ever edited in place, so any past state stays reconstructible.",
     "src/laplace/self_corpus.py:340-355"),
    ("law:budget-displacement", "law", "cluster:laws",
     "RUNNING — a bounded payload displaces rather than truncates. Under the 21,000-char grade-0 "
     "bound the oldest ingested entries are dropped first and each is replaced by a descend "
     "handle naming how to get it back. The reader always learns that something was displaced.",
     "src/laplace/self_corpus.py:742-760"),

    # ---------------- seams -------------------------------------------------
    ("seam:docs-gap", "seam", "cluster:seams",
     "RUNNING — the significant seam. TECHNICAL_GUIDE.md never mentions recursive_read, beam, "
     "centroid, meaning_upfold or the leaf cap; grep-confirmed zero hits across 537 lines. The "
     "actual read mechanism lives only in docstrings and one evidence file.",
     "TECHNICAL_GUIDE.md:1-537"),
    ("seam:spectral-spread", "seam", "cluster:seams",
     "RUNNING — 1224.70s at n=21,339 against 488.92s at n=21,420: a 2.5x spread on a slightly "
     "LARGER corpus. Nothing in the code or the timing log explains it. Until it is explained, "
     "the full fold has no predictable cost, only a range.",
     "scripts/reembed.py:158-170"),
    ("seam:two-budgets", "seam", "cluster:seams",
     "RUNNING — one wake payload carries two uncoordinated budgets: the flat fixed point's "
     "21,000-char bound with oldest-first displacement, and the semantic block's own discipline "
     "of 8 handles. Neither knows the other's size. The flat one already self-flags as debt.",
     "src/laplace/self_corpus.py:72-86"),
    ("seam:reindex-variance", "seam", "cluster:seams",
     "RUNNING — the reindex phase varies 11.2s to 37.9s at near-identical node counts, "
     "unexplained by the code; I/O variance is suspected but unmeasured. A phase nobody has "
     "characterised is a phase nobody can budget for.",
     "scripts/reembed.py:146-151"),
    ("loop:closure-meter", "organ", "cluster:restructuring",
     "DESIGNED — T1, pre-registered, free, pre-GPU: every descend banks per-node route "
     "stats: entered, digest-decided, materialized, wasted, plus the holdout self-score. "
     "Need-fired reaches only. Zero behavior change; the loop's instrument.",
     "DESIGN_2026-08-11_the-structuring-loop.md:69-75"),
    ("loop:commuting-split", "organ", "cluster:restructuring",
     "DESIGNED — per cut, banked traffic splits content into the commuting sector (the "
     "digest decides it) and the non-commuting residual (forces descent or crossing). Two "
     "lawful responses: absorb the residual into the digest, or move the cut.",
     "DESIGN_2026-08-11_the-structuring-loop.md:76-83"),
    ("loop:wormholes", "organ", "cluster:restructuring",
     "DESIGNED — T3: down-graph modification without re-folding: tree plus learned "
     "shortcuts where traffic repeatedly crosses boundaries. The wire reused; only the "
     "signal changes — co-materialization in successful descents, not cosine.",
     "DESIGN_2026-08-11_the-structuring-loop.md:84-89"),
    ("loop:constrained-resplit", "organ", "cluster:restructuring",
     "DESIGNED — T4: residual mass at a cut past threshold re-splits THAT subtree under "
     "must-link/cannot-link constraints (constrained spectral); epsilon, the unclosed "
     "mass, is the no-longer-closes-here signal. One alternating up/down sweep.",
     "DESIGN_2026-08-11_the-structuring-loop.md:90-95"),
    ("loop:bottom-up-escalation", "organ", "cluster:restructuring",
     "DESIGNED — PROPOSED in-session 2026-08-16: after a local re-split, a sub-centroid "
     "closer to a sibling parent promotes the rebuild one level; global is escalation "
     "failing to terminate. Signals: margin tail, ambiguity gap, silhouette decay.",
     "evidence/steer_2026-08-16_restructuring.md"),
    ("loop:nu-nonlocality", "organ", "cluster:restructuring",
     "DESIGNED — conjecture-fenced: nu(q), minimal subtree cover of a query's answer "
     "support, its bond dimension against the geometry. Serve cost O(nu.b.log_b N); "
     "E[nu] is the loop's objective. The irreducibly nonlocal class belongs to scans.",
     "DESIGN_2026-08-11_the-structuring-loop.md:299-311"),
    ("loop:fitness-reserved", "fork", "cluster:restructuring",
     "DESIGNED — HIS (F23): closure-residual is a typed object, but its promotion to a "
     "fitness signal and the threshold phi are reserved to the author; autonomous structural "
     "writes are dreamer-class behind fork 2. Usage-count is not the signal.",
     "DESIGN_2026-08-11_the-structuring-loop.md:96-101"),
    ("register:gpu-week", "register", "cluster:registers",
     "MIGRATION — the GPU arrives the week of 2026-08-17 (his word, 2026-08-16). Opens: "
     "the dense-spectral wall, larger embedders, the atlas-in-Eigen run, the "
     "restructuring hunt against banked residual distributions.",
     "evidence/steer_2026-08-16_restructuring.md"),
    ("seam:jury-undocumented", "seam", "cluster:seams",
     "RUNNING — the jury is the pipeline's only model-judgement site and it has never been "
     "canonically documented: which model, on what trigger, at what cadence. It exists in "
     "docstrings and two handoffs. The one place intelligence sits is the one place least written down.",
     "scripts/drain_proposals.py:1-13"),
]

# ---------------------------------------------------------------------------
# the edges — (node, target, edge type)
# ---------------------------------------------------------------------------

_EDGES: list[tuple[str, str, str]] = [
    ("loop:closure-meter", "loop:constrained-resplit", "instrument-feeds-organ"),
    ("loop:constrained-resplit", "fold:upfold-spectral", "refines"),
    ("loop:wormholes", "fold:wire-drain", "mechanism-reused"),
    ("loop:bottom-up-escalation", "loop:constrained-resplit", "extends"),
    ("loop:fitness-reserved", "intel:law", "bounds"),
    # --- dataflow: stage feeds stage -------------------------------------
    ("stage:shard", "stage:lenses", "stage-feeds-stage"),
    ("stage:lenses", "stage:embed", "stage-feeds-stage"),
    ("stage:embed", "fold:upfold-incremental", "stage-feeds-stage"),
    ("fold:upfold-incremental", "fold:upfold-spectral", "escalates-to"),
    ("fold:upfold-incremental", "fold:tree-build", "stage-feeds-stage"),
    ("fold:upfold-spectral", "fold:tree-build", "stage-feeds-stage"),
    ("stage:paper-atomiser", "fold:tree-build", "stage-feeds-stage"),
    ("fold:tree-build", "fold:persist", "stage-feeds-stage"),
    ("fold:persist", "fold:wire-drain", "stage-feeds-stage"),
    ("fold:wire-drain", "fold:reindex", "stage-feeds-stage"),
    ("fold:persist", "read:descent", "stage-feeds-stage"),
    ("fold:persist", "read:wake-projection", "stage-feeds-stage"),
    ("stage:ledger-door", "read:wake-projection", "stage-feeds-stage"),

    # --- grounding: a stage rests on a mathematical object ----------------
    ("stage:embed", "math:embedding-map", "grounded-in"),
    ("stage:embed", "math:quantisation", "grounded-in"),
    ("stage:embed", "math:content-hash", "grounded-in"),
    ("stage:embed", "math:path-heat", "grounded-in"),
    ("fold:upfold-incremental", "math:cosine", "grounded-in"),
    ("fold:upfold-incremental", "math:centroid", "grounded-in"),
    ("fold:upfold-incremental", "math:content-hash", "grounded-in"),
    ("fold:full-triggers", "math:drift-fraction", "grounded-in"),
    ("fold:upfold-spectral", "math:affinity", "grounded-in"),
    ("fold:upfold-spectral", "math:spectral", "grounded-in"),
    ("fold:upfold-spectral", "math:silhouette", "grounded-in"),
    ("fold:tree-build", "math:grade-height", "grounded-in"),
    ("fold:tree-build", "math:keyword-promotion", "grounded-in"),
    ("fold:wire-drain", "math:decision-band", "grounded-in"),
    ("read:descent", "math:beam-search", "grounded-in"),
    ("read:descent", "math:centroid", "grounded-in"),
    ("read:descent", "math:cosine", "grounded-in"),
    ("read:wake-projection", "math:budget-displacement", "grounded-in"),
    ("stage:ledger-door", "math:budget-displacement", "grounded-in"),
    ("fact:grade-duality", "math:grade-height", "grounded-in"),

    # --- intelligence: site sits at a stage; the law binds the sites ------
    ("intel:embedder", "stage:embed", "sited-at"),
    ("intel:wire-jury", "fold:wire-drain", "sited-at"),
    ("intel:ledger-grade-kind", "stage:ledger-door", "sited-at"),
    ("intel:law", "intel:embedder", "law-binds"),
    ("intel:law", "intel:wire-jury", "law-binds"),
    ("intel:law", "intel:ledger-grade-kind", "law-binds"),
    ("intel:thresholds-from-verdicts", "intel:law", "substantiates"),
    ("intel:thresholds-from-verdicts", "math:decision-band", "grounded-in"),

    # --- scaling: a cost is the cost OF a stage ---------------------------
    ("scale:wall-spectral", "fold:upfold-spectral", "cost-of"),
    ("scale:wall-spectral", "math:affinity", "grounded-in"),
    ("scale:wall-tree-open", "read:descent", "cost-of"),
    ("scale:wall-vector-caches", "stage:embed", "cost-of"),
    ("scale:wall-vector-caches", "fold:upfold-incremental", "cost-of"),
    ("scale:wall-reindex", "fold:reindex", "cost-of"),
    ("scale:flat-descent", "read:descent", "cost-of"),
    ("scale:flat-descent", "math:beam-search", "grounded-in"),
    ("scale:flat-wake", "read:wake-projection", "cost-of"),
    ("read:beam-bench", "read:descent", "substantiates"),

    # --- laws bind the places that enforce them ---------------------------
    ("law:loud-degrade", "fold:upfold-spectral", "law-binds"),
    ("law:loud-degrade", "read:descent", "law-binds"),
    ("law:loud-degrade", "fold:wire-gate-a", "law-binds"),
    ("law:seal-at-sharder", "stage:shard", "law-binds"),
    ("law:handles-not-copies", "stage:shard", "law-binds"),
    ("law:handles-not-copies", "stage:lenses", "law-binds"),
    ("law:handles-not-copies", "stage:embed", "law-binds"),
    ("law:append-only", "stage:ledger-door", "law-binds"),
    ("law:append-only", "fold:wire-drain", "law-binds"),
    ("law:budget-displacement", "stage:ledger-door", "law-binds"),
    ("law:budget-displacement", "read:wake-projection", "law-binds"),
    ("law:budget-displacement", "math:budget-displacement", "grounded-in"),

    # --- registers: every claim-bearing cluster declares its register -----
    ("register:cpu-truth", "register:running", "in-register"),
    ("register:gpu-boundary", "register:migration", "in-register"),
    ("register:atlas-instrument", "register:running", "in-register"),
    ("register:migration-open", "register:migration", "in-register"),
    ("register:naming-collision", "register:migration", "in-register"),
    ("intel:law", "register:designed", "in-register"),
    ("register:cpu-truth", "stage:embed", "describes"),
    ("register:cpu-truth", "fold:spectral-gate", "describes"),
    ("register:gpu-boundary", "fold:upfold-spectral", "describes"),
    ("register:migration-open", "scale:wall-spectral", "describes"),
    ("register:migration-open", "seam:docs-gap", "describes"),

    # --- seams sit in a named place ---------------------------------------
    ("seam:docs-gap", "read:descent", "seam-in"),
    ("seam:docs-gap", "fold:upfold-incremental", "seam-in"),
    ("seam:spectral-spread", "scale:wall-spectral", "seam-in"),
    ("seam:two-budgets", "read:wake-projection", "seam-in"),
    ("seam:two-budgets", "stage:ledger-door", "seam-in"),
    ("seam:reindex-variance", "scale:wall-reindex", "seam-in"),
    ("seam:jury-undocumented", "intel:wire-jury", "seam-in"),
]


# ---------------------------------------------------------------------------
# the record emitters — deterministic order, stable ids
# ---------------------------------------------------------------------------

class Emitter:
    """Mints add-node / add-edge rewire records with stable AS-NNNN ids in call order."""

    def __init__(self) -> None:
        self.records: list[dict] = []
        self._seq = 0
        self.nodes: set[str] = set()

    def _id(self) -> str:
        self._seq += 1
        return f"AS-{self._seq:04d}"

    def node(self, nid: str, kind: str, parent: str, essence: str, ref: str) -> None:
        if nid in self.nodes:
            raise ValueError(f"duplicate node id: {nid}")
        body = " ".join(essence.split())
        full = f"{body} · src:{ref}"
        if len(full) > ESSENCE_CAP:
            raise ValueError(f"essence over {ESSENCE_CAP} chars ({len(full)}): {nid}")
        self.nodes.add(nid)
        self.records.append({
            "id": self._id(), "ts": FIXED_TS, "kind": "add-node", "node": nid,
            "target": None, "value": None, "by": BUILD_TAG, "status": "open",
            "parent": parent, "node_kind": kind, "essence": full, "ref": ref})

    def edge(self, node: str, target: str, edge_type: str) -> None:
        self.records.append({
            "id": self._id(), "ts": FIXED_TS, "kind": "add-edge", "node": node,
            "target": target, "value": edge_type, "by": BUILD_TAG, "status": "open"})


def build_records() -> tuple[list[dict], dict[str, Any]]:
    """Emit the full deterministic record set from the tables above, plus a census."""
    em = Emitter()

    em.node(GOAL, KIND["goal"], ROOT,
            "RUNNING — how the Laplace engine stores and reconstructs itself: the write side, "
            "the fold, the read side, the mathematics under them, and the honest cost of each. "
            "Authored as nodes because design prose rots.",
            "src/laplace/keeper.py:346-443")

    for cid, ess in _CLUSTERS:
        em.node(cid, KIND["cluster"], GOAL, ess, "src/laplace/keeper.py:346-443")

    # the mathematics cluster, in section order — the numbering IS the contract
    for suffix, sec, ess in _MATH:
        # every mathematical object below is computed by the running system today, so the
        # whole cluster carries the RUNNING register; the prefix is added here, once.
        em.node(f"math:{suffix}", KIND["math"], "cluster:mathematics",
                f"RUNNING — {ess}", f"MATHEMATICS:§{sec}")

    for nid, typ, parent, ess, ref in _NODES:
        em.node(nid, KIND[typ], parent, ess, ref)

    for node, target, etype in _EDGES:
        if node not in em.nodes:
            raise ValueError(f"edge from unknown node: {node}")
        if target not in em.nodes:
            raise ValueError(f"edge to unknown node: {target}")
        em.edge(node, target, etype)

    n_nodes = sum(1 for r in em.records if r["kind"] == "add-node")
    n_edges = sum(1 for r in em.records if r["kind"] == "add-edge")
    registers: dict[str, int] = {}
    for r in em.records:
        if r["kind"] != "add-node":
            continue
        head = r["essence"].split(" — ", 1)[0]
        if head in REGISTERS:
            registers[head] = registers.get(head, 0) + 1
        elif r["node"] in _SCAFFOLD:
            registers["scaffold"] = registers.get("scaffold", 0) + 1
        else:
            raise ValueError(
                f"three-register law: {r['node']} carries no register prefix "
                f"(add one of {REGISTERS}, or list it in _SCAFFOLD)")
    census = {
        "corpus": CORPUS,
        "n_nodes": n_nodes,
        "n_edges": n_edges,
        "n_math_objects": len(_MATH),
        "n_clusters": len(_CLUSTERS),
        "registers": dict(sorted(registers.items())),
        "node_kinds": dict(sorted(
            {k: sum(1 for r in em.records
                    if r["kind"] == "add-node" and r["node_kind"] == k)
             for k in sorted(set(KIND.values()))}.items())),
        "edge_types": sorted({r["value"] for r in em.records if r["kind"] == "add-edge"}),
        "max_essence_chars": max(len(r["essence"]) for r in em.records
                                 if r["kind"] == "add-node"),
    }
    return em.records, census


# ---------------------------------------------------------------------------
# ledger IO — preserve foreign records, rewrite ours, byte-stable
# ---------------------------------------------------------------------------

def _serialise(records: list[dict]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)


def split_foreign(text: str, build_tag: str = BUILD_TAG) -> tuple[list[dict], list[dict]]:
    """Split a ledger's NON-build records by their side of the rebuilt block.

    The same cure as the design builder's twin (WO-20260820-rewire-append-drifts-the-builder):
    ``corpus_ingest.rewire_add`` appends at end-of-file, so a deposit through the sanctioned door
    lands AFTER our block; re-emitting it before the block made ``--check`` red on a legitimate
    deposit until the builder re-ran. Each foreign row is now preserved on the side it was written
    on, which keeps ``--check`` byte-exact and keeps a door deposit applying ON TOP of the built
    nodes. A ledger with no block of ours yet keeps the old behaviour: everything is 'before'."""
    before: list[dict] = []
    after: list[dict] = []
    seen_build = False
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            r = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if r.get("by") == build_tag:
            seen_build = True
            continue
        (after if seen_build else before).append(r)
    return before, after


def emit(path: Path) -> tuple[str, dict[str, Any]]:
    """Compute the ledger text (foreign records preserved on their own side of our rebuilt
    block) without writing — the pure core the writer and the --check path share."""
    records, census = build_records()
    before, after = split_foreign(path.read_text(encoding="utf-8") if path.is_file() else "")
    census["n_foreign_preserved"] = len(before) + len(after)
    census["n_foreign_after_block"] = len(after)
    return _serialise(before + records + after), census


def check_math(note: Path) -> tuple[bool, list[str]]:
    """Resolve every ``MATHEMATICS:§…`` ref this build emits against the companion note's
    actual headers. The ledger's math refs are subsection-level claims; a ref that names a
    section the note does not have is a broken citation, not a cosmetic slip, so it is
    checkable rather than trusted. A ref of the form ``a.b-c.d`` names a span and every
    endpoint must exist."""
    import re
    lines: list[str] = []
    if not note.is_file():
        return False, [f"companion note not found: {note}"]
    headers: set[str] = set()
    for ln in note.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^#{2,3}\s+(\d+(?:\.\d+)?)[.\s]", ln)
        if m:
            headers.add(m.group(1))
    records, _census = build_records()
    ok = True
    for r in records:
        ref = r.get("ref", "")
        if not ref.startswith("MATHEMATICS:§"):
            continue
        cited = ref.split("§", 1)[1]
        for part in cited.split("-"):
            if part in headers:
                lines.append(f"  ok    {r['node']:<28} §{part}")
            else:
                ok = False
                lines.append(f"  BROKEN {r['node']:<27} §{part} — no such section in {note.name}")
    return ok, lines


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the atlas-system conceptric ledger.")
    ap.add_argument("--repo-root", default=".",
                    help="repo root; the ledger defaults to <root>/" + LEDGER)
    ap.add_argument("--ledger", default=None,
                    help="explicit ledger path, overriding --repo-root")
    ap.add_argument("--check", action="store_true",
                    help="verify the on-disk ledger already equals a fresh build (idempotent)")
    ap.add_argument("--check-math", action="store_true",
                    help="verify every MATHEMATICS:§ ref resolves to a real section of the note")
    ap.add_argument("--math-note", default=None,
                    help="path to MATHEMATICS.md (default: beside this script)")
    args = ap.parse_args()

    if args.check_math:
        note = Path(args.math_note) if args.math_note \
            else Path(__file__).resolve().parent / "MATHEMATICS.md"
        ok, lines = check_math(note)
        print("\n".join(lines))
        print(("all mathematics refs resolve in " if ok else "BROKEN mathematics refs against ")
              + str(note))
        return 0 if ok else 1

    path = Path(args.ledger) if args.ledger else Path(args.repo_root).resolve() / LEDGER
    text, census = emit(path)

    if args.check:
        current = path.read_text(encoding="utf-8") if path.is_file() else ""
        if current != text:
            print("DRIFT: on-disk ledger != fresh build (run without --check to re-emit)",
                  file=sys.stderr)
            return 1
        print(f"idempotent: {path} matches a fresh build")
        print(json.dumps(census, indent=2, ensure_ascii=False))
        return 0

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(f"wrote {path}")
    print(json.dumps(census, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
