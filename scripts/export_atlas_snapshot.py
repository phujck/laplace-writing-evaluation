"""export_atlas_snapshot.py - the ONE bridge from the engine to the atlas, and it carries no code.

    python3 scripts/export_atlas_snapshot.py [--out-dir atlas/stores/snapshots] [--limit N]

This script imports laplace and writes a RecordSnapshot bundle as DATA. It never imports atlas;
atlas never imports laplace. The dependence is one-way and both directions are enforced by AST
walks (``tests/test_atlas_seal.py`` here, ``atlas/tests/test_seal.py`` there), each with a
zero-length allowlist.

That seal costs this file a duplication: canonical JSON, sha256, the atomic write and the blob
layout are re-implemented below rather than imported from ``atlas.ids`` / ``atlas.store``. The
duplication is the price of the one-way dependence, and it is not trusted - ``snapshot.verify``
on the atlas side RECOMPUTES the snapshot id and every content hash with its own functions and
refuses on disagreement. Agreement is checked, never assumed.

THE UNIVERSE. The nodes are the files the engine's self-shard walk covers, enumerated by calling
``self_shard._tracked_files`` and classified by ``self_shard._is_soul`` and
``self_shard._TEXT_EXT`` - the same tracked-plus-untracked-not-ignored set, single-sourced from
the engine rather than re-derived here, so the snapshot and the live conceptric cannot drift
apart over what counts as a node.

THE SEAL. Bytes under a sealed prefix are never read. Sealed nodes enter as
``{sealed: true, content_blob: null, content_hash: "refs-only"}`` and carry size 0 - refs only,
nothing that could reconstruct content. ``seal_report.json`` carries the two counts the atlas
side refuses on. This is stricter than the engine's in-process posture on purpose: bundles
travel as data into benchmarks and out of this repository. The exporter's sealed set is
therefore WIDER than ``self_shard._SEALED_PREFIXES`` - see EXTRA_SEALED_PREFIXES below for the
three added zones, the measurement that forced them, and the two zones deliberately left out,
and NEVER_PUBLIC_PATHS for the files whose own headers forbid them to travel. Since 2026-08-21
that last class is no longer transcribed by hand alone: ``scan_declarations`` reads the head of
every candidate node and seals any file whose own header declares itself never-public, beside
the literal lists and never instead of them.

DETERMINISM. ``snapshot_id`` is the sha256 of the canonical JSON of the manifest minus two
fields: the id itself, and ``created_ts``. The timestamp is recorded because provenance is
useful and excluded from the hash because an instrument whose ids move under a clock cannot
measure anything. Two exports with the same parent and delta produce the same id. Unchanged node bytes
keep their nodes_sha256 even when a newly tracked parent changes the bundle identity. ``atlas/stores/`` is excluded from the universe for the same reason:
the exporter's own output must not become part of its next input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from laplace.pipeline import dial_profiles as dials  # noqa: E402
from laplace.engine import self_shard

EXPORTER_VERSION = "3"      # verified incremental ancestry and optional travelling blobs

# These four strings must equal their atlas-side constants. They are duplicated by the seal, and
# the agreement is enforced mechanically: a bundle written under a version atlas does not read
# is refused by schema.from_dict, not silently reinterpreted.
ATLAS_SCHEMA_VERSION = "1"                       # atlas/__init__.py:ATLAS_SCHEMA_VERSION
SNAPSHOT_NODE_SCHEMA = "snapshot-node/1"         # atlas/schema.py:SnapshotNode.SCHEMA_VERSION
RECORD_SNAPSHOT_SCHEMA = "record-snapshot/1"     # atlas/schema.py:RecordSnapshot.SCHEMA_VERSION
REFS_ONLY = "refs-only"                          # atlas/schema.py:REFS_ONLY
NOT_READ = "not-read"                            # atlas/schema.py:NOT_READ

# Derived stores are not record. Excluding this prefix is what makes a re-export at an unchanged
# tree reproduce its id instead of ingesting the previous run's output.
EXCLUDED_PREFIXES = ("atlas/stores/",)

# THE EXPORTER'S SEAL IS WIDER THAN THE ENGINE'S, AND THIS IS THE WHOLE OF THE WIDENING.
#
# The engine's ``_SEALED_PREFIXES`` is an IN-PROCESS posture: soul text may be read to build a
# vector that never leaves the process. A bundle is the opposite case - it travels as data into
# benchmarks and, at Phase 8, out of this repository - and the design's own words are that the
# snapshot posture must be "stricter than the live engine's, deliberately".
#
# Measured at the first export (2026-08-01, commit 436b706): with the engine's two prefixes
# alone the bundle carried 6,915 nodes and 306 MB of ``archive/soul_dump/`` - raw WhatsApp logs
# with named third parties and full Claude conversation exports - which is 58% of all content
# bytes in the snapshot. That is not stricter than the engine; it is the most sensitive material
# in the repository, packaged for travel. ``soul_vectors/nodes.jsonl`` likewise carries
# ``payload`` text and ``person`` fields, 79 MB of it.
#
# So these three prefixes are sealed HERE, at the exporter, and the widening is deliberately
# visible: ``sealed_prefixes`` is a hashed manifest field, so a narrower or wider list is a
# different snapshot_id, and reverting is deleting a line. The atlas-side floor
# (``snapshot.SOUL_PREFIXES``) stays at the design's two prefixes - a wider write-side list
# still verifies clean, because those nodes simply arrive sealed.
#
# NOT sealed, named so the boundary is a decision and not an oversight: ``collaborator_corpus/``
# (4.1 MB) and ``life_corpus/`` (65 KB). Those are the engine's working corpora, cited
# throughout the record and read by ordinary organs; sealing them would be over-reach. If the
# author rules them sealed for travelling bundles, they go in this tuple.
EXTRA_SEALED_PREFIXES = (
    "archive/soul_dump/",     # the raw dump: third-party chat logs, personal correspondence
    "soul_corpus/",           # soul-derived by construction (widens soul_corpus/sealed/)
    "soul_vectors/",          # soul vectors carrying payload text and person identifiers
)

# DERIVED-FROM-SEALED IS SEALED, FOR A TRAVELLING BUNDLE.
#
# A path-prefix seal cannot see a LAUNDERED leak: soul content that has been folded into a
# derived store living at an ordinary path. The Phase 1 judge found five such stores carrying
# 125,159,800 bytes - 53.4% of the post-widening text corpus and 123,824 spans, 55.7% of the
# bundle - none of them under any sealed prefix:
#
#   archive/self_shard/.upfold_vec_cache.json  68.3 MB  12,975 soul_dump-keyed vectors
#   .meaning_tree.json                         18.5 MB  38,916 soul_dump occurrences + soul-derived
#                                                       cluster labels
#   .self_graded.json                          16.4 MB  including 1,674 VERBATIM timestamped
#                                                       private-chat lines with named third parties
#   .self_embeddings.json                      12.0 MB  6,946 vectors keyed by sealed paths
#   SELF_SHARD_INDEX.md                         4.0 MB  25,945 soul_dump refs with essences
#
# Exact paths, not prefixes: their siblings are ordinary record (``archive/self_shard/
# upfold_v0.json`` is a v0 artifact scoring 30 refs) and sealing a whole directory to catch one
# file would be the over-reach this list exists to avoid. Hashed into the manifest exactly like
# the prefixes, so the perimeter is part of the snapshot's identity.
#
# Orchestrator decision, derived per the fork law, recorded for the author's retrospective
# correction. The PRINCIPLE - derived-from-sealed is sealed for bundles - is put to the author;
# it is not settled here.
DERIVED_FROM_SEALED_PATHS = (
    "archive/self_shard/.upfold_vec_cache.json",
    ".meaning_tree.json",
    ".self_graded.json",
    ".self_embeddings.json",
    "SELF_SHARD_INDEX.md",
    # blk2-A: generated subtrees are sealed by directory; harnesses and reports stay record.
    "evidence/EMBEDDING_BAKEOFF_2026-08-19/bge-base/",  # candidate vectors and navigation over sealed leaves
    "evidence/EMBEDDING_BAKEOFF_2026-08-19/bge-small/",  # candidate vectors and navigation over sealed leaves
    "evidence/EMBEDDING_BAKEOFF_2026-08-19/gte-base/",  # candidate vectors and navigation over sealed leaves
    "evidence/EMBEDDING_BAKEOFF_2026-08-19/nomic-v1.5/",  # candidate vectors and navigation over sealed leaves
    "evidence/EMBEDDING_BAKEOFF_2026-08-19/_half/_shadow_repo/",  # copied fold of the sealed-inclusive corpus
    "evidence/EMBEDDING_BAKEOFF_2026-08-19/_dryrun/bge-small/",  # dry-run navigation derived from sealed leaves
    "evidence/EMBEDDING_BAKEOFF_2026-08-19/_dryrun/gte-base/",  # dry-run navigation derived from sealed leaves
    "evidence/EMBEDDING_BAKEOFF_2026-08-19/_dryrun/_budget/_shadow_repo/",  # copied budget fold includes sealed leaves
    "evidence/EMBEDDING_BAKEOFF_2026-08-19/_dryrun/_half/_shadow_repo/",  # copied half fold includes sealed leaves
    "evidence/FIBRE_CENSUS_2026-08-19/leaves.jsonl",  # census rows derived from sealed chat leaves
    "evidence/FIBRE_CENSUS_2026-08-19/buckets.json",  # fibre membership derived from sealed chat leaves
    "evidence/RESIDUAL_CENSUS_2026-08-19/before/",  # generated census of the sealed-inclusive predecessor tree
    "evidence/RESIDUAL_CENSUS_2026-08-19/arm3_new_tree/",  # generated census of the sealed-inclusive candidate tree
    "evidence/RESIDUAL_CENSUS_2026-08-19/after/",  # generated census of the sealed-inclusive successor tree
    "evidence/RESIDUAL_AXIS_2026-08-20/leaves.jsonl",  # axis measurements over sealed chat leaves
    "evidence/RESIDUAL_AXIS_2_2026-08-20/none_leaves.jsonl",  # residual leaf set derived from sealed chat shards
    "evidence/COLLAB_FIBRE_2026-08-20/leaves.jsonl",  # collaborator-axis census includes sealed chat leaves
    "evidence/COLLAB_FIBRE_2026-08-20/buckets.json",  # collaborator buckets derived from sealed chat leaves
    "evidence/NAVIGABILITY_BENCH_2026-08-18/_edge_index_cache.json",  # cached graph includes sealed-derived edges
    "evidence/ESSENCE_PROTO_2026-08-20/extracted.jsonl",  # candidate essences extracted from sealed chat shards
    ".escalate_briefs.HELD-20260824-for-atlas.json",  # enriched routing briefs carry sealed-derived essences
    ".digests.jsonl",  # extracted digest store has sealed-source pointers and membership
    ".wire_proposals.HELD-20260824-for-atlas.jsonl",  # geometric routing proposals derived from sealed-node vectors
    ".wire_verdicts.jsonl",  # routing judgments include sealed-node candidates and rationale
    "evidence/DESCENT_PROVENANCE_2026-08-20/sweep.json",  # materialized descent traces include sealed-derived routes
    "evidence/ROUTE_MASS_TERM_2026-08-21/sweep.json",  # measured routing traces include sealed-derived routes
    "evidence/ROUTE_MASS_TERM_2026-08-21/sweep_apex.json",  # apex routing traces include sealed-derived routes
    "evidence/CALIBRATION_ZERO_2026-08-19/locality_results.json",  # graph locality projection includes sealed-derived neighbourhoods
    "evidence/LOCALITY_BASELINE_2026-08-18/results.json",  # graph locality projection includes sealed-derived neighbourhoods
    "evidence/ATLAS_BENCH_2026-08-24/WAVE_RECORD_author_model.json",  # generated claims and grounds carry sealed-source derivations
)

# NEVER-PUBLIC BY THE FILE'S OWN IN-BAND DECLARATION.
#
# The second class of path-seal defeat, and it is not laundering - it is the opposite. These
# files say, in their own first paragraph, that they must never travel, and they sit at ordinary
# paths outside every sealed prefix, so BOTH standing instruments miss them: the path seal never
# looks at them and the reference-density check scores them near zero (they cite ``profiles/``,
# not a sealed prefix). Measured 2026-08-13 against the banked bundles 0aafd4e3 (2026-08-01) and
# 9c816260 (2026-08-11): ``profiles/GERARD_PSYCH_PROFILE_2026-07-11_v1.md`` entered both with
# ``sealed: false``, ``read_policy: text``, 30,583 bytes hashed and blobbed.
#
#   profiles/GERARD_PSYCH_PROFILE_2026-07-11_v1.md      "NEVER-PUBLIC - engine-repo only. This
#                                                        file must never enter any bundle,
#                                                        export, website, talk, disclosure, or
#                                                        manuscript."
#   profiles/GERARD_PROFILE_2026-08-12_v2_the-honest-one.md
#                                                       "NEVER-PUBLIC - engine-repo only, sealed
#                                                        class. Soul-derived throughout; the
#                                                        perimeter law applies at any boundary
#                                                        that travels."
#
# THE RENDERINGS ARE THE DOCUMENT. A seal on the .md alone would move the leak one file over:
# the .tex carries the same prose (LaTeX-escaped, so a fingerprint drawn from the .md does not
# even match it) and the .pdf, though read_policy ``asset-not-read``, still announces the
# document and its exact byte size in a travelling bundle. A never-public document is sealed in
# every rendering it has, or it is not sealed.
#
# WHAT IS DELIBERATELY NOT HERE. Outward artifacts that were sent by the author's own hand -
# ``DRAFT_2026-08-12_jack-hampson-operating-profile.{md,tex,pdf}``, ``output/pdf/`` - carry no
# such declaration and stay unsealed. The seal follows the declaration, never the directory.
#
# THE LIST IS NO LONGER THE ONLY INSTRUMENT (2026-08-21, WO-20260814-autoseal-by-declaration).
# ``scan_declarations`` below reads the head of every unsealed text node and seals any file whose
# own header declares itself never-public. It runs BESIDE this list, never instead of it: the
# union is the perimeter and the widest wins. Measured against this tree, the scan reproduces
# five of the six paths named here on its own (the two .md declarations, the .tex, and both .pdf
# renderings by the sibling rule) and cannot reach the sixth -
# ``profiles/gerard_mini_conceptric_v1.json``, whose declaration lives in a companion note and
# not in its own head. That one file is the whole argument for keeping the list.
NEVER_PUBLIC_PATHS = (
    "profiles/GERARD_PSYCH_PROFILE_2026-07-11_v1.md",
    "profiles/GERARD_PSYCH_PROFILE_2026-07-11_v1.pdf",
    "profiles/GERARD_PROFILE_2026-08-12_v2_the-honest-one.md",
    "profiles/GERARD_PROFILE_2026-08-12_v2_the-honest-one.tex",
    "profiles/GERARD_PROFILE_2026-08-12_v2_the-honest-one.pdf",
    # Companion by its own note ("NEVER-PUBLIC, engine-repo only. Companion to
    # profiles/GERARD_PSYCH_PROFILE_2026-07-11_v1.md") - same declaration class, found by the
    # 2026-08-13 sweep in all five banked bundles at 47,315 B unsealed.
    "profiles/gerard_mini_conceptric_v1.json",
)

# CARRIERS OF VERBATIM EXCERPTS FROM NEVER-PUBLIC FILES. The third class, and the one the
# perimeter law (STANDING_LAW.md 2026-08-01) was measured from: a derived store at an ordinary
# path holding sealed content verbatim. These four manifests/transcripts embed the psych
# profile's header block and opening prose as ``excerpt`` fields (12, 12, 12, and 9+9 matched
# distinctive lines respectively, fingerprint scan 2026-08-13). Sealing the SOURCE does nothing
# to them, and they score ~1 on the reference-density check. The content edit that would redact
# the excerpt fields inside the committed record is the author's; the seal at the boundary that
# travels is the law's. The fifth transcript of the same econ run (agent-a5fc4c5d712de307f)
# measured zero hits and stays open - the seal follows the measurement, never the directory.
EXCERPT_CARRIER_PATHS = (
    "corpus_friction/deslop_manifest_eigenengine.json",
    "paper_falqon/manuscript/dispatches/structural_conformance_manifest.json",
    "synthetics papers/subset-sum-itqde/manuscript/dispatches/structural_conformance_manifest.json",
    "eigenengine/manuscript/rounds/harnessed/econ_run_2026-07-13_growth/agent-a4211c6761681c0f0.jsonl",
    "eigenengine/manuscript/rounds/harnessed/econ_run_2026-07-13_growth/agent-ad5ee5263bba15ccd.jsonl",
    "eigenengine/manuscript/rounds/harnessed/econ_run_2026-07-13_growth/agent-a3b0b213e5f8591cf.jsonl",
    "eigenengine/manuscript/rounds/harnessed/econ_run_2026-07-13_growth/agent-a754854d4c55efe09.jsonl",
)

# The exporter's path perimeter: a trailing slash seals a whole generated directory.
# Directory entries also enter sealed_prefixes, keeping that meaning explicit for consumers.
# Three rationales, one hashed list. Order is stable so the
# manifest's ``sealed_paths`` - and therefore the snapshot id - moves only when the perimeter
# does.
EXTRA_SEALED_PATHS = DERIVED_FROM_SEALED_PATHS + NEVER_PUBLIC_PATHS + EXCERPT_CARRIER_PATHS

# ---------------------------------------------------------------------------
# AUTO-SEAL BY DECLARATION - the fourth class, and the only self-maintaining one
# ---------------------------------------------------------------------------
#
# Three lists above are maintained by hand, which means each of them is exactly as current as the
# last judge who read the corpus. The measured failure they were written from was not that a rule
# was missing - the psych profile SAID in its own first paragraph that it must never travel - it
# was that nobody had transcribed that sentence into a Python tuple. A perimeter that depends on
# transcription fails on the next file written, silently, at whatever hour it is written.
#
# So the file's own header is read as the declaration it already is. Every unsealed text node's
# first ``DECLARATION_WINDOW_BYTES`` are scanned, and a head that BINDS seals the node.
#
# THE GRAMMAR (the settled design call; Eigen's jurisdiction per
# AMEND-20260820-scored-autoseal-by-declaration). Four clauses, each one there to keep a file
# that DISCUSSES the declaration from being read as one that MAKES it:
#
#   1. HEAD ONLY. The window is the first 2 KB. A declaration is a banner; a sentence in the body
#      of a session handoff quoting one is record about a banner, not a banner.
#   2. NORMALIZED LINE. Markdown, comment and TeX decoration is stripped (``>`` ``#`` ``*`` ``_``
#      backtick ``%`` ``//`` ``"""`` ``\cmd`` ``{}``), whitespace collapsed. The .tex rendering's
#      banner is buried under three LaTeX macros and must still bind - the renderings ARE the
#      document.
#   3. BANNER POSITION. The token must begin within ``DECLARATION_LINE_PREFIX_BUDGET`` characters
#      of its normalized line. This single clause is what separates the two profiles from every
#      near-miss in this tree; in the false positives the token sits mid-sentence, 85+ characters
#      in, behind a numbered list item.
#   4. BANNER PUNCTUATION. What follows the token must be a separator - an em/en dash, a hyphen,
#      a colon, a comma, a full stop, an exclamation mark - or the qualifier itself. A banner
#      announces and then explains; a sentence carries the token as a noun mid-clause. This is
#      the clause that survives line wrapping, and it is the one clause the tree could not have
#      taught me: the live near-miss in ``SESSION_HANDOFF_2026-08-14`` fails clause 3 only
#      because of where its lines happen to break, and a re-wrap of that paragraph would have
#      sealed a session handoff. The planted discussion node in
#      ``tests/test_atlas_export_perimeter.py`` is that re-wrap, written on purpose.
#   5. A QUALIFIER FROM A FIXED VOCABULARY, in the same normalized line or the two after it. The
#      bare token is a topic; the token plus "engine-repo only" / "must never enter" / "sealed
#      class" is an instruction. The vocabulary is short and closed on purpose: a grammar that
#      accepts paraphrase accepts the paraphrase in a file about paraphrases.
#
# MEASURED, 2026-08-21, over the 14,898-node universe of this tree: 3 nodes BIND - both
# never-public profiles' .md and the honest profile's .tex, i.e. every text rendering of every
# document the 2026-08-13 judge found by hand - and 0 nodes bind that should not. 11 nodes carry
# the token in their head and do NOT bind, and all eleven are the machinery and the record OF the
# perimeter: this file, ``verify_seal_fingerprints.py``, ``tests/test_atlas_export_perimeter.py``,
# ``evidence/SEV_2026-08-13_profile-perimeter/README.md``, three session handoffs, the canon wiki
# page, ``soul_shard.py``, and two soul nodes already sealed by prefix. The gap is categorical,
# not marginal: nothing in this tree sits between "banner" and "prose about banners".
#
# THE NEAR-MISSES ARE REPORTED, NEVER DROPPED. ``declaration_near_miss_paths`` in
# ``seal_report.json`` names every head that carried the token without binding. A grammar that
# discards its own borderline cases silently is the hand-maintained list again, one level down.
#
# EVERY RENDERING. A declaration in the .md binds the .tex and the .pdf beside it: any node in
# the universe sharing directory and stem with a declaring file is sealed with it. That is the
# 2026-08-13 finding made mechanical - a seal on the .md alone moves the leak one file over, and
# the .pdf cannot declare anything because it is never read as text at all.
#
# THE POSTURE, AND WHOSE CALL IT IS. Default: SEAL, and say so loudly on stdout and in the seal
# report. That is the fail-closed branch - a bundle missing a node's content leaks nothing, and an
# export that dies because a new file declared itself leaks nothing either but stops the work.
# ``--refuse-on-declaration`` is the other branch, one word away: the export refuses when the scan
# seals anything the literal lists did not already name, so a human rules on the file before any
# bundle travels. WHICH DEFAULT BINDS IS THE AUTHOR'S CALL, not settled here (the grammar was
# mine; the posture over his material is his). Until he rules, the fail-closed branch is live.
#
# BYTE ACCOUNTING, STATED PLAINLY, as the fingerprint tool states its own. The scan never opens a
# node under a sealed PREFIX. It does read the head of a node on the exact-path lists, because an
# instrument that trusts the hand list cannot check it (see ``scan_declarations``). It runs BEFORE
# pass 1, so a node it seals is never opened again and no body is ever read. The export's
# ``bytes_read_from_sealed: 0`` therefore stays true of CONTENT, which is what it measures, and
# the heads read from files that end up sealed are counted under their own honest name:
# ``declaration_head_bytes_read_from_declared``.
DECLARATION_GRAMMAR_VERSION = "1"
DECLARATION_WINDOW_BYTES = 2048
DECLARATION_LINE_PREFIX_BUDGET = 40
DECLARATION_QUALIFIER_LOOKAHEAD_LINES = 2

