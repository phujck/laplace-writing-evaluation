"""The digest mint - a node's CLAIM, mechanically extracted from its own members, banked as a row.

WHY THIS EXISTS (the six red thread probes, holdout/THREAD_PROBES.json). Three of the reds were
minted on 2026-08-23 and re-stamped the same night with the measured cause written into them:
"fresh content-grade queries missing on title-grade handles". A concept cluster's handle is
``meaning_upfold._label``'s six tf*idf keywords over its members' PATH keywords - so a query that
names a MECHANISM ("closure residual coupling between scales") is scored against a bag of file-name
words. The node knows what it holds; its handle does not say it. That gap is the digest's whole
subject.

WHAT A DIGEST IS, AND WHAT IT IS NOT. A content-grade digest answers what its grade owes: the CLAIM
(one line), the MECHANISM, and the LOAD-BEARING OBJECTS (equations, constants, identifiers a content
question would grep for). CLAIM-GRADE is the only grade minted here - one line, claim plus object
tokens - and the tower deepens later only where the question-form meter fails. Everything in this
module is MECHANICAL: sentences ranked by tf*idf against SIBLING clusters (the same math as
``meaning_upfold._label`` at :731, at sentence grade instead of keyword grade), object tokens
harvested by regex classes. There is NO model call anywhere on this path, by construction: a row
carrying ``method="composed"`` and no ``src_pointers`` is a DEFECT, not a richer digest.

LENS, NEVER LEAVES (the residue-tree law). ``keeper.build_self`` clusters by meaning only what NO
lens claims, so anything written into a shard/leaf store RECLUSTERS as content and the tree folds its
own summaries back into itself. Digests therefore live in their own store (``.digests.jsonl``) and
join the readers through ``laplace.engine.digest_lens``, which mirrors ``laplace.engine.distillate_lens``: one
typed referent per load-bearing object, minted on the digested node and on the leaves that supplied
it, merged into the substrate edge-index ``keeper_ring.build_reach`` folds into ``reach``. Same
channel, same guard, same law.

THE KEY. Rows are keyed ``(node_id, member_sha, basis, grade)``.

  * ``node_id`` derives from FOUNDING membership - ``meaning_upfold._cluster_id`` is a sha1 over the
    sorted member leaf ids at the moment the cluster was first cut, and it is deliberately stable
    across rebuilds so an unchanged cluster never re-embeds.
  * ``member_sha`` is a sha256 over the node's CURRENT sorted leaf descendants. Accretion drifts
    that set while the id stays put, so the pair is exactly the lineage-vs-current handle drift
    detection needs: same id + different member_sha IS the drift, stated rather than inferred.
  * ``basis`` is the tree's ``lens_hash`` - which lens partition the membership was read under. It
    is RECORDED PROVENANCE and, since the verify wave's cure A1, never a serve gate: the hash takes
    a new value nearly every close, so gating on it darkened the whole layer every close.
  * ``grade`` is which storey of the tower this row is. ``claim`` is the only value today, and that
    is exactly why it is in the key now: without it, the first mechanism-grade mint of an unchanged
    node reads as ``already banked`` and silently banks nothing.

Serving is ``digest_lens``'s call, not the mint's: exact ``member_sha`` serves; Jaccard overlap at or
above ``DRIFT_FLOOR`` serves marked inherited-with-drift; below that the row is STALE and serves
nothing. Only the stale TRANSITION banks a new row, and banking is the orchestrator's hand - this
module writes only when told to (``--run``), and never on a lens read. The lens RE-APPLIES the
defect law on read (``digest_lens.conformance``): this module's ``_defective`` guards the write
boundary, and a store is a file that anything can append to.

COST. Every entry point reports VOLUME x RATE. The mint is pure CPU file I/O plus regex; the demand
set pays one embedder load and one descent per probe, and the descender is opened ONCE and reused.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

DIGEST_STORE = ".digests.jsonl"
SCHEMA = "digest/0.1"
GRADE = "claim"                 # the ONLY grade minted now; the tower deepens where the meter fails
METHOD = "extracted"            # the only honest value on this path - see the module docstring

# --- declared dials ---------------------------------------------------------
DRIFT_FLOOR = 0.8       # Jaccard(banked members, current members) at/above this = serve-with-drift
READ_CAP = 64           # member files read per node. member_sha still covers ALL members; the row
                        # banks n_members and n_read so a claim drawn from a sample says so.
FILE_CHARS = 120_000    # per-file read cap - a claim is never in the tail of a 2 MB store row
MIN_SENT = 40           # a "sentence" shorter than this is a fragment, not a claim
MAX_SENT = 400          # ... and a candidate is cut at its LAST terminator inside this, or dropped
N_OBJECTS = 12          # load-bearing object tokens banked per digest
N_SRC = 16              # src_pointers banked per digest (mandatory, never empty)
N_CLAIM_SENTS = 3       # sentences whose pointers are banked behind the claim
IDF_CLIMB = 3           # levels to climb looking for >= 2 contrast documents before falling back

# the readable member classes. A binary member (png/pdf) carries no sentences and is skipped, named.
TEXT_EXT = {".md", ".py", ".json", ".jsonl", ".tex", ".txt", ".sh", ".yaml", ".yml", ".toml",
            ".cfg", ".ini", ".js", ".mjs", ".ts", ".csv", ".bib", ".rst", ".html", ".css"}

_STOP = {"a", "an", "and", "the", "of", "to", "in", "is", "it", "for", "on", "with", "md", "py",
         "json", "tex", "as", "at", "by", "or", "be", "that", "this", "are", "was", "not", "but",
         "from", "has", "have", "its", "than", "then", "so", "no", "one", "two", "we", "you"}


def _term_ok(w: str) -> bool:
    """``meaning_upfold._label_ok``'s gate, widened by the prose stopwords a SENTENCE carries and a
    path keyword never did. Same shape, one grade down."""
    return len(w) > 2 and not w.isdigit() and w not in _STOP


_WORD_RE = re.compile(r"[a-z0-9_]+")


def _terms(text: str) -> list[str]:
    return [w for w in _WORD_RE.findall(text.lower()) if _term_ok(w)]


# ---------------------------------------------------------------------------
# the object classes - what a CONTENT question would grep for
# ---------------------------------------------------------------------------

_OBJECT_CLASSES: list[tuple[str, re.Pattern[str]]] = [
    # latex: inline math, display math, and a named equation environment's body
    ("latex", re.compile(r"\$[^$\n]{3,120}\$|\\\[[^\]\n]{3,160}\\\]"
                         r"|\\begin\{(?:equation|align)\*?\}(.{3,200}?)\\end\{(?:equation|align)\*?\}",
                         re.S)),
    # a numeric constant WITH ITS CONTEXT - a bare number is noise, "0.8 jaccard" is an object
    ("numeric", re.compile(r"\b(\d+(?:\.\d+)?(?:[eE][-+]?\d+)?%?)\s*([A-Za-z_][A-Za-z0-9_-]{2,24})"
                           r"|\b([A-Za-z_][A-Za-z0-9_-]{2,24})\s*[=:]\s*(\d+(?:\.\d+)?(?:[eE][-+]?\d+)?%?)")),
    # code/path identifiers: dotted calls, module paths, real file names
    ("ident", re.compile(r"\b[A-Za-z_][\w.]*\(\)|\b[\w./-]+\.(?:py|md|json|jsonl|tex|sh|yaml|toml)\b")),
    ("camel", re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+\b")),
    ("snake", re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")),
    ("upper", re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")),
]


# A NUL in any form is not an object (cure B3). ``read_member`` rejects a file with raw NUL bytes,
# but a store row that JOINS ids on NUL carries the escape `\u0000` as ordinary text - and
# `digest::u0000eigen-diary-md` was proven wired into reach off exactly that. The escape names a
# separator, never a thing a content question could grep for.
_NUL_RE = re.compile(r"\x00|\\?u0000", re.I)


def object_tokens(text: str) -> list[tuple[str, str]]:
    """``[(class, token)]`` harvested from one member's text by the regex classes above, in file
    order. Nothing is ranked here - ranking is tf*idf against the siblings, done by the caller over
    the whole node, so a token common to every sibling cannot win on raw frequency. A token
    carrying a NUL in any form (raw byte or JSON escape) is dropped - see ``_NUL_RE``."""
    out: list[tuple[str, str]] = []
    for cls, rx in _OBJECT_CLASSES:
        for m in rx.finditer(text):
            if cls == "numeric":
                groups = [g for g in m.groups() if g]
                tok = " ".join(groups[:2]) if len(groups) >= 2 else m.group(0)
            elif cls == "latex" and m.lastindex:
                tok = (m.group(1) or m.group(0))
            else:
                tok = m.group(0)
            tok = " ".join(tok.split())[:120]
            if len(tok) >= 3 and not _NUL_RE.search(tok):
                out.append((cls, tok))
    return out


# ---------------------------------------------------------------------------
# the reproducible sentence index - what a src_pointer POINTS AT
# ---------------------------------------------------------------------------

_PARA_RE = re.compile(r"\n\s*\n")
_ENDER_RE = re.compile(r"(?<=[.!?])\s+")

# A line that OPENS a new logical unit instead of continuing the one above it: a markdown bullet, a
# numbered item, a heading, a table row, a block quote, a fence (all of which may be indented), or a
# store row - `{`/`[` AT COLUMN 0, which is what a jsonl row looks like and what an INDENTED LaTeX
# brace continuation does not. Measured: with the brace opener allowed at any indent, a hard-wrapped
# `\bibfield {author} {\bibinfo ...` bibliography line was cut into a fragment claim and banked.
# Anything not matching this, under a line that has not yet ended, is a HARD WRAP and is joined back.
_OPENER_RE = re.compile(r"\s*(?:[-*+]\s|\d+[.)]\s|#{1,6}\s|>|\||```|~~~|\\[a-zA-Z]|\{|\[)")
# A SENTENCE TERMINATOR: `.!?` plus any closing quote/bracket, followed by whitespace or the end of
# the candidate. The lookahead is what keeps `0.8` and `v1.2` out - their dot is followed by a digit,
# never by space - so a decimal can never be mistaken for the end of a claim.
_TERM_RE = re.compile(r"[.!?][\"')\]]*(?=\s|$)")
_ENDS_TERM_RE = re.compile(r"[.!?][\"')\]]*$")

# A CLAIM BEGINS LIKE A CLAIM (the re-verify wave's begin defect): _ENDER_RE splits on the
# abbreviation period inside a BibTeX field ('Blume, D.' | 'B.}, month = mar, ...'), so a
# candidate can BEGIN mid-record. _clip polices where a claim ends; this polices where it
# begins. Three continuation shapes, all measured on the five offending rows: a short token
# closing a brace/quote then a comma ('B.},' / 'Bondar},' / '{Hanggi}},'), a candidate that
# OPENS on a bib-field assignment ('journal ="Phys.'), and one carrying two or more field
# assignments anywhere ('month = mar, year = {1997}' - whitespace-tolerant on purpose: the
# census hole that hid c29f9c02cd was `year = {1997}` against a spaceless regex).
_BEGIN_BAD_RE = re.compile(r"^(?:\S{0,16}[}\]\"'],|\w+\s*=\s*[{\"'])")
_BIBFIELD_RE = re.compile(r"\b\w+\s*=\s*[{\"']")


def claimlike(sent: str) -> bool:
    """May this sentence be a CLAIM candidate? (It stays in ``sentences()`` and keeps its index -
    pointers and object harvesting are untouched - it is barred from the claim slot only.)"""
    if _BEGIN_BAD_RE.match(sent):
        return False
    return len(_BIBFIELD_RE.findall(sent)) < 2


def _unwrap(para: str) -> list[str]:
    """One paragraph's LOGICAL lines - hard-wrapped continuations joined back onto the line above.

    THE MEASURED DISEASE (the DP-A2 verify wave). The first form split on physical lines, so every
    hard-wrapped markdown paragraph in this corpus produced LINE FRAGMENTS rather than sentences:
    27 of 45 live claims were cut mid-word and only 10 ended on a terminator. A hard wrap is a line
    break INSIDE a sentence, so the cure is to undo it before splitting - and to undo only that: a
    bullet, a heading, a table row and a jsonl row each open a unit of their own and are never
    joined to their neighbour (joining them would fuse a whole bullet list into one terminator-less
    blob and lose every claim in it)."""
    out: list[str] = []
    for raw in para.split("\n"):
        line = " ".join(raw.split())
        if not line:
            continue
        if out and not _OPENER_RE.match(raw) and not _ENDS_TERM_RE.search(out[-1]):
            out[-1] = f"{out[-1]} {line}"
        else:
            out.append(line)
    return out


def _clip(s: str) -> str:
    """The candidate cut at its LAST sentence terminator inside ``MAX_SENT``, or ``""`` when it has
    none there. A claim ends where a sentence ends: never mid-word, never mid-clause, and never at
    character 400 of a run-on. A candidate with no terminator in range is not a claim candidate at
    all - it is a fragment, and the honest thing to do with a fragment is drop it."""
    out = ""
    for m in _TERM_RE.finditer(s):
        if m.end() > MAX_SENT:
            break
        out = s[:m.end()]
    return out


def sentences(text: str) -> list[str]:
    """The canonical sentence list of one member's text. ``src_pointers`` index into THIS list, so
    the derivation is the contract: paragraphs, then LOGICAL lines (``_unwrap`` - hard wraps joined,
    bullets and store rows kept apart), then sentence enders; whitespace collapsed; fragments under
    ``MIN_SENT`` dropped; and every survivor cut at its last terminator inside ``MAX_SENT`` or
    dropped for having none (``_clip``). Deterministic and re-derivable from the file alone, which
    is what makes a pointer checkable."""
    out: list[str] = []
    for para in _PARA_RE.split(text):
        for line in _unwrap(para):
            for s in _ENDER_RE.split(line):
                s = " ".join(s.split())
                if len(s) < MIN_SENT:
                    continue
                s = _clip(s)
                if len(s) < MIN_SENT:
                    continue
                out.append(s)
    return out


# ---------------------------------------------------------------------------
# the graded network - the membership the lens and the mint BOTH read
# ---------------------------------------------------------------------------

def load_nodes(repo_root: Path | str) -> dict[str, dict[str, Any]]:
    """The graded network (``.self_graded.json``), through ``keeper.load_tree_local``. This is the
    ONE membership source for both the mint and the lens: minting off the meaning tree and serving
    off the graded network would make every row stale on the day it was cut. Verified equal on the
    live corpus - a concept node's graded ``members`` IS its ``parent_map`` child list."""
    from laplace.engine import keeper
    return keeper.load_tree_local(Path(repo_root))