#: The topic token. Alone it binds nothing - clause 4 is what turns it into an instruction.
DECLARATION_TOKEN = re.compile(rb"never[-_ ]?public", re.I)

#: The closed vocabulary, as (label, pattern). Each entry is a phrase a file uses ABOUT ITSELF;
#: adding one widens the perimeter and is a deliberate edit, exactly like adding a line to the
#: literal lists. The LABEL is what a seal report names - a constant of this file, so the report
#: can say why a node was sealed without carrying a byte of the node.
DECLARATION_QUALIFIERS = (
    ("engine-repo only", rb"engine[- ]repo only"),
    ("must never enter", rb"must never enter"),
    ("must never travel", rb"must never travel"),
    ("must never leave", rb"must never leave"),
    ("never travel", rb"never travel"),
    ("sealed class", rb"sealed class"),
)
_DECLARATION_QUALIFIERS = tuple(
    (label, re.compile(pattern, re.I)) for label, pattern in DECLARATION_QUALIFIERS
)
_ANY_QUALIFIER = b"|".join(pattern for _, pattern in DECLARATION_QUALIFIERS)

#: Clause 4: a banner announces, then explains - a separator, the qualifier itself, or the end of
#: the line it stands on. Anything else after the token (a letter, a bracket) means the token is a
#: noun inside a sentence about the perimeter.
_DECLARATION_BANNER_PUNCT = re.compile(
    rb"^\s*(?:[-:,.!]|\xe2\x80\x94|\xe2\x80\x93|" + _ANY_QUALIFIER + rb"|$)", re.I,
)