_LENS_HASH_RE = re.compile(rb'"lens_hash"\s*:\s*"([0-9a-fA-F]+)"')


def basis_of(repo_root: Path | str) -> str:
    """The tree's ``lens_hash`` - a digest row's ``basis``. Read from the head of
    ``.meaning_tree.json`` rather than by parsing it: the key sits in the first 200 bytes of a 22 MB
    file and a full parse costs 2.5 s for one 40-character string. Falls back to the full read if
    the head scan misses, so a reordered writer degrades to slow, never to wrong."""
    path = Path(repo_root) / ".meaning_tree.json"
    if not path.is_file():
        return ""
    with path.open("rb") as fh:
        head = fh.read(4096)
    m = _LENS_HASH_RE.search(head)
    if m:
        return m.group(1).decode()
    return str(json.loads(path.read_text(encoding="utf-8")).get("lens_hash") or "")


def leaf_members(nodes: dict[str, dict[str, Any]], nid: str) -> list[str]:
    """The node's CURRENT leaf descendants, sorted - the set ``member_sha`` is taken over.

    Leaf DESCENDANTS rather than direct children because that is the set ``node_id`` was founded on:
    ``meaning_upfold._cluster_id`` hashes the sorted member LEAF ids. Comparing a current leaf set
    against a founding leaf set is the drift the pair exists to expose; comparing direct children
    against leaf ids would compare two different things and call the difference drift."""
    seen: set[str] = set()
    out: set[str] = set()
    stack = [nid]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        node = nodes.get(cur)
        if node is None:
            continue
        if node.get("leaf", True):
            out.add(cur)
            continue
        stack.extend(node.get("members") or [])
    return sorted(out)