def _qualifier_label(window: bytes) -> str | None:
    for label, pattern in _DECLARATION_QUALIFIERS:
        if pattern.search(window):
            return label
    return None

#: Decoration a banner may hide behind: markdown, line comments, docstring fences, TeX macros
#: and braces. Replaced with a space rather than deleted so two words never fuse into one.
_DECLARATION_DECOR = re.compile(rb"\\[a-zA-Z@]+\*?|\"\"\"|'''|//|/\*|\*/|[{}>#*_`|=\[\]%;]")


def normalize_declaration_line(raw: bytes) -> bytes:
    """Strip decoration, collapse whitespace. Clause 2 of the grammar, and nothing more."""
    return re.sub(rb"\s+", b" ", _DECLARATION_DECOR.sub(b" ", raw)).strip()


def declaration_binds(head: bytes) -> str | None:
    """Does this head DECLARE itself never-public? Returns the qualifier that bound, or None.

    The return value is drawn from ``DECLARATION_QUALIFIERS`` - this exporter's own fixed
    vocabulary - and never from the scanned bytes, so a seal report can name why a file was
    sealed without quoting a syllable of it.
    """
    if not DECLARATION_TOKEN.search(head):
        return None                       # the cheap gate: almost every node exits here
    lines = [normalize_declaration_line(raw) for raw in head.split(b"\n")]
    for i, line in enumerate(lines):
        hit = DECLARATION_TOKEN.search(line)
        if hit is None or hit.start() > DECLARATION_LINE_PREFIX_BUDGET:
            continue                      # clause 3: mid-line is prose, not a banner
        if not _DECLARATION_BANNER_PUNCT.match(line[hit.end():]):
            continue                      # clause 4: the token is a noun in a sentence
        window = b" ".join(
            [line[hit.end():]] + lines[i + 1: i + 1 + DECLARATION_QUALIFIER_LOOKAHEAD_LINES]
        )
        label = _qualifier_label(window) or _qualifier_label(line[:hit.start()])
        if label is not None:
            return label                  # clause 5, and the label is this file's, not the node's
    return None