def member_sha(members: list[str]) -> str:
    """sha256 over the sorted member ids, joined by NUL - the current-membership half of the key."""
    return hashlib.sha256("\x00".join(sorted(members)).encode("utf-8", "replace")).hexdigest()


def jaccard(a: list[str] | set[str], b: list[str] | set[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    union = sa | sb
    return len(sa & sb) / len(union) if union else 0.0


# ---------------------------------------------------------------------------
# the contrast set - SIBLING clusters, the same idf shape as meaning_upfold._label
# ---------------------------------------------------------------------------

def contrast_docs(nodes: dict[str, dict[str, Any]], nid: str) -> tuple[list[str], str]:
    """``([document ids], why)`` - the node plus its SIBLINGS, which is what makes a term
    distinctive-to-this-cluster rather than merely frequent.

    Each document's term set is its banked ``coverage`` (the union of its subtree's keywords), so
    the contrast costs zero file reads. A node with fewer than two contrast documents (an only
    child) climbs to its grandparent's children, up to ``IDF_CLIMB`` levels; a node that still has
    no contrast falls back to uniform idf and SAYS SO in the row (``idf_basis``), because a claim
    ranked by raw frequency is a different claim and must not read as the same one."""
    cur = nid
    for level in range(IDF_CLIMB):
        parent = (nodes.get(cur) or {}).get("parent")
        # `parent is None` is the ROOT; `parent == ""` is a real node id (the graded network's own
        # root is keyed by the empty string, and `conceptric.load_network` finds the true root by
        # `parent is None`). A falsy test here read every TOP-LEVEL cluster as parentless and sent
        # it to the uniform-idf fallback - measured on the demand union: concept::34d47ff372 and
        # session-handoff-series both minted with `idf_basis=uniform-fallback` while their four
        # siblings sat right there.
        if parent is None or parent not in nodes:
            break
        sibs = [m for m in ((nodes.get(parent) or {}).get("members") or []) if m in nodes]
        if len(sibs) >= 2:
            docs = sorted(set(sibs) | {nid})
            return docs, ("siblings" if level == 0 else f"siblings+{level}")
        cur = parent
    return [nid], "uniform-fallback"


def idf_over(nodes: dict[str, dict[str, Any]], docs: list[str]) -> tuple[dict[str, float], float]:
    """``(idf, default)`` over the contrast documents' coverage - ``log(ndoc / df)``, exactly
    ``meaning_upfold._cluster_residue_body``'s inline idf with the documents being CLUSTERS instead
    of leaves. ``default`` is the value for a term no contrast document carries at all: ``log(ndoc)``
    - maximally distinctive, which is the truth about a token that appears in this node's content
    and in no sibling's coverage."""
    df: Counter = Counter()
    for d in docs:
        cov = (nodes.get(d) or {}).get("coverage") or (nodes.get(d) or {}).get("keywords") or []
        df.update({w for w in cov if _term_ok(w)})
    ndoc = max(1, len(docs))
    default = math.log(ndoc) if ndoc > 1 else 1.0
    return {w: math.log(ndoc / c) for w, c in df.items()}, default


def _tok_weight(tok: str, weight: dict[str, float], default: float) -> float:
    """An object token's weight: the heaviest of its constituent terms. A token is a PHRASE
    (``0.8 jaccard``, ``BibitemOpen``, ``corpus_friction/campaign.jsonl``) and the term that makes it
    load-bearing is the distinctive one, not the average of it with its filler."""
    ws = _terms(tok)
    return max((weight.get(w, default) for w in ws), default=default)


# THE SENTENCE-GRADE WEIGHT, measured rather than assumed (the bake-off run, 2026-08-23).
#
# The first cut was ``meaning_upfold._label``'s math transposed literally: raw node tf times sibling
# idf. On the live corpus it returns BOILERPLATE, because ``_label``'s tf is bounded - it counts
# MEMBERS carrying a keyword, so no term can run away - while a term counted over raw prose is not
# bounded at all. Measured on four real demand nodes: ``concept::b93d52a33b`` claimed
# ``\bibfield {author} {\bibinfo {author} ...`` (``bibfield`` is absent from every sibling's
# coverage, so it took the maximum default idf, and it occurs ~300 times), ``concept::d9a504a15c``
# claimed a line of ``round(b["silhouette"] - a["silhouette"], 6)``.
#
# Three variants were ranked on the same four nodes:
#   A  raw tf x sibling-idf            - the literal transposition. Boilerplate on 3 of 4.
#   B  sibling-idf x node-sentence-idf - drops node tf entirely. Real prose, but mid-document.
#   C  (1 + log tf) x sibling-idf x node-sentence-idf   <- ADOPTED. Won all four by inspection:
#      "**Claim.** Derives equations for inducing a dynamically generated broadband ENZ ...",
#      "Founding charter for the second seat, banked in the tree so nothing founding lives only ...".
#
# Both extra factors are the SAME law one scale down: sublinear tf is the standard damping for a
# term that repeats inside one document, and the node-sentence idf is "distinctive, never merely
# frequent" applied to the node's own sentences instead of its siblings' coverage. The sibling idf
# is untouched - it is still the contrast that makes a term distinctive to THIS cluster.
SCORING = "sublinear-tf x sibling-idf x node-sentence-idf"


def term_weights(tf: Counter, sdf: Counter, n_sents: int,
                 idf: dict[str, float], default_idf: float) -> tuple[dict[str, float], float]:
    """``(weight per term, the weight of an unseen term)`` - the adopted product, computed once per
    node and shared by the sentence ranking and the object ranking so the two agree by construction."""
    n = max(1, n_sents)
    out: dict[str, float] = {}
    for w, c in tf.items():
        idf_node = math.log(n / sdf[w]) if sdf.get(w) else math.log(n)
        out[w] = (1.0 + math.log(c if c > 0 else 1)) * idf.get(w, default_idf) * idf_node
    return out, default_idf * math.log(n)


# ---------------------------------------------------------------------------
# reading the members
# ---------------------------------------------------------------------------

# THE ENGINE'S OWN STORES (cure B2). The engine must not read its own index as corpus: a digest
# whose claim is a line of `.self_graded.json` describes the ENGINE'S BOOKKEEPING about the node,
# not the node - and it is exactly the residue-tree failure one level down, the tree folding its own
# summaries back in. Measured on the first demand union: 4 of 49 nodes read one of these. Named
# explicitly AND covered by the general rule below, so a store added later is excluded by default.
ENGINE_STORES = {".meaning_tree.json", ".self_record_floor.jsonl", ".self_graded.json",
                 ".digests.jsonl", ".closure_meter.jsonl"}

# a member excluded from the CLAIM slot but still lawful as an OBJECT-TOKEN source: a structured
# data file has no prose to claim (7 of 49 claims were bare JSON key fragments) and plenty of
# load-bearing identifiers to harvest.
CLAIM_EXCLUDED_SUFFIXES = {".json", ".jsonl",
                           # the code-fragment bar (the successor judge's grade of CP-A2FIX-1:
                           # three claims shipped ending mid-expression - `strip("[?]` reads as
                           # terminator+bracket to the regex; source code is the barred class in
                           # the claim slot, and suffix is the mechanical line): code still feeds
                           # tf/sdf and object tokens, exactly as structured data does.
                           ".py", ".mjs", ".js", ".ts", ".sh", ".bash", ".zsh", ".ps1",
                           ".c", ".h", ".cpp", ".rs", ".go", ".java", ".css"}


def is_own_store(fid: str) -> bool:
    """Is this member the engine's own store rather than corpus? The named five, plus ANY dotfile
    store at the repo root - which is where this engine keeps them. A dotted DIRECTORY (``.claude/
    settings.json``) is not caught: it is content that happens to live under a dot, and the rule
    here is about the root-level stores the engine writes."""
    return fid in ENGINE_STORES or (fid.startswith(".") and "/" not in fid)


def claim_eligible(fid: str) -> bool:
    """May a sentence from this member become the CLAIM? Structured data may not (see
    ``CLAIM_EXCLUDED_SUFFIXES``); it still contributes object tokens and still counts in the term
    statistics, because what it lacks is prose, not information."""
    return Path(fid).suffix.lower() not in CLAIM_EXCLUDED_SUFFIXES


def member_files(members: list[str]) -> list[str]:
    """Every distinct FILE the members name, deduped, in member order - before any exclusion. The
    unfiltered list exists so ``read_targets``' exclusions can be COUNTED rather than merely done."""
    out: list[str] = []
    seen: set[str] = set()
    for mid in members:
        fid = mid.split("::", 1)[0] if "::" in mid else mid
        if fid and fid not in seen:
            seen.add(fid)
            out.append(fid)
    return out


def read_targets(members: list[str]) -> list[str]:
    """The FILES a node's members live in, deduped, in member order, MINUS the engine's own stores
    (``is_own_store``) - what the mint actually reads.

    THE LENS-CLAIMED MEMBER, measured (the first full demand-union dry run, 2026-08-23: 4 of 49
    nodes minted with no ``src_pointers`` at all, among them
    ``SESSION_HANDOFF_2026-08-23_stage-one-becomes-the-marriage.md``, which is one of the six reds'
    own must_reach targets). A file that a shard lens claims appears in the graded network as an
    INTERNAL node whose members are its ``::`` slices, so a walk to the leaves lands on 15 sub-node
    ids and none of them is a file - the node's whole content read as unreadable and the digest came
    out empty. A ``::`` id names a SLICE OF a file, so it resolves to that file; deduping means a
    file with 15 shards is read once rather than fifteen times (which would multiply its terms by
    fifteen and hand it the claim on frequency alone).

    ``member_sha`` is deliberately NOT taken over this list: the key is the node's true leaf
    membership, and this is the read plan derived from it. Two different things, kept apart."""
    return [fid for fid in member_files(members) if not is_own_store(fid)]


def _readable(repo_root: Path, nodes: dict[str, dict[str, Any]], mid: str) -> Path | None:
    """The on-disk file a member id names, or None when it is not text this mint may read.

    THE SEAL IS CHECKED FIRST AND IS NOT NEGOTIABLE. ``.digests.jsonl`` travels; a sealed node's
    CONTENT never crosses that boundary in any form, so a sealed member contributes no sentence, no
    object token and no pointer. Skips are counted and named in the report - never silent."""
    node = nodes.get(mid) or {}
    if node.get("sealed") or mid.startswith("soul/") or mid.startswith("soul://"):
        return None
    if "::" in mid or "://" in mid:          # a lens-claimed sub-node has no file of its own
        return None
    path = repo_root / mid
    if not path.is_file() or path.suffix.lower() not in TEXT_EXT:
        return None
    return path


def read_member(path: Path) -> str | None:
    """One member's text, capped. A null byte means the extension lied; that member is skipped."""
    try:
        raw = path.read_bytes()[:FILE_CHARS]
    except OSError:
        return None
    if b"\x00" in raw[:4096]:
        return None
    return raw.decode("utf-8", "replace")


# ---------------------------------------------------------------------------
# the mint itself
# ---------------------------------------------------------------------------

def digest_row(repo_root: Path | str, nodes: dict[str, dict[str, Any]], nid: str,
               basis: str, read_cap: int = READ_CAP) -> dict[str, Any]:
    """One claim-grade digest row for ``nid``, extracted from its own members. No model call.

    The claim is the member sentence with the highest sibling-tf*idf mass: for every distinct term
    in the sentence, ``tf(term over this node's read text) * idf(term against the sibling clusters)``,
    divided by the square root of the sentence's distinct-term count so a long sentence cannot win by
    accumulation alone. The object tokens are the regex classes ranked on the same product. Both
    carry ``src_pointers`` - ``[leaf_id, sentence_index]`` into ``sentences(file text)`` - and
    ``method="extracted"``, which is the whole warrant that this row was READ off the corpus rather
    than written about it."""
    repo_root = Path(repo_root)
    members = leaf_members(nodes, nid)
    docs, idf_basis = contrast_docs(nodes, nid)
    idf, default_idf = idf_over(nodes, docs)

    all_files = member_files(members)
    files = read_targets(members)
    read_ids = files[:read_cap]
    skipped = {"sealed": 0, "not_text": 0, "unreadable": 0,
               "own_store": len(all_files) - len(files)}
    texts: dict[str, str] = {}
    for mid in read_ids:
        path = _readable(repo_root, nodes, mid)
        if path is None:
            node = nodes.get(mid) or {}
            key = "sealed" if (node.get("sealed") or "://" in mid
                               or mid.startswith("soul/")) else "not_text"
            skipped[key] += 1
            continue
        text = read_member(path)
        if text is None:
            skipped["unreadable"] += 1
            continue
        texts[mid] = text

    tf: Counter = Counter()
    sdf: Counter = Counter()
    sent_index: dict[str, list[str]] = {}
    n_sents = 0
    for mid, text in texts.items():
        tf.update(_terms(text))
        sent_index[mid] = sentences(text)
        for sent in sent_index[mid]:
            n_sents += 1
            sdf.update(set(_terms(sent)))
    weight, default_w = term_weights(tf, sdf, n_sents, idf, default_idf)

    # --- the claim: the top-weight sentence (SCORING, measured) ------------
    # STRUCTURED DATA IS NOT A CLAIM SOURCE (cure B2): a .json/.jsonl member's "sentences" are key
    # fragments, and 7 of 49 live claims were exactly that. The file still feeds tf/sdf and still
    # supplies object tokens - it is barred from the claim slot only.
    scored: list[tuple[float, str, int, str]] = []
    for mid, sents in sent_index.items():
        if not claim_eligible(mid):
            continue
        for i, sent in enumerate(sents):
            if not claimlike(sent):
                continue
            terms = set(_terms(sent))
            if not terms:
                continue
            mass = sum(weight.get(w, default_w) for w in terms)
            scored.append((mass / math.sqrt(len(terms)), mid, i, sent))
    scored.sort(key=lambda r: (-r[0], r[1], r[2]))

    # --- the objects: the same weight over the regex classes ---------------
    obj_count: Counter = Counter()
    obj_class: dict[str, str] = {}
    obj_where: dict[str, tuple[str, int]] = {}
    for mid, text in texts.items():
        first_line: dict[str, int] = {}
        for i, sent in enumerate(sent_index[mid]):
            for _cls, tok in object_tokens(sent):
                first_line.setdefault(tok, i)
        for cls, tok in object_tokens(text):
            obj_count[tok] += 1
            obj_class.setdefault(tok, cls)
            if tok not in obj_where and tok in first_line:
                obj_where[tok] = (mid, first_line[tok])
    ranked_obj = sorted(
        obj_count,
        key=lambda t: (-((1.0 + math.log(obj_count[t])) * _tok_weight(t, weight, default_w)), t))
    objects = ranked_obj[:N_OBJECTS]

    claim = scored[0][3] if scored else ""
    pointers: list[list[Any]] = [[m, i] for _s, m, i, _t in scored[:N_CLAIM_SENTS]]
    for tok in objects:
        where = obj_where.get(tok)
        if where and [where[0], where[1]] not in pointers:
            pointers.append([where[0], where[1]])
    pointers = pointers[:N_SRC]

    return {
        "schema": SCHEMA,
        "node_id": nid,
        "member_sha": member_sha(members),
        "basis": basis,
        "grade": GRADE,
        "method": METHOD,
        "claim": claim,
        "object_tokens": [{"class": obj_class.get(t, "?"), "token": t, "n": obj_count[t]}
                          for t in objects],
        "src_pointers": pointers,
        "members": members,
        "n_members": len(members),
        "n_files": len(files),
        "n_read": len(texts),
        "read_cap": read_cap,
        # G5, the scarcity law: the contract declares its caps ON the row - the cut is the
        # selection, and a reader sees exactly which walls shaped it.
        "caps": {"read_cap": read_cap, "max_sent": MAX_SENT, "min_sent": MIN_SENT,
                 "n_objects": N_OBJECTS, "n_src": N_SRC, "n_claim_sents": N_CLAIM_SENTS},
        "skipped": skipped,
        "idf_basis": idf_basis,
        "scoring": SCORING,
        "n_contrast_docs": len(docs),
        "n_sentences": n_sents,
        "label": (nodes.get(nid) or {}).get("essence") or "",
        "minted": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def digest_text(row: dict[str, Any]) -> str:
    """The one line a digest IS: the claim, then its load-bearing objects. This is the text the
    meter's member-retrieval arm uses as its query and the text ``digest_lens`` mints referents
    from - one derivation, so the thing measured is the thing wired."""
    toks = " ".join(o["token"] for o in (row.get("object_tokens") or []))
    return " | ".join(p for p in (row.get("claim") or "", toks) if p)


def row_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    """The identity of a banked row: ``(node_id, member_sha, basis, grade)``.

    GRADE IS IN THE KEY NOW, BEFORE A SECOND GRADE EXISTS (cure B6). ``claim`` is the only value
    today, and that is exactly why this is the moment to add it: without ``grade`` the key says
    "this node, this membership, this lens has a digest", so the first mechanism-grade mint of an
    unchanged node reports ``already`` and banks nothing - measured, and it would have blocked the
    tower's next storey silently. The tower deepens per grade; the key has to be able to say so."""
    return (row.get("node_id", ""), row.get("member_sha", ""),
            row.get("basis", ""), row.get("grade", ""))


def load_rows(repo_root: Path | str) -> list[dict[str, Any]]:
    """Every banked digest row. A malformed line is skipped and counted by the caller, never fatal -
    this store is append-only and a half-written tail must not blind the lens to the rows above it."""
    path = Path(repo_root) / DIGEST_STORE
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def _defective(row: dict[str, Any]) -> str | None:
    """The design's own DEFECT test, applied at the write boundary: ``method="composed"`` with no
    ``src_pointers`` is a defect, and so is an empty pointer list under a method claiming extraction.
    A defect is a contract violation and never banks - it is not the same thing as a refusal."""
    if row.get("method") != METHOD:
        return f"method={row.get('method')!r} - only {METHOD!r} is minted on this path"
    if row.get("n_read") and not row.get("src_pointers"):
        return "read members but banked no src_pointers - the extraction did not produce its warrant"
    # THE HOLE THIS CLOSES (cure B4): a latex-only member banked claim="" with valid pointers and
    # passed. A row whose method says EXTRACTED and whose claim is empty extracted nothing; the
    # pointers point at objects, and objects without a claim are a keyword list wearing a digest's
    # clothes. Not a refusal (the node HAD readable members) - a defect.
    if not str(row.get("claim") or "").strip():
        return "extracted no claim - the members yielded no sentence that ends where a claim ends"
    return None


_FORBIDDEN_KEYS = ("thesis", "synthesis", "theory")


def _anchor_defect(repo_root: Path, nodes: dict[str, dict[str, Any]],
                   row: dict[str, Any]) -> str | None:
    """G2, the quote-anchor gate (genesis's ``check_residue`` discipline, transposed): every
    extracted claim substring-matches its source RAW - whitespace-normalized, read straight off
    the file, never re-derived through the splitter that produced it (the circular-warrant
    defect the verify wave named). An unresolvable source is a GATE FAILURE, never a silent
    skip - 'an empty source would make every quote check vacuous' is genesis's own sentence.
    And extraction EXTRACTS: the composed arm's keys are forbidden on an extracted row."""
    for k in _FORBIDDEN_KEYS:
        if row.get(k):
            return f"forbidden key {k!r} on an extracted row - composition is the separate gated arm"
    claim = str(row.get("claim") or "").strip()
    ptrs = row.get("src_pointers") or []
    if not claim or not ptrs:
        return None  # the empty-claim / no-pointer defects carry their own names in _defective
    mid = str(ptrs[0][0])
    path = _readable(Path(repo_root), nodes, mid)
    if path is None:
        return f"quote anchor unresolvable: {mid} not readable - a vacuous check is a gate failure"
    text = read_member(path)
    if text is None:
        return f"quote anchor unresolvable: {mid} unreadable - a vacuous check is a gate failure"
    if " ".join(claim.split()) not in " ".join(text.split()):
        return ("quote anchor FAILED: the claim is not a whitespace-normalized substring of "
                f"{mid} - extraction must quote, never paraphrase")
    return None


def _refused(row: dict[str, Any]) -> str | None:
    """A REFUSAL, which is not a defect: the node has nothing this mint may read, so there is no
    claim to extract and composing one would be the defect. Measured on the demand union: two
    clusters (``concept::8e85e079e2``, ``concept::09d118383c``) are entirely ``published_corpus/pdfs``
    binaries, and a third class is entirely sealed. Named and reported, never banked, never guessed -
    extracting text from a pdf would need a dependency this organ does not have and must not add."""
    if row.get("n_read"):
        return None
    sk = row.get("skipped") or {}
    parts = [f"{k}={v}" for k, v in sorted(sk.items()) if v]
    return (f"no readable member: {row.get('n_files', 0)} file(s), " + ", ".join(parts)
            if parts else "no readable member")


def mint(repo_root: Path | str, node_ids: list[str], dry_run: bool = True,
         read_cap: int = READ_CAP,
         nodes: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Mint claim-grade digests for ``node_ids``. IDEMPOTENT: a row whose ``(node_id, member_sha,
    basis, grade)`` is already banked is not re-minted and not re-appended.

    ``dry_run`` (the default) does the whole extraction and reports it without touching the store -
    the only difference between the two modes is the append, so a dry run is a real measurement of
    the rows a run would bank, not a plan for them."""
    repo_root = Path(repo_root)
    t0 = time.perf_counter()
    nodes = load_nodes(repo_root) if nodes is None else nodes
    basis = basis_of(repo_root)
    existing = {row_key(r) for r in load_rows(repo_root)}

    minted: list[dict[str, Any]] = []
    already: list[str] = []
    defects: list[dict[str, str]] = []
    refusals: list[dict[str, str]] = []
    unknown: list[str] = []
    n_read = 0
    for nid in node_ids:
        if nid not in nodes:
            unknown.append(nid)
            continue
        row = digest_row(repo_root, nodes, nid, basis, read_cap=read_cap)
        n_read += row["n_read"]
        if row_key(row) in existing:
            already.append(nid)
            continue
        why = _refused(row)
        if why:
            refusals.append({"node_id": nid, "why": why})
            continue
        why = _defective(row) or _anchor_defect(repo_root, nodes, row)
        if why:
            defects.append({"node_id": nid, "why": why})
            continue
        minted.append(row)
        existing.add(row_key(row))

    written = 0
    if not dry_run and minted:
        path = repo_root / DIGEST_STORE
        with path.open("a", encoding="utf-8") as fh:
            for row in minted:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        written = len(minted)

    elapsed = time.perf_counter() - t0
    return {
        "mode": "dry-run" if dry_run else "run",
        "basis": basis,
        "asked": len(node_ids),
        "minted": len(minted),
        "written": written,
        "already_banked": already,
        "unknown_nodes": unknown,
        "refusals": refusals,
        "defects": defects,
        "rows": minted,
        "cost": _cost("mint", {"nodes": len(node_ids), "member_files_read": n_read},
                      elapsed, unit="nodes",
                      why=f"{len(node_ids)} demanded node(s), read_cap={read_cap}"),
    }


# ---------------------------------------------------------------------------
# the demand set - which nodes the six reds actually need digested
# ---------------------------------------------------------------------------

PROBES_FILE = "holdout/THREAD_PROBES.json"
RED_PROBES = [
    "thread-dmrg-hierarchicalisation",
    "thread-orthogonality-catastrophe",
    "thread-closure-residual",
    "thread-2026-08-23-the-accounting-day",
    "thread-2026-08-23-the-two-seat-form",
    "thread-2026-08-23-the-campaign-rows",
]


def load_probes(repo_root: Path | str, probe_ids: list[str] | None = None) -> list[dict[str, Any]]:
    path = Path(repo_root) / PROBES_FILE
    data = json.loads(path.read_text(encoding="utf-8"))
    probes = {p["id"]: p for p in data.get("probes", [])}
    want = probe_ids if probe_ids is not None else RED_PROBES
    missing = [p for p in want if p not in probes]
    if missing:
        raise KeyError(f"probe id(s) absent from {PROBES_FILE}: {missing}")
    return [probes[p] for p in want]


def _is_root(nodes: dict[str, dict[str, Any]], nid: str) -> bool:
    """The network's single root - the node with ``parent is None``. It is dropped from every demand
    arm: a descent does not CHOOSE the root, it starts there, so a digest on it decides nothing, and
    its "claim" would be one sentence read from 52 of 18,988 leaves - a summary of the whole engine,
    which is the flatten reflex wearing a digest's clothes."""
    return (nodes.get(nid) or {}).get("parent") is None


def _matches(nodes: dict[str, dict[str, Any]], target: str) -> list[str]:
    """Every network node a ``must_reach`` target names. Exact id first; failing that, the target as
    a DIRECTORY or lens prefix (``paper_operatorial_loss`` names 225 leaves, not one). Substring
    matching is deliberately NOT done - it would silently widen a probe's owed path."""
    if target in nodes:
        return [target]
    return sorted(n for n in nodes if n.startswith(target + "/") or n.startswith(target + "::"))


def _ancestors(nodes: dict[str, dict[str, Any]], nid: str) -> list[str]:
    """The node's ancestor chain, nearest first, from the graded network's own parentage.

    The graded network rather than ``.meaning_tree.json``'s ``parent_map`` on purpose: a target may
    be LENS-CLAIMED and therefore absent from the residue tree entirely (measured -
    ``SESSION_HANDOFF_2026-08-23_stage-one-becomes-the-marriage.md`` is one of the six reds' targets
    and is not a tree leaf at all, because its ``::`` shards claim it). Its owed path is real and
    the tree cannot name it; the network can, and the digest lens joins the network."""
    chain: list[str] = []
    cur = nid
    seen = {nid}
    while True:
        parent = (nodes.get(cur) or {}).get("parent")
        if parent is None or parent in seen or parent not in nodes:
            break   # `parent is None` is the root; `""` is a real node id - see contrast_docs
        chain.append(parent)
        seen.add(parent)
        cur = parent
    return chain


def demand_set(repo_root: Path | str, probe_ids: list[str] | None = None,
               beam: int = 4, nodes: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """The ordered node ids the red probes demand a digest of, per probe and as a union.

    Two arms, both named in the row:

      * CURRENT PATH - where the descent actually goes today. ``recursive_read.descend(query,
        beam=4)`` and the union of every hit's ``path`` (the cluster chain from the hit's own parent
        up to the root). These are the handles that WON, and a digest on them is what would make the
        next descent's choice a content choice.
      * OWED PATH - where it must go. For every node matching a ``must_reach`` target: the node
        itself plus its ancestor chain. These are the handles that LOST, and a digest on them is
        what would let them win.

    One ``Descender`` is opened for the whole set (the open is a 2.6 s tree parse plus the model
    load; the descents are ~0.3 s each), so the cost of asking six probes is one open, not six.

    NOTHING IS BANKED ACROSS THE DESCENTS. The env-var save/set/restore dance that used to hold
    the closure meter off here was a partial cure (it missed ``scripts/wire_distillates.py:73`` and
    the benches that pass no label at all). The bank seam itself is gone from
    ``recursive_read.descend``, so a probe cannot feed the residual ledger from any caller."""
    repo_root = Path(repo_root)
    t0 = time.perf_counter()
    nodes = load_nodes(repo_root) if nodes is None else nodes
    probes = load_probes(repo_root, probe_ids)

    from laplace.engine import recursive_read
    t_open = time.perf_counter()
    dsc = recursive_read.open_descender(repo_root)
    open_s = time.perf_counter() - t_open

    per_probe, union, descent_s = _descend_demand(dsc, nodes, probes, beam)

    elapsed = time.perf_counter() - t0
    return {
        "schema": "digest-demand/0.1",
        "beam": beam,
        "backend": dsc.backend.name,
        "basis": basis_of(repo_root),
        "per_probe": per_probe,
        "union": union,
        "n_union": len(union),
        "cost": _cost("demand", {"probes": len(probes), "descents": len(probes),
                                 "nodes_in_network": len(nodes)},
                      elapsed, unit="descents",
                      why=f"{len(probes)} red probe(s) x 1 descent at beam={beam}",
                      extra={"open_seconds": round(open_s, 3),
                             "descent_seconds": round(descent_s, 3)}),
    }


def _descend_demand(dsc: Any, nodes: dict[str, dict[str, Any]], probes: list[dict[str, Any]],
                    beam: int) -> tuple[list[dict[str, Any]], list[str], float]:
    """``(per-probe rows, the ordered union, seconds spent descending)`` - the body of
    ``demand_set``, lifted out so the closure-meter switch has one obvious scope and cannot leak
    past a raise."""
    per_probe: list[dict[str, Any]] = []
    union: list[str] = []
    seen: set[str] = set()
    descent_s = 0.0
    for probe in probes:
        t1 = time.perf_counter()
        packet = dsc.descend(probe["query"], k=int(probe.get("top_k", 5)), beam=beam,
                             fire="dutiful")
        descent_s += time.perf_counter() - t1
        current: list[str] = []
        for hit in packet["hits"]:
            for cid in hit["path"]:
                if cid and cid in nodes and not _is_root(nodes, cid) and cid not in current:
                    current.append(cid)
        owed: list[str] = []
        targets: list[dict[str, Any]] = []
        for target in probe.get("must_reach", []):
            matched = _matches(nodes, target)
            chain: list[str] = []
            for mid in matched:
                for cand in [mid, *_ancestors(nodes, mid)]:
                    if cand not in chain and not _is_root(nodes, cand):
                        chain.append(cand)
            # ``kind`` is the lens-claimed tell: a target that matched EXACTLY but is INTERNAL in
            # the graded network carries ``::`` shard children, which means a lens claims it and
            # the residue meaning tree cannot hold it - so no descent can ever HIT it and its owed
            # path is a network chain, not a tree chain. Named per target rather than assumed.
            first = nodes.get(matched[0]) if matched else None
            targets.append({"target": target, "n_matched": len(matched),
                            "exact_id_match": bool(matched) and matched[0] == target,
                            "kind": ("leaf" if (first or {}).get("leaf", True) else "internal")
                                    if first else "none",
                            "n_owed": len(chain)})
            for cand in chain:
                if cand not in owed:
                    owed.append(cand)
        ordered = current + [n for n in owed if n not in current]
        for nid in ordered:
            if nid not in seen:
                seen.add(nid)
                union.append(nid)
        per_probe.append({
            "probe": probe["id"],
            "query": probe["query"],
            "expected_now": probe.get("expected_now"),
            "n_current_path": len(current),
            "n_owed_path": len(owed),
            "n_demand": len(ordered),
            "current_path": current,
            "owed_path": owed,
            "targets": targets,
            "hits": [h["id"] for h in packet["hits"]],
        })
    return per_probe, union, descent_s


# ---------------------------------------------------------------------------
# the cost law - M-minutes-are-guilty-until-arithmetic
# ---------------------------------------------------------------------------

def _device() -> str:
    return (f"cpu x{os.cpu_count()} ({sys.platform}, system python3 "
            f"{sys.version_info.major}.{sys.version_info.minor})")


def _cost(what: str, volume: dict[str, int], seconds: float, why: str, unit: str,
          extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """VOLUME x RATE, with the device named. Every entry point returns one of these; a run that
    cannot say what n it paid for has not been measured, only performed. ``unit`` is named by the
    caller rather than inferred from the largest count - the rate that means something is per
    descent or per node, never per node-in-the-network-that-was-merely-loaded."""
    n = max(1, volume.get(unit, 1))
    row = {"what": what, "volume": volume, "why_that_n": why,
           "seconds": round(seconds, 3),
           "ms_per_unit": round(1000.0 * seconds / n, 2),
           "unit": unit,
           "device": _device()}
    if extra:
        row.update(extra)
    return row


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python3 -m laplace.engine.digest_mint",
        description="the digest mint - claim-grade node digests, extracted, never composed")
    ap.add_argument("--demand", metavar="WHICH", nargs="?", const="reds",
                    help="report the demand set. WHICH=reds (default) or a comma-separated probe id list")
    ap.add_argument("--mint", metavar="IDS",
                    help="mint digests for a comma-separated node id list, or the word 'demand' "
                         "to mint the red probes' demand union")
    ap.add_argument("--dry-run", action="store_true", default=None,
                    help="extract and report without writing (the default for --mint)")
    ap.add_argument("--run", dest="dry_run", action="store_false",
                    help="write the minted rows to .digests.jsonl")
    ap.add_argument("--limit", type=int, default=0, help="mint at most N nodes (0 = no limit)")
    ap.add_argument("--read-cap", type=int, default=READ_CAP)
    ap.add_argument("--beam", type=int, default=4)
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--json", action="store_true", help="emit the whole report as JSON")
    args = ap.parse_args(argv)

    root = Path(args.repo_root).resolve()
    if not args.demand and not args.mint:
        ap.error("nothing asked: pass --demand or --mint")

    out: dict[str, Any] = {}
    if args.demand:
        ids = None if args.demand == "reds" else [s for s in args.demand.split(",") if s]
        out["demand"] = demand_set(root, ids, beam=args.beam)

    if args.mint:
        if args.mint == "demand":
            report = out.get("demand") or demand_set(root, None, beam=args.beam)
            out.setdefault("demand", report)
            node_ids = report["union"]
        else:
            node_ids = [s for s in args.mint.split(",") if s]
        if args.limit:
            node_ids = node_ids[:args.limit]
        out["mint"] = mint(root, node_ids,
                           dry_run=True if args.dry_run is None else args.dry_run,
                           read_cap=args.read_cap)

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0

    if "demand" in out:
        d = out["demand"]
        print(f"demand set (beam={d['beam']}, backend={d['backend']}, basis={d['basis'][:12]})")
        for p in d["per_probe"]:
            print(f"  {p['probe']:<44} demand={p['n_demand']:<4} "
                  f"current={p['n_current_path']:<4} owed={p['n_owed_path']}")
            for t in p["targets"]:
                print(f"      target {t['target']!r}: matched={t['n_matched']} "
                      f"exact={t['exact_id_match']} kind={t['kind']} owed={t['n_owed']}")
        print(f"  UNION {d['n_union']} node(s)")
        c = d["cost"]
        print(f"  cost: {c['volume']} in {c['seconds']}s "
              f"({c['ms_per_unit']} ms/{c['unit']}, open={c.get('open_seconds')}s, "
              f"descents={c.get('descent_seconds')}s) on {c['device']}")

    if "mint" in out:
        m = out["mint"]
        print(f"mint [{m['mode']}] asked={m['asked']} minted={m['minted']} written={m['written']} "
              f"already={len(m['already_banked'])} refused={len(m['refusals'])} "
              f"defects={len(m['defects'])} unknown={len(m['unknown_nodes'])}")
        for row in m["rows"]:
            print(f"  {row['node_id']}  members={row['n_members']} read={row['n_read']} "
                  f"idf={row['idf_basis']}/{row['n_contrast_docs']} ptrs={len(row['src_pointers'])}")
            print(f"      label : {row['label'][:100]}")
            print(f"      claim : {row['claim'][:160]}")
            print(f"      objects: {', '.join(o['token'] for o in row['object_tokens'][:8])}")
        for r_ in m["refusals"]:
            print(f"  REFUSED {r_['node_id']}: {r_['why']}")
        for d_ in m["defects"]:
            print(f"  DEFECT {d_['node_id']}: {d_['why']}")
        c = m["cost"]
        print(f"  cost: {c['volume']} in {c['seconds']}s ({c['ms_per_unit']} ms/{c['unit']}) "
              f"on {c['device']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