def scan_declarations(repo_root: Path, rels: list[str]) -> dict[str, Any]:
    """Read heads, bind declarations, expand to every rendering. The self-maintaining half.

    WHAT IS SKIPPED, AND WHY THE LITERAL LISTS ARE NOT. Nodes under a sealed PREFIX are never
    opened - those bytes the seal forbids reading, full stop. Files on the exact-path lists ARE
    scanned, even though they are already sealed, because a scan that trusts the hand list can
    never disagree with it, and this file's own standing rule is that agreement is checked and
    never assumed. Scanning them makes the fourth class an INDEPENDENT instrument: the report
    then shows how much of the hand-maintained perimeter the machine reproduces on its own (five
    of six paths in this tree) and how much only the list can reach (one, the companion .json).
    Only the head is read, only paths and counts are emitted, and the head bytes read from files
    that end up sealed are counted separately as
    ``declaration_head_bytes_read_from_declared`` - the export's ``bytes_read_from_sealed: 0``
    remains a true statement about CONTENT, which is what it has always measured.
    """
    universe = set(rels)
    bound: dict[str, str] = {}
    near_misses: list[str] = []
    heads_read = 0
    head_bytes_read = 0
    declared_head_bytes = 0

    for rel in rels:
        if rel.startswith(BUNDLE_SEALED_PREFIXES):
            continue
        path = repo_root / rel
        if Path(rel).suffix.lower() not in TEXT_EXTENSIONS or not path.is_file():
            continue
        try:
            with open(path, "rb") as fh:
                head = fh.read(DECLARATION_WINDOW_BYTES)
        except OSError as exc:
            raise ExportRefusal(f"cannot read the head of {rel}: {exc}") from exc
        heads_read += 1
        head_bytes_read += len(head)
        qualifier = declaration_binds(head)
        if qualifier is not None:
            bound[rel] = qualifier
            declared_head_bytes += len(head)
        elif DECLARATION_TOKEN.search(head):
            near_misses.append(rel)

    # Index sibling renderings once; the old nested walk was O(declarations * nodes).
    siblings: dict[tuple[str, str], list[str]] = {}
    for rel in universe:
        path = Path(rel)
        siblings.setdefault((str(path.parent), path.stem), []).append(rel)
    renderings: dict[str, str] = {}
    for rel in sorted(bound):
        path = Path(rel)
        for other in siblings[(str(path.parent), path.stem)]:
            if other != rel and other not in bound:
                renderings[other] = f"rendering of {rel}"

    sealed = dict(bound)
    sealed.update(renderings)
    return {
        "sealed": sealed,
        "declared": bound,
        "renderings": renderings,
        "near_misses": sorted(near_misses),
        "heads_read": heads_read,
        "head_bytes_read": head_bytes_read,
        "declared_head_bytes": declared_head_bytes,
    }

# THE LAUNDERED-LEAK CHECK. The five paths above were found by a judge reading the corpus; this
# check finds the next one mechanically. Every unsealed TEXT node's bytes are scanned for
# occurrences of the sealed path prefixes, and a node whose density crosses the threshold is a
# derived store by signature, whatever its path says.
#
# The threshold is set on the measured gap, not by taste (2026-08-01, post-widening corpus):
# the five derived stores score 6,947 / 13,899 / 20,847 / 20,857 / 6,948 refs, while the highest
# scoring node that is NOT one of them scores 30 (``archive/self_shard/upfold_v0.json``). 100
# sits in a two-order-of-magnitude gap on both sides: far above prose that cites a sealed path,
# far below anything that indexes one. The live totals are NOT restated here - they are in every
# bundle's ``seal_report.json`` as ``sealed_path_refs_in_unsealed`` and ``sealed_path_ref_nodes``.
# This file is itself a node that references sealed paths, so a number written here changes the
# number it reports.
#
# The signature has a blind spot, named because an unnamed one is the dangerous kind: it measures
# sealed-PATH-REFERENCE density, so a derived store keyed by opaque ids would score zero. The
# complement is ``scripts/verify_seal_fingerprints.py``, which is content-based and path-blind.

# ``.jsonl`` is absent from the engine's ``_TEXT_EXT``, so the contract ledgers, the friction
# channel and the verbatim record floor enter the shard walk as name-only assets and the design's
# jsonl row-window segmenter would have nothing to segment. Added here as a named extension of
# the engine's list; ``text_extensions`` is a hashed manifest field, so it is visible in the id.
EXTRA_TEXT_EXTENSIONS = (".jsonl",)

SEALED_PREFIXES = tuple(self_shard._SEALED_PREFIXES) + EXTRA_SEALED_PREFIXES
BUNDLE_SEALED_PREFIXES = SEALED_PREFIXES + tuple(
    path for path in EXTRA_SEALED_PATHS if path.endswith("/")
)
TEXT_EXTENSIONS = frozenset(self_shard._TEXT_EXT) | frozenset(EXTRA_TEXT_EXTENSIONS)


def is_sealed(rel: str, declared: frozenset[str] = frozenset()) -> bool:
    """Sealed for a TRAVELLING bundle: the engine's zones, the prefix widening, the exact paths.

    The exact-path half is two lists with two rationales - ``DERIVED_FROM_SEALED_PATHS`` (soul
    content folded into a store at an ordinary path) and ``NEVER_PUBLIC_PATHS`` (a file whose own
    header forbids it to travel) - joined into ``EXTRA_SEALED_PATHS`` because the seal is one
    perimeter and one hashed manifest field.

    ``declared`` is the fourth class: what ``scan_declarations`` found by reading heads on this
    run. It is a UNION, never a replacement - the widest wins - and it defaults to empty so that
    a caller asking the standing question ("is this path on the declared perimeter?") gets the
    standing answer without paying for a scan.
    """
    return rel.startswith(BUNDLE_SEALED_PREFIXES) or rel in EXTRA_SEALED_PATHS or rel in declared


def count_sealed_refs(data: bytes) -> int:
    """Count the original sealed-source prefixes; derived output names do not change the gauge."""
    return sum(data.count(p.encode("utf-8")) for p in SEALED_PREFIXES)

DEFAULT_OUT_DIR = ROOT / "atlas" / "stores" / "snapshots"


class ExportRefusal(RuntimeError):
    """A named refusal. The exporter degrades loudly or not at all."""


# ---------------------------------------------------------------------------
# the hashing law, duplicated across the seal (src/atlas/ids.py)
# ---------------------------------------------------------------------------

def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def chash(obj: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def hash_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# the universe
# ---------------------------------------------------------------------------

def run_git(repo_root: Path, args: list[str], timeout: int) -> str:
    """Every git subprocess in the exporter runs through here, and the decode is pinned.

    ``text=True`` decodes with the platform default - cp1252 on Windows - which dies with a
    UnicodeDecodeError on any utf-8 multibyte path in the tree (measured 2026-08-11, byte
    1,076,870 of ``ls-tree`` output on the author's box), and the failed reader thread hands
    back ``stdout=None`` so the caller's ``.split()`` raises AttributeError instead of naming
    the cause. So: ``encoding="utf-8"`` explicitly, ``errors="strict"`` explicitly - a
    non-utf-8 byte is a named refusal, never a silently mangled path filed under a wrong blob
    - and a ``stdout is None`` refusal that names the command.
    """
    cmd = ["git", *args]
    shown = " ".join(cmd)
    try:
        out = subprocess.run(cmd, cwd=repo_root, capture_output=True,
                             encoding="utf-8", errors="strict", timeout=timeout, check=True)
    except UnicodeDecodeError as exc:
        raise ExportRefusal(f"`{shown}` output is not utf-8: {exc}") from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise ExportRefusal(f"`{shown}` failed: {exc}") from exc
    if out.stdout is None:
        raise ExportRefusal(f"`{shown}` returned no stdout (capture failed); refusing to guess")
    return out.stdout


def commit_sha(repo_root: Path) -> str:
    return run_git(repo_root, ["rev-parse", "HEAD"], timeout=30).strip()


def head_blobs(repo_root: Path) -> dict[str, str]:
    """path -> git blob sha at HEAD. ``-z`` so paths with odd bytes need no unquoting."""
    stdout = run_git(repo_root, ["ls-tree", "-r", "-z", "HEAD"], timeout=120)
    blobs: dict[str, str] = {}
    for entry in stdout.split("\0"):
        if not entry:
            continue
        meta, _, path = entry.partition("\t")
        parts = meta.split()
        if len(parts) >= 3 and path:
            blobs[path] = parts[2]
    return blobs


def git_blob_sha(data: bytes) -> str:
    """The sha git would file these bytes under - lets one pass compare content against HEAD."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def node_universe(repo_root: Path) -> list[str]:
    """Repo-relative paths, sorted and deduplicated, minus the derived stores."""
    rels: set[str] = set()
    for path in self_shard._tracked_files(repo_root):
        try:
            rel = str(Path(path).resolve().relative_to(repo_root)).replace("\\", "/")
        except ValueError:
            continue                       # outside the tree (a symlink target); not a node
        if rel.startswith(EXCLUDED_PREFIXES):
            continue
        rels.add(rel)
    return sorted(rels)


def node_record(repo_root: Path, rel: str,
                declared: frozenset[str] = frozenset()) -> tuple[dict[str, Any], bytes | None]:
    """One SnapshotNode row, plus the bytes to store as its blob (None when nothing was read)."""
    path = repo_root / rel
    ext = Path(rel).suffix.lower()
    sealed = is_sealed(rel, declared)

    if sealed:
        # Never opened, never stat'ed for size. Refs only: the path is the whole record.
        return ({
            "schema_version": SNAPSHOT_NODE_SCHEMA, "node_id": rel, "path": rel, "kind": "soul",
            "sealed": True, "is_text": False, "read_policy": "sealed-refs-only",
            "content_hash": REFS_ONLY, "content_blob": None, "size_bytes": 0,
        }, None)

    kind = ext.lstrip(".") or "data"
    if ext not in TEXT_EXTENSIONS:
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise ExportRefusal(f"cannot stat {rel}: {exc}") from exc
        return ({
            "schema_version": SNAPSHOT_NODE_SCHEMA, "node_id": rel, "path": rel, "kind": kind,
            "sealed": False, "is_text": False, "read_policy": "asset-not-read",
            "content_hash": NOT_READ, "content_blob": None, "size_bytes": size,
        }, None)

    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ExportRefusal(f"cannot read {rel}: {exc}") from exc
    key = hash_bytes(data)
    return ({
        "schema_version": SNAPSHOT_NODE_SCHEMA, "node_id": rel, "path": rel, "kind": kind,
        "sealed": False, "is_text": True, "read_policy": "text",
        "content_hash": key, "content_blob": key, "size_bytes": len(data),
    }, data)


# ---------------------------------------------------------------------------
# the bundle
# ---------------------------------------------------------------------------

def blob_path(blobs_root: Path, key: str) -> Path:
    hexd = key.split(":", 1)[1]
    return blobs_root / hexd[:2] / hexd


def promote(stage: Path, final: Path) -> None:
    """Move a staged bundle into place. An existing bundle at the same id is content-identical."""
    if not final.exists():
        stage.rename(final)
        return
    for src in sorted(stage.rglob("*")):
        if src.is_dir():
            continue
        dest = final / src.relative_to(stage)
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(src, dest)
    shutil.rmtree(stage, ignore_errors=True)


def export_policy(dial_set: dict[str, Any]) -> str:
    """A parent cannot certify rows under a different perimeter or classification law."""
    return chash({"version": EXPORTER_VERSION, "prefixes": BUNDLE_SEALED_PREFIXES,
                  "paths": EXTRA_SEALED_PATHS, "text": sorted(TEXT_EXTENSIONS),
                  "excluded": EXCLUDED_PREFIXES, "dials": dial_set,
                  "declaration": DECLARATION_GRAMMAR_VERSION})


def diff_paths(repo_root: Path, *revisions: str) -> dict[str, str]:
    fields = run_git(repo_root, ["diff", "--name-status", "--no-renames", "-z",
                                *revisions, "--"], 120).split("\0")
    return {fields[i + 1]: fields[i] for i in range(0, len(fields) - 1, 2)
            if not fields[i + 1].startswith(EXCLUDED_PREFIXES)}


def working_delta(repo_root: Path) -> dict[str, str]:
    changes = diff_paths(repo_root, "HEAD")
    for rel in run_git(repo_root, ["ls-files", "--others", "--exclude-standard", "-z"], 30).split("\0"):
        if rel and not rel.startswith(EXCLUDED_PREFIXES):
            changes[rel] = "A"
    return changes


def find_parent(repo_root: Path, out_dir: Path, sha: str, policy: str) -> dict[str, Any]:
    """Latest indexed, clean, complete ancestor bundle; verify before carrying any rows."""
    tracked = set(run_git(repo_root, ["ls-files", "-z"], 30).split("\0"))
    roots = {repo_root / "atlas/stores/snapshots", out_dir}
    candidates = []
    for root in roots:
        for path in root.glob("*/manifest.json"):
            try:
                rel = path.resolve().relative_to(repo_root.resolve()).as_posix()
            except ValueError:
                continue
            if any(str(Path(rel).with_name(name)).replace("\\", "/") not in tracked
                   for name in ("manifest.json", "nodes.jsonl", "seal_report.json")):
                continue
            try:
                man = json.loads(path.read_bytes())
            except (OSError, ValueError) as exc:
                raise ExportRefusal(f"PARENT-MANIFEST-INVALID: {rel}: {exc}") from exc
            if (man.get("tree_dirty") is not False or man.get("node_limit") is not None
                    or man.get("exporter_version") != EXPORTER_VERSION):
                continue
            ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", man["commit_sha"], sha],
                                      cwd=repo_root, capture_output=True)
            if ancestor.returncode == 1:
                continue
            if ancestor.returncode:
                raise ExportRefusal(f"PARENT-ANCESTRY-UNAVAILABLE: {rel}")
            candidates.append((man.get("created_ts", ""), rel, path, man))
    for _, rel, path, man in sorted(candidates, reverse=True):
        if man["snapshot_id"] != chash({k: v for k, v in man.items()
                                       if k not in ("snapshot_id", "created_ts")}):
            raise ExportRefusal(f"PARENT-IDENTITY-MISMATCH: {rel}")
        try:
            nodes_bytes = path.with_name("nodes.jsonl").read_bytes()
            report_bytes = path.with_name("seal_report.json").read_bytes()
            report = json.loads(report_bytes)
            rows = [json.loads(line) for line in nodes_bytes.splitlines() if line]
        except (OSError, ValueError) as exc:
            raise ExportRefusal(f"PARENT-SIDECAR-INVALID: {rel}: {exc}") from exc
        if (hash_bytes(nodes_bytes) != man["nodes_sha256"]
                or hash_bytes(report_bytes) != man["seal_report_sha256"]):
            raise ExportRefusal(f"PARENT-SIDECAR-HASH-MISMATCH: {rel}")
        if report.get("export_policy") != policy:
            continue
        if len(rows) != man["node_count"] or len({r["node_id"] for r in rows}) != len(rows):
            raise ExportRefusal(f"PARENT-NODE-EXTENT-MISMATCH: {rel}")
        return {"manifest": man, "rows": rows, "report": report}
    raise ExportRefusal("PARENT-UNAVAILABLE: no compatible tracked clean ancestor; run --full, then track its metadata")


def incremental_scan(repo_root: Path, rels: list[str], changed: set[str],
                     parent_report: dict[str, Any]) -> dict[str, Any]:
    universe = set(rels)
    scan = scan_declarations(repo_root, sorted(changed & universe))
    bound = {p: why for p, why in parent_report["declaration_declared_paths"].items()
             if p in universe and p not in changed}
    bound.update(scan["declared"])
    siblings: dict[tuple[str, str], list[str]] = {}
    for rel in rels:
        path = Path(rel)
        siblings.setdefault((str(path.parent), path.stem), []).append(rel)
    renderings = {}
    for rel in sorted(bound):
        path = Path(rel)
        for other in siblings[(str(path.parent), path.stem)]:
            if other != rel and other not in bound:
                renderings[other] = f"rendering of {rel}"
    scan.update(declared=bound, renderings=renderings, sealed={**bound, **renderings},
                near_misses=sorted(set(scan["near_misses"]) | {
                    p for p in parent_report["declaration_near_miss_paths"]
                    if p in universe and p not in changed}))
    return scan


def export(repo_root: Path, out_dir: Path, limit: int | None = None,
           allow_dirty: bool = False,
           refuse_on_declaration: bool = False, *, full: bool = False,
           with_blobs: bool = False) -> dict[str, Any]:
    dial_set = dials.current("atlas-export")
    SEALED_REF_THRESHOLD = dial_set["dials"]["sealed_ref_threshold"]["value"]
    SEALED_REF_TOP_N = dial_set["dials"]["sealed_ref_top_n"]["value"]
    repo_root = repo_root.resolve()
    sha = commit_sha(repo_root)
    policy = export_policy(dial_set)
    parent = None if full else find_parent(repo_root, out_dir, sha, policy)
    if parent and limit is not None:
        raise ExportRefusal("LIMIT-REQUIRES-FULL: a partial universe cannot carry a parent")
    # Git catches deleted, sealed and asset changes without reading sealed contents ourselves.
    try:
        work_changes = working_delta(repo_root) if (repo_root / ".git").exists() else {}
    except ExportRefusal:
        if (repo_root / ".git").exists():
            raise
        work_changes = {}  # non-Git fixture provenance is supplied by head_blobs
    if work_changes and not allow_dirty:
        raise ExportRefusal(f"working tree is dirty against {sha[:12]}: "
                            f"{len(work_changes)} paths; use --allow-dirty (with blobs)")
    head = head_blobs(repo_root) if full or work_changes else {}
    parent_rows = {r["node_id"]: r for r in parent["rows"]} if parent else {}
    changes = diff_paths(repo_root, parent["manifest"]["commit_sha"] + ".." + sha) if parent else {}
    for rel, status in work_changes.items():
        if parent and rel not in parent_rows and status == "D":
            changes.pop(rel, None)
        else:
            changes[rel] = ("D" if status == "D" else
                            "M" if rel in parent_rows else "A")
    if parent:
        for rel, status in changes.items():
            if status != "D" and (repo_root / rel).resolve() != repo_root / rel:
                raise ExportRefusal(f"ALIASED-PATH-REQUIRES-FULL: {rel}")
        universe = set(parent_rows)
        for rel, status in changes.items():
            if status == "D":
                universe.discard(rel)
            else:
                universe.add(rel)
        rels = sorted(universe)
        scan = incremental_scan(repo_root, rels, set(changes), parent["report"])
    else:
        rels = node_universe(repo_root)
        if limit is not None:
            rels = rels[:limit]
        scan = scan_declarations(repo_root, rels)
    changed = set(changes) if parent else set(rels)
    # A changed declaration can change a sibling rendering's seal without changing its bytes.
    seal_affected = {rel for rel in rels if rel in parent_rows
                     and parent_rows[rel]["sealed"] != is_sealed(rel, frozenset(scan["sealed"]))}
    changed.update(seal_affected)
    diff_counts = {"added": sum(v == "A" for v in changes.values()),
                   "modified": sum(v != "A" and v != "D" for v in changes.values()),
                   "deleted": sum(v == "D" for v in changes.values()),
                   "seal_affected": len(seal_affected)}

    declared = frozenset(scan["sealed"])
    new_to_the_lists = sorted(p for p in declared if p not in set(EXTRA_SEALED_PATHS))
    if refuse_on_declaration and new_to_the_lists:
        raise ExportRefusal(
            f"{len(new_to_the_lists)} node(s) declare themselves never-public in their own head "
            f"and are not on the exporter's literal lists. Under --refuse-on-declaration the "
            f"export stops so a human rules on them before any bundle travels; without the flag "
            f"they are sealed and named in seal_report.json. First few: "
            + ", ".join(new_to_the_lists[:5])
        )

    # PASS 1 - classify and MEASURE. Nothing is written here, deliberately: every refusal below
    # must be able to fire before a single byte reaches the disk, or a refused export leaves a
    # staging directory behind whose metadata files are committable (the ignore rules key on
    # blobs/ and spans.jsonl). Text bytes are read, hashed, scanned and dropped; pass 2 re-reads
    # them to write blobs, and re-hashes to catch a file that moved between the passes.
    rows: list[dict[str, Any]] = []
    text_n = sealed_n = asset_n = 0
    total_bytes = 0
    skipped_non_files = 0
    sealed_refs: list[tuple[int, str]] = []
    dirty: list[list[str]] = [[p, status] for p, status in work_changes.items()]
    parent_refs = parent["report"]["sealed_path_refs_by_node"] if parent else {}
    for rel in rels:
        carried = rel in parent_rows and rel not in changed
        if carried:
            row, data = parent_rows[rel], None
        else:
            path = repo_root / rel
            if not path.is_file():
                skipped_non_files += 1
                continue
            row, data = node_record(repo_root, rel, declared)
        rows.append(row)
        if row["sealed"]:
            sealed_n += 1
        elif row["read_policy"] == "asset-not-read":
            asset_n += 1
        else:
            text_n += 1
            total_bytes += row["size_bytes"]
            refs = parent_refs.get(rel, 0) if carried else count_sealed_refs(data)
            if refs:
                sealed_refs.append((refs, rel))
        # Provenance against HEAD. Sealed and unread-asset nodes are checked for PRESENCE only -
        # comparing their content would mean reading bytes the seal forbids reading.
        if carried or (parent and not work_changes):
            continue
        if rel not in head:
            dirty.append([rel, row["content_hash"]])
        elif data is not None and git_blob_sha(data) != head[rel]:
            dirty.append([rel, row["content_hash"]])

    rows.sort(key=lambda r: r["node_id"])
    dirty = sorted(dict(dirty).items())

    # --- REFUSALS. All of them, before any write. -----------------------------------------

    # The seal counts are COMPUTED from the rows, not asserted. A leaking bundle must never
    # reach the disk in the first place.
    soul_with_content = sum(
        1 for r in rows
        if (r["sealed"] or r["path"].startswith(BUNDLE_SEALED_PREFIXES))
        and r["content_blob"] is not None
    )
    if soul_with_content:
        raise ExportRefusal(f"{soul_with_content} sealed node(s) carry content; refusing to write")

    # THE LAUNDERED-LEAK REFUSAL. A path-prefix seal cannot see soul content folded into a
    # derived store at an ordinary path; ref density can. Sealed nodes are not scanned - they
    # carry no bytes - so a store on EXTRA_SEALED_PATHS never reaches this test.
    launderers = sorted((r for r in sealed_refs if r[0] > SEALED_REF_THRESHOLD), reverse=True)
    if launderers:
        named = "\n".join(f"  {rel} ({n} refs)" for n, rel in launderers)
        raise ExportRefusal(
            f"{len(launderers)} unsealed node(s) reference sealed paths above the "
            f"{SEALED_REF_THRESHOLD}-ref threshold - a derived-store signature, and "
            f"derived-from-sealed is sealed for a travelling bundle. Seal them by adding them to "
            f"EXTRA_SEALED_PATHS if derived, or fix genuinely unsealed source references:\n"
            f"{named}"
        )

    if dirty and not allow_dirty:
        raise ExportRefusal(
            f"working tree is dirty against {sha[:12]}: {len(dirty)} node(s) are absent from or "
            f"differ at HEAD, so this bundle is NOT rebuildable from its commit_sha. Pass "
            f"--allow-dirty to export anyway (the manifest will record tree_dirty=true and a "
            f"dirty_nodes_hash naming the delta). First few: "
            + ", ".join(p for p, _ in dirty[:5])
        )

    nodes_bytes = "".join(canonical_json(r) + "\n" for r in rows).encode("utf-8")
    # ONE hashed exact-path perimeter, in a stable order: the three literal lists as written, then
    # whatever the scan added this run, sorted. No new manifest FIELD is minted for the fourth
    # class on purpose - ``atlas.schema.RecordSnapshot`` recomputes the snapshot id from the field
    # set it knows, so a field the atlas side has never heard of would make every bundle fail
    # verification. The perimeter widens inside ``sealed_paths``, where it already lived.
    exact_perimeter = list(EXTRA_SEALED_PATHS) + new_to_the_lists
    seal_report = {
        "soul_paths_with_content": soul_with_content,
        "sealed_spans": 0,                     # no spans in a bundle at export; atlas recounts
        "sealed_nodes": sealed_n,
        "bytes_read_from_sealed": 0,
        "sealed_prefixes": list(BUNDLE_SEALED_PREFIXES),
        "engine_sealed_prefixes": list(self_shard._SEALED_PREFIXES),
        "exporter_widening": list(EXTRA_SEALED_PREFIXES),
        "exporter_sealed_paths": exact_perimeter,
        # The exact-path perimeter, split by rationale so a reader of a travelling bundle can
        # tell a derived store from a file that declared itself never-public.
        "exporter_derived_from_sealed_paths": list(DERIVED_FROM_SEALED_PATHS),
        "exporter_never_public_paths": list(NEVER_PUBLIC_PATHS),
        "exporter_excerpt_carrier_paths": list(EXCERPT_CARRIER_PATHS),
        # THE FOURTH CLASS, self-maintaining: what the heads declared on THIS run. Paths and
        # counts only, and the "why" is drawn from this exporter's own closed qualifier
        # vocabulary - never a byte of a scanned file reaches the report.
        "declaration_grammar_version": DECLARATION_GRAMMAR_VERSION,
        "declaration_window_bytes": DECLARATION_WINDOW_BYTES,
        "declaration_qualifiers": [label for label, _ in DECLARATION_QUALIFIERS],
        "declaration_sealed_paths": sorted(scan["sealed"]),
        "declaration_declared_paths": {k: scan["declared"][k] for k in sorted(scan["declared"])},
        "declaration_rendering_paths": sorted(scan["renderings"]),
        "declaration_paths_new_to_the_literal_lists": new_to_the_lists,
        # Near-misses: token in the head, grammar not satisfied. Named so the borderline cases
        # are a surface a reader can audit rather than a silent discard.
        "declaration_near_miss_paths": scan["near_misses"],
        "declaration_heads_read": scan["heads_read"],
        "declaration_head_bytes_read": scan["head_bytes_read"],
        "declaration_head_bytes_read_from_declared": scan["declared_head_bytes"],
        "declaration_posture": "refuse" if refuse_on_declaration else "seal-and-report",
        "nodes_scanned": len(changed & set(rels)),
        "export_policy": policy,
        "sealed_path_refs_by_node": {rel: n for n, rel in sealed_refs},
        # The laundered-leak instrument: a COUNTED number, not an assertion. Zero would be a
        # claim; this is the measurement that a future derived store has to climb past.
        "sealed_path_refs_in_unsealed": sum(n for n, _ in sealed_refs),
        "sealed_path_ref_nodes": len(sealed_refs),
        "sealed_path_ref_threshold": SEALED_REF_THRESHOLD,
        "sealed_path_ref_top": [
            {"node_id": rel, "refs": n}
            for n, rel in sorted(sealed_refs, reverse=True)[:SEALED_REF_TOP_N]
        ],
    }
    seal_bytes = (canonical_json(seal_report) + "\n").encode("utf-8")

    manifest = {
        "schema_version": RECORD_SNAPSHOT_SCHEMA,
        "atlas_schema_version": ATLAS_SCHEMA_VERSION,
        "exporter_version": EXPORTER_VERSION,
        "source_repo": ".",
        "parent_snapshot": parent["manifest"]["snapshot_id"] if parent else None,
        "diff_counts": diff_counts,
        "commit_sha": sha,
        "node_count": len(rows),
        "text_node_count": text_n,
        "sealed_node_count": sealed_n,
        "asset_node_count": asset_n,
        "total_content_bytes": total_bytes,
        "nodes_sha256": hash_bytes(nodes_bytes),
        "seal_report_sha256": hash_bytes(seal_bytes),
        "sealed_prefixes": list(BUNDLE_SEALED_PREFIXES),
        "sealed_paths": exact_perimeter,
        "excluded_prefixes": list(EXCLUDED_PREFIXES),
        "text_extensions": sorted(TEXT_EXTENSIONS),
        "node_limit": limit,
        # Provenance, hashed: a bundle is rebuildable from commit_sha only when tree_dirty is
        # false. When it is true, dirty_nodes_hash names the delta - chash over the sorted
        # (path, content_hash) pairs of every node absent from or differing at HEAD - so two
        # dirty exports of the SAME working tree still agree, and a different delta is a
        # different snapshot.
        "tree_dirty": bool(dirty),
        "dirty_node_count": len(dirty),
        "dirty_nodes_hash": chash(dirty),
    }
    snapshot_id = chash(manifest)          # created_ts is not in the dict yet: never hashed
    manifest["snapshot_id"] = snapshot_id
    manifest["created_ts"] = datetime.now(timezone.utc).isoformat()

    # PASS 2 - WRITE. Everything that could refuse has refused; from here the only exits are a
    # successful promote or an error, and the finally clause removes the staging directory on
    # both. A staging directory that outlives the process is not merely litter: its metadata
    # files are committable, because the ignore rules key on blobs/ and spans.jsonl.
    out_dir.mkdir(parents=True, exist_ok=True)
    stage = out_dir / f".staging-{os.getpid()}"
    final = out_dir / snapshot_id.split(":", 1)[1]   # hex only: ':' is not a legal Windows path
    try:
        if stage.exists():
            shutil.rmtree(stage)
        blobs_root = stage / "blobs"
        for row in rows if (with_blobs or dirty) else []:
            if row["read_policy"] != "text":
                continue
            dest = blob_path(blobs_root, row["content_blob"])
            if dest.is_file():
                continue
            try:
                data = (repo_root / row["node_id"]).read_bytes()
            except OSError as exc:
                raise ExportRefusal(f"cannot re-read {row['node_id']}: {exc}") from exc
            # The file moved between the measuring pass and the writing pass. Refuse rather than
            # file bytes under a key the manifest says belongs to different bytes.
            if hash_bytes(data) != row["content_hash"]:
                raise ExportRefusal(
                    f"{row['node_id']} changed during export; re-run against a settled tree"
                )
            write_atomic(dest, data)
        write_atomic(stage / "nodes.jsonl", nodes_bytes)
        write_atomic(stage / "seal_report.json", seal_bytes)
        write_atomic(stage / "manifest.json",
                     (json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False) + "\n")
                     .encode("utf-8"))
        if (repo_root / ".git").exists() and (commit_sha(repo_root) != sha
                or working_delta(repo_root) != work_changes):
            raise ExportRefusal("TREE-MOVED-DURING-EXPORT: retry against a settled tree")
        promote(stage, final)
    finally:
        shutil.rmtree(stage, ignore_errors=True)

    return {"snapshot_id": snapshot_id, "path": final, "manifest": manifest,
            "seal_report": seal_report, "skipped_non_files": skipped_non_files,
            "declaration_scan": scan}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="export a RecordSnapshot bundle for the atlas")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--limit", type=int, default=None,
                        help="export only the first N nodes; recorded in the hashed manifest so "
                             "a limited bundle can never collide with a full one")
    parser.add_argument("--full", action="store_true", help="rebuild every node without a parent")
    parser.add_argument("--with-blobs", action="store_true", help="copy bytes for a travelling bundle")
    parser.add_argument("--allow-dirty", action="store_true",
                        help="export from a working tree that differs from HEAD; the bundle is "
                             "then NOT rebuildable from commit_sha alone and says so")
    parser.add_argument("--refuse-on-declaration", action="store_true",
                        help="refuse the export when the head scan seals a file the literal "
                             "lists did not already name, instead of sealing it and reporting. "
                             "The author's posture call; the default is the fail-closed seal")
    args = parser.parse_args(argv)

    started = time.perf_counter()
    try:
        out = export(ROOT, args.out_dir, args.limit, allow_dirty=args.allow_dirty,
                     refuse_on_declaration=args.refuse_on_declaration,
                     full=args.full, with_blobs=args.with_blobs)
    except ExportRefusal as exc:
        print(f"REFUSED {exc}", file=sys.stderr)
        return 2
    man = out["manifest"]
    report = out["seal_report"]
    print(f"snapshot_id       {out['snapshot_id']}")
    print(f"path              {out['path']}")
    print(f"parent_snapshot   {man['parent_snapshot']}")
    print(f"diff_counts       {canonical_json(man['diff_counts'])}")
    print(f"commit_sha        {man['commit_sha']}")
    print(f"tree_dirty        {man['tree_dirty']} ({man['dirty_node_count']} nodes) "
          f"{man['dirty_nodes_hash']}")
    print(f"nodes             {man['node_count']} ({man['text_node_count']} text, "
          f"{man['sealed_node_count']} sealed, {man['asset_node_count']} asset)")
    print(f"content_bytes     {man['total_content_bytes']}")
    print(f"nodes_sha256      {man['nodes_sha256']}")
    print(f"sealed_path_refs  {report['sealed_path_refs_in_unsealed']} across "
          f"{report['sealed_path_ref_nodes']} unsealed nodes "
          f"(max {report['sealed_path_ref_top'][0]['refs'] if report['sealed_path_ref_top'] else 0}"
          f", threshold {report['sealed_path_ref_threshold']})")
    # THE SCAN SPEAKS. Silence here would make the fourth class the only part of the perimeter a
    # reader of the run cannot see; every declaration-sealed path is named on stdout.
    print(f"declaration scan  {report['declaration_heads_read']} heads read "
          f"({report['declaration_head_bytes_read']} B, window {DECLARATION_WINDOW_BYTES}), "
          f"grammar v{report['declaration_grammar_version']}, "
          f"posture {report['declaration_posture']}")
    print(f"  sealed by head    {len(report['declaration_sealed_paths'])} "
          f"({len(report['declaration_declared_paths'])} declared, "
          f"{len(report['declaration_rendering_paths'])} renderings); "
          f"{len(report['declaration_paths_new_to_the_literal_lists'])} new to the literal lists")
    for rel, why in report["declaration_declared_paths"].items():
        print(f"      DECLARED   {rel}  [{why}]")
    for rel in report["declaration_rendering_paths"]:
        print(f"      RENDERING  {rel}")
    print(f"  near misses       {len(report['declaration_near_miss_paths'])} "
          f"(token in head, grammar not satisfied)")
    for rel in report["declaration_near_miss_paths"]:
        print(f"      near       {rel}")
    print(f"skipped_non_file  {out['skipped_non_files']}")
    print(f"wall_clock        {time.perf_counter() - started:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
