#!/usr/bin/env python
"""Compile the `synthetics-definition` conceptric DECLARATION from the banked root documents.

WHAT THIS IS. The definition of synthetics — the object, not the campaign that produced it —
poured through the encoded-doors path (ruling R3, `evidence/SYNTHETICS_DEFINITION_2026-08-13
_derived-rulings.md`). This script is the ONE PRODUCER of four derived artefacts:

    synthetics papers/synthetics-definition/conceptric_overlay.json   the declaration
    synthetics papers/synthetics-definition/prices.jsonl              the price-pair sidecar (R6)
    synthetics papers/synthetics-definition/STATE.json                the run-state surface
    synthetics papers/synthetics-definition/manuscript/main.tex       the resolve_corpus stub

Nothing here is hand-maintained: re-run the script and the artefacts are rebuilt. The ledger
(`corpus_friction/synthetics-definition.jsonl`) is the NEXT producer's — run
`scripts/build_overlay_conceptric.py --project synthetics-definition` after this one.

WHAT IS DERIVED vs WHAT IS AUTHORED. Every source REFERENCE, every epistemic status, and
every census number below is DERIVED at compile time by locating a named anchor inside a
banked root document; an anchor that is missing, or that matches more than one line, is a
hard failure, so a moved source can never silently produce a graph whose refs point at the
wrong prose. What gets STORED is a CONTENT anchor (`<path>:@<digest>[+<n>]`,
`laplace.manuscript.source_anchor`), never the located offset: the line number is derived at read time
(`python3 -m laplace.manuscript.source_anchor <ref>`). That distinction is the whole point — an offset
is a property of the file, so inserting one line into a root document rewrote every ref
below it and turned an unrelated edit into a byte-stability failure (twice on 2026-08-20:
at `ef4b6f2f`, and again on a W7 insertion into OPEN_STACK.md). An anchor is a property of
the anchored text, so these artefacts now change when the prose they point at changes and at
no other time. The node ESSENCES are authored short descriptions written for
this graph — THE_STORY's prose is his and stays in its own file (the graph points at it, it
does not copy it). That claim is MEASURED, not asserted: `check_no_story_prose` refuses to
emit any essence carrying a verbatim run of `MAX_VERBATIM_RUN` words or more from THE_STORY,
so an essence assembled out of his sentences fails the compile instead of shipping. The first
build of this project shipped without that gate and leaked — nine essences were elisions of
single Story paragraphs, the worst 78% verbatim — which is why the gate exists and why the
door test re-measures the same property on the emitted declaration.

ROOT DOCUMENTS (all under `synthetics papers/synthetics-genesis/`, plus three repo-level ones):
    THE_STORY_OF_SYNTHETICS.md    the seven-part reading order, the §3 tier words
    projection/claims.json        the 13 grade-1 claims and their five-value statuses
    projection/anchors.json       the anchor census the external-anchor residue is computed from
    genesis/genesis.jsonl         the 22 genesis rows
    corpus/cards/*.md             the 12 fragment cards' front matter
    OPEN_STACK.md                 the N37 open port
    DESIGN_2026-08-01_the-atlas.md + evidence/ATLAS_PHASE3_…  the atlas touchpoint's carriers
    evidence/SYNTHETICS_DEFINITION_2026-08-13_derived-rulings.md   the campaign rulings

DETERMINISM. No model calls, no wall-clock, no randomness: the record stamp is the fixed
`TS` below, the node order is the order of the spec table, and the JSON is written with a
fixed encoder. Two runs on the same tree produce byte-identical files.

    python3 scripts/compile_synthetics_definition_overlay.py
    python3 scripts/compile_synthetics_definition_overlay.py --check    # byte-stability probe
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:                                            # the ref grammar is engine-level, not ours
    from laplace.manuscript import source_anchor
except ImportError:                             # run from a tree where src/ is not on the path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from laplace.manuscript import source_anchor

PROJECT = "synthetics-definition"
PROJECT_DIR = f"synthetics papers/{PROJECT}"
PRODUCER = "scripts/compile_synthetics_definition_overlay.py"

#: the FIXED record stamp — the declaration is a derived artefact, not an event log, so it
#: carries the campaign date rather than the clock (byte-stability, one-producer law).
TS = "2026-08-13T00:00:00"

GENESIS = "synthetics papers/synthetics-genesis"
STORY = f"{GENESIS}/THE_STORY_OF_SYNTHETICS.md"
CLAIMS = f"{GENESIS}/projection/claims.json"
ANCHORS = f"{GENESIS}/projection/anchors.json"
GENESIS_LEDGER = f"{GENESIS}/genesis/genesis.jsonl"
CARDS = f"{GENESIS}/corpus/cards"
RULINGS = "evidence/SYNTHETICS_DEFINITION_2026-08-13_derived-rulings.md"
ATLAS_DESIGN = "DESIGN_2026-08-01_the-atlas.md"
ATLAS_PHASE3 = "evidence/ATLAS_PHASE3_2026-08-01_stop-condition.md"
OPEN_STACK = "OPEN_STACK.md"


class CompileError(Exception):
    """A source the compiler cannot locate — named and refused, never guessed around."""


# ---------------------------------------------------------------------------
# the source readers — every one of them a LOCATOR, so a ref is measured, not typed
# ---------------------------------------------------------------------------

class Sources:
    """The banked root documents, read once, with the anchor locators the spec calls."""

    def __init__(self, repo: Path) -> None:
        self.repo = repo
        self._lines: dict[str, list[str]] = {}

    def lines(self, rel: str) -> list[str]:
        if rel not in self._lines:
            p = self.repo / rel
            if not p.is_file():
                raise CompileError(f"root document missing: {rel}")
            self._lines[rel] = p.read_text(encoding="utf-8").splitlines()
        return self._lines[rel]

    def line_of(self, rel: str, needle: str) -> int:
        """The 1-indexed line carrying ``needle`` — EXACTLY one, or a hard failure."""
        hits = [i for i, ln in enumerate(self.lines(rel), 1) if needle in ln]
        if not hits:
            raise CompileError(f"anchor not found in {rel}: {needle!r}")
        if len(hits) > 1:
            raise CompileError(f"anchor ambiguous in {rel} (lines {hits}): {needle!r}")
        return hits[0]

    # -- what gets STORED: the content, never the offset --------------------
    def ref_at(self, rel: str, start: int, end: int | None = None) -> str:
        """The ref for a span this compiler has already LOCATED, keyed on the span's own
        text. The located line number does its work and is then thrown away: it is a
        property of the file (any insertion above moves it), while the anchor is a property
        of the prose the node actually points at."""
        try:
            return f"{rel}:{source_anchor.anchor(self.lines(rel), start, end)}"
        except source_anchor.AnchorError as e:
            raise CompileError(f"{rel}: {e}") from None

    def ref_of(self, rel: str, needle: str) -> str:
        """Locate ``needle`` (the hard floor: exactly one hit) and store its CONTENT."""
        return self.ref_at(rel, self.line_of(rel, needle))

    # -- THE_STORY -------------------------------------------------------
    def story_parts(self) -> list[dict]:
        """The seven parts in THE_STORY's OWN order (ruling R4) — the declared arc."""
        out = []
        for i, ln in enumerate(self.lines(STORY), 1):
            m = re.match(r"^## (\d)\. (.+)$", ln)
            if m:
                out.append({"n": int(m.group(1)), "title": m.group(2).strip(), "line": i})
        if [p["n"] for p in out] != [1, 2, 3, 4, 5, 6, 7]:
            raise CompileError(f"THE_STORY's part order moved: {[p['n'] for p in out]}")
        return out

    def story_findings(self) -> list[dict]:
        """§3's graded findings, in the order the section states them, each with the tier
        word the section itself puts in front of it (solid / suggestive / one-data-point /
        withdrawn). The three withdrawn ones are findings like any other (ruling R6)."""
        tiers = {"Solid": "solid", "Suggestive": "suggestive",
                 "One data point": "one-data-point", "Withdrawn": "withdrawn"}
        out = []
        for i, ln in enumerate(self.lines(STORY), 1):
            m = re.match(r"^\*\*(Solid|Suggestive|One data point|Withdrawn): (.*)$", ln)
            if m:
                out.append({"tier": tiers[m.group(1)], "line": i})
        if len(out) != 13:
            raise CompileError(f"§3 graded findings: expected 13, found {len(out)}")
        return out

    # -- claims.json -----------------------------------------------------
    def claims(self) -> dict[str, dict]:
        """``{C1: {status, line}}`` — the status is read from the parsed JSON, the line
        from the raw text, so the ref points at the claim a reader can open."""
        raw = self.lines(CLAIMS)
        doc = json.loads((self.repo / CLAIMS).read_text(encoding="utf-8"))
        out: dict[str, dict] = {}
        for c in doc["claims"]:
            cid = c["id"]
            line = self.line_of(CLAIMS, f'"id": "{cid}",')
            end = line
            for j in range(line, min(line + 8, len(raw)) + 1):
                if re.match(r'^\s*"status":', raw[j - 1]):
                    end = j
                    break
            out[cid] = {"status": c["status"], "line": line, "end": end}
        if len(out) != 13:
            raise CompileError(f"claims.json: expected 13 claims, found {len(out)}")
        return out

    # -- genesis.jsonl ---------------------------------------------------
    def genesis(self) -> dict[str, int]:
        out = {}
        for i, ln in enumerate(self.lines(GENESIS_LEDGER), 1):
            if ln.strip():
                out[json.loads(ln)["g_id"]] = i
        return out

    # -- the fragment cards ----------------------------------------------
    def cards(self) -> list[dict]:
        """The 12 fragment cards' front matter: id, class, fit, and the front-matter span
        (line 1 to the ``fit:`` line) that a card node refs."""
        out = []
        for p in sorted((self.repo / CARDS).glob("*.md")):
            rel = f"{CARDS}/{p.name}"
            fm: dict[str, Any] = {"rel": rel}
            for i, ln in enumerate(self.lines(rel), 1):
                m = re.match(r"^(id|class|fit):\s*(.+)$", ln)
                if m and m.group(1) not in fm:
                    fm[m.group(1)] = m.group(2).strip()
                    fm[m.group(1) + "_line"] = i
            for key in ("id", "class", "fit"):
                if key not in fm:
                    raise CompileError(f"card {rel} has no `{key}:` front-matter line")
            out.append(fm)
        if not out:
            raise CompileError(f"no fragment cards under {CARDS}")
        return out

    # -- anchors.json ----------------------------------------------------
    def anchor_census(self) -> dict[str, int]:
        """The residue/claim anchor split by root — what the external-anchor residue node
        states, computed here rather than quoted, so the counts cannot drift (ruling R5)."""
        doc = json.loads((self.repo / ANCHORS).read_text(encoding="utf-8"))
        res = doc["residue_anchors"]
        claim_ev = [e for c in doc["claims"] for e in c.get("evidence", [])]
        foreign_res = sum(1 for a in res if a.get("root") == "corpus")
        foreign_claim = sum(1 for e in claim_ev if e.get("root") == "corpus")
        return {
            "residue_total": len(res),
            "residue_foreign": foreign_res,
            "claim_total": len(claim_ev),
            "claim_foreign": foreign_claim,
            "local_total": (len(res) - foreign_res) + (len(claim_ev) - foreign_claim),
            "corpus_root": doc["corpus_root"],
        }


# ---------------------------------------------------------------------------
# the ref locators used by the spec table
# ---------------------------------------------------------------------------

def resolve_ref(src: Sources, spec: tuple, ctx: dict) -> str:
    """Every branch LOCATES first and then hands the located span to ``ref_at``, so the
    emitted ref names content. A locator that cannot find its target still hard-fails."""
    kind = spec[0]
    if kind == "story":
        return src.ref_of(STORY, spec[1])
    if kind == "story-part":
        part = ctx["parts"][spec[1] - 1]
        return src.ref_at(STORY, part["line"])
    if kind == "story-finding":
        return src.ref_at(STORY, ctx["findings"][spec[1]]["line"])
    if kind == "claim":
        c = ctx["claims"][spec[1]]
        return src.ref_at(CLAIMS, c["line"], c["end"])
    if kind == "genesis":
        return src.ref_at(GENESIS_LEDGER, ctx["genesis"][spec[1]])
    if kind == "card":
        card = next(c for c in ctx["cards"] if c["id"] == spec[1])
        return src.ref_at(card["rel"], 1, card["fit_line"])
    if kind == "file":
        return src.ref_of(spec[1], spec[2])
    raise CompileError(f"unknown ref locator {kind!r}")


# ---------------------------------------------------------------------------
# THE GRAPH SPEC. Node order here is the emission order (and so the OV-NNNN order).
# `p` = parent, `k` = native kind, `t` = term, `e` = authored essence, `r` = ref locator.
# ---------------------------------------------------------------------------

GOAL_ID = "goal:synthetics-definition"

GOAL_ESSENCE = (
    "THE DEFINITION, short form: synthetics is the programme claiming that a law is not handed to "
    "a finite description from outside — the description SYNTHESISES one. As the corpus actually "
    "stands, it is two rigorous halves welded by an aspiration rather than by mathematics. The "
    "relational half (records that will not merge) and the variational half (descriptions priced "
    "by rank) are each real, and each defeats its strongest rival; the bridge between them is "
    "half-built and terminates at a single missing equation — the exchange rate beta/lambda "
    "relating the counting currency to the authority currency. Wording rides ruling R4 and awaits "
    "his redline; the ledger corrects retrospectively."
)

# native kind -> a corpus_ingest.LOGICAL_KINDS member. The natives are this project's own
# words and are deliberately disjoint from LOGICAL_KINDS (widening that tuple would move
# every project's gap counts). Kinds are REAL, not a blanket `support`: PROVENANCE_EXEMPT
# must not swallow the graph, so findings are `result` and the provenance instruments have
# something to check (ruling R7).
KIND_MAP = {
    "programme-goal": "goal",
    "object": "definition",
    "principle": "postulate",
    "open-problem": "definition",
    "open-port": "definition",
    "finding": "result",
    "residue": "result",
    "derived-theorem": "theorem",
    "method": "technique",
    "experiment-spec": "technique",
    "portal-ref": "portal",
    "literature": "citation",
}

REL_MAP = {
    "in-part": "contains",              # the structural wire: a member names its container
    "draws-from": "derives",            # a coarse node describes itself by the level below
    "derives-from": "derives",
    "rests-on-literature": "derives",   # the outgoing hop the substrate gate walks
    "bears-claim": "supports",          # the token lives ON the literature node (schema.AXES)
    "evidenced-by": "validates",        # a result names the banked carrier that bears it
}

# the seven beat containers, in THE_STORY's own part order (ruling R4)
BEATS = [
    ("def:the-ten-papers", "the ten papers, given back"),
    ("technique:the-reconstruction-method", "how the corpus was read"),
    ("res:the-graded-findings", "what was found, by tier"),
    ("def:two-halves-and-the-fused-word", "two bodies of work, one overloaded word"),
    ("def:the-join", "the mathematics, half-built"),
    ("res:the-price-law-fell", "the headline that died twice"),
    ("def:the-forward-programme", "what is owed next"),
]

BEAT_NARRATIVE = {
    "def:the-ten-papers":
        "the corpus first: ten paper-projects, each carrying a real result and a real hole, "
        "because the pattern across the holes is what everything after is about",
    "technique:the-reconstruction-method":
        "then the instrument: blind readers, quote-anchored digests, rivals with teeth and "
        "pre-registered tests — so a pattern that comes back is the corpus's, not a briefing's",
    "res:the-graded-findings":
        "then the findings, each carrying the tier word that limits it, the withdrawals "
        "standing in the same list as the wins",
    "def:two-halves-and-the-fused-word":
        "the discovery that reorganised the rest: two remainder-objects of different type, "
        "fused under one word at a dated site, and every later cost traced to that fusion",
    "def:the-join":
        "the mathematics he supplied in a night, typed into obligations: five closed, two "
        "failed usefully, every route stopping at the same missing equation",
    "res:the-price-law-fell":
        "the reversal that buys the rest its credibility — the project's best headline "
        "killed twice by its own instruments, reported in full",
    "def:the-forward-programme":
        "and what the definition owes: the one equation, the conservation test, the free-move "
        "hunt, the stranded theorem, the un-fusing of the word",
}

# --- the node table ---------------------------------------------------------
# Each row: (id, native kind, parent, term, authored essence, ref locator, projection extras)
NODES: list[tuple] = [

    # ---- part 1: what you wrote --------------------------------------------
    ("def:the-ten-papers", "object", GOAL_ID, "the ten papers",
     "THE CORPUS the definition is a definition OF: ten physics paper-projects written "
     "April-June 2026, each read from inside its full revision history so its real result and "
     "its real hole are both on the record. The fragment cards are the per-paper carriers.",
     ("story-part", 1), {}),

    ("def:the-prompt-as-fragment", "object", "def:the-ten-papers", "the prompt as a fragment",
     "The reconstruction's own prompt entered the corpus as fragment P0 — an object of the "
     "reconstruction, not only its instructions. This is why the definition can be reflexive "
     "without being circular: the instrument is inside the census it reports.",
     ("card", "P0"), {}),

    ("portal:genesis-evidence-cards", "portal-ref", "def:the-ten-papers", "the fragment cards",
     "PORTAL into synthetics-genesis: the per-fragment evidence cards (role, fit, "
     "instantiated primitives, quote-anchored resistance). The substance lives there; this "
     "graph points at it and never copies it.",
     ("card", "cost-of-complexity"), {}),

    # ---- part 2: what the reconstruction did --------------------------------
    ("technique:the-reconstruction-method", "method", GOAL_ID, "the reconstruction method",
     "THE INSTRUMENT: twelve documents, read blind by isolated readers under a single hard rule — "
     "no assertion about a text without a verbatim quotation and its location — then an "
     "architecture built to be attacked by rivals over five loops, halted at provisionally "
     "complete rather than at any claimed fixed point.",
     ("story-part", 2), {}),

    ("technique:pre-registered-discriminant", "method", "technique:the-reconstruction-method",
     "pre-registration",
     "The method's decisive move: criterion, threshold and the null's prediction all written "
     "down BEFORE anything is counted. It is what makes section 6's reversal a result rather "
     "than an embarrassment — the same registration that would have crowned the law killed it.",
     ("story", "Decisive questions were settled by *pre-registered* tests"), {}),

    ("def:the-standing-null", "object", "technique:the-reconstruction-method",
     "the standing null",
     "The rival never retired: that the corpus is one mind rhyming with itself rather than "
     "ten attempts on one object. The definition is stated with this rival alive, not after "
     "it was defeated — it was not.",
     ("story", "which became the standing null hypothesis and was never retired"), {}),

    ("def:the-confound", "object", "technique:the-reconstruction-method", "the standing confound",
     "Recorded, not resolved: the reconstruction is itself a stack of describers handing residues "
     "upward — the very shape of the theory it reconstructs — and the join's mathematics came "
     "into existence only once an audit named it missing. Whether the instrument discovered the "
     "object or completed it is left undecided by the record, and the definition says as much.",
     ("story", "structurally resembles the theory it was reconstructing"), {}),

    ("portal:genesis-jsonl", "portal-ref", "technique:the-reconstruction-method",
     "the genesis ledger",
     "PORTAL: the append-only ledger of the reconstruction's own revisions — 22 rows across "
     "five loops, each naming what changed and what residue was left unabsorbed, terminating "
     "at the provisionally-complete verdict.",
     ("genesis", "G022"), {}),

    ("portal:the-story", "portal-ref", "technique:the-reconstruction-method", "the Story",
     "PORTAL: the seven-part linear read written for him, which is the surface this whole "
     "definition transports. Private to him by his ruling; this graph refs its lines and "
     "reproduces none of its prose.",
     ("story", "This document is for you, Gerard"), {}),

    # ---- part 3: what was found ---------------------------------------------
    ("res:the-graded-findings", "finding", GOAL_ID, "the graded findings",
     "THE FINDINGS LEDGER: every claim carries the tier word that bounds it — solid, "
     "suggestive, one data point, withdrawn — and the withdrawals sit in the same list at the "
     "same standing as the wins. That grading IS part of the definition: synthetics is stated "
     "at the strength its own instruments could pay for.",
     ("story-part", 3), {}),

    # (the 13 §3 findings are appended programmatically, in section order)

    ("res:zero-cross-half-equations", "finding", "res:the-graded-findings",
     "zero cross-half equations",
     "The audit counted, across the working tree, the whole recorded history and the deleted "
     "material with macros expanded, how often a symbol belonging to one half sits as a defined "
     "argument inside a formula belonging to the other. The count comes back zero in every one of "
     "those places. That negative fact is what the entire definition turns on.",
     ("claim", "C1"), {}),

    ("res:tuple-not-a-derivation", "finding", "res:the-graded-findings",
     "the best offer is a tuple",
     "The corpus's strongest cross-half object is a comma-separated triple co-listing a cost "
     "symbol and a residue symbol as coordinates — never an equation relating them, and its "
     "cost symbol is never connected to the log-rank price, so the chain has no first link.",
     ("claim", "C2"), {}),

    ("res:rqm-rival-win", "finding", "res:the-graded-findings", "a rival won the discriminator",
     "The pre-registered discriminator between 'one latent object' and 'two programmes joined "
     "by an analogy' resolved FOR the rival: the latent-object reading predicted at least one "
     "derived cross-half edge, and there are none. Shipped because the ledger ships whole.",
     ("claim", "C3"), {}),

    ("res:pt1-cut", "finding", "res:the-graded-findings", "a primitive was cut",
     "One alleged load-bearing primitive was subjected to a removal test, collapsed nothing, "
     "and was cut. A definition that survives the deletion of one of its own posited parts is "
     "reporting what is load-bearing rather than what was proposed.",
     ("claim", "C11"), {}),

    ("res:e2-partially-superseded", "finding", "res:the-graded-findings",
     "a primer statement superseded itself",
     "An intermediate exposition's account of the scope-for-warrant exchange was overtaken by "
     "the project's own later run. Recorded as superseded rather than quietly rewritten.",
     ("claim", "C12"), {}),

    ("res:corrections-are-the-instrument", "finding", "res:the-graded-findings",
     "the corrections are the instrument working",
     "The reversals are reported against the reconstruction itself, not only against the "
     "corpus: the same books are kept on both sides of the instrument. This is the clause that "
     "makes the tier words trustworthy rather than decorative.",
     ("claim", "C13"), {}),

    ("res:external-anchor-residue", "residue", "res:the-graded-findings",
     "the external-anchor residue",
     None,   # composed from the anchor census at compile time
     ("file", RULINGS, "588/643 residue anchors"), {}),

    ("portal:genesis-claims-ledger", "portal-ref", "res:the-graded-findings",
     "the grade-1 claims ledger",
     "PORTAL: the 13 grade-1 claims with their five-value statuses (standing / superseded / "
     "withdrawn / rival-win / cut) and their quote anchors. This is the authored vocabulary "
     "the epistemic_status slots on this graph's findings are read from — none is invented here.",
     ("file", CLAIMS, "Status vocabulary: standing | superseded | withdrawn | rival-win | cut"),
     {}),

    # ---- part 4: the two halves and the fused word ---------------------------
    ("def:two-halves-and-the-fused-word", "object", GOAL_ID, "two halves, one word",
     "THE CENTRAL STRUCTURAL FACT: the corpus is two bodies of work that never touched, held "
     "together by a single overloaded word. Everything the definition can and cannot claim "
     "follows from this shape.",
     ("story-part", 4), {}),

    ("def:relational-half", "object", "def:two-halves-and-the-fused-word", "the relational half",
     "HALF ONE: certificates that will not globalise, records that resist merging, and the "
     "residue left when a description closes on itself. Its objects are local; its failures are "
     "obstructions standing between describers. Against the strongest inference-theoretic rival "
     "it wins outright.",
     ("story", "One half is relational"), {}),

    ("def:variational-half", "object", "def:two-halves-and-the-fused-word", "the variational half",
     "HALF TWO: costs indexed by rank, prices logarithmic in it, partition functions taken over "
     "description complexity. Its objects are prices; its failures are bills that cannot be paid. "
     "It survives every structural rival — nothing lacking a cost ledger reproduces its "
     "measurements.",
     ("story", "The other half is variational"), {}),

    ("def:lateral-remainder", "object", "def:two-halves-and-the-fused-word",
     "the lateral remainder",
     "REMAINDER ONE — two describers, one moment: certified records that refuse to combine. Its "
     "type is an ELEMENT — a commutator, addable and normable, resident inside an algebra, "
     "transforming two-sidedly. Its decisive instance is an obstruction between two provably "
     "sufficient maps in which no generator appears at all.",
     ("story", "A lateral one"), {}),

    ("def:vertical-remainder", "object", "def:two-halves-and-the-fused-word",
     "the vertical remainder",
     "REMAINDER TWO — one describer, two levels: a dynamics that refuses to descend through "
     "coarse-graining. Its type is a MAP, Delta_C = PL - G_M P, living irreducibly between two "
     "spaces, and it transforms ONE-SIDEDLY. That is why enlarging the algebra never reconciles "
     "it with the lateral object.",
     ("story", "the exact gap between a candidate coarse law and the true generator"), {}),

    ("def:the-fused-word", "object", "def:two-halves-and-the-fused-word", "the fused word",
     "THE FUSION: one word — 'residue' — made to carry both remainders, from a dated site "
     "where both types were written down together and the page that told them apart was "
     "removed. Thereafter the shared name let a paper change what its central object WAS "
     "instead of paying a derivation it owed, and the type migrations land exactly at the "
     "missing steps. The fix is free and it is item six of the forward programme: two objects, "
     "two names.",
     ("story", "One word, two objects, and the only page that told them apart removed"), {}),

    ("def:synthesises-not-inherits", "object", "def:two-halves-and-the-fused-word",
     "synthesises, not inherits",
     "THE LITERAL CLAIM carried by the name, and the definition's own core sentence: a finite "
     "description synthesises its law rather than inheriting one. Everything else in this graph "
     "is an object that claim requires, a measurement of it, or an admission of a bill it still "
     "cannot settle.",
     ("story", "does not inherit its law but synthesises one"), {}),

    ("thm:memory-kernel-identity", "derived-theorem", "def:two-halves-and-the-fused-word",
     "the memory-kernel identity",
     "The relational half's single strongest result: the closure residue is precisely the object "
     "that produces the memory kernel — whatever a description throws away comes back as the "
     "shape of its recall. The proof exists only in the ELEMENT frame, on a branch nobody builds, "
     "while the frame the canonical paper committed to is the one in which it cannot be proved.",
     ("story", "showing that this same residue generates the memory kernel"), {}),

    ("portal:the-edge-audit", "portal-ref", "def:two-halves-and-the-fused-word",
     "the cross-half edge audit",
     "PORTAL: the audit that swept the full tree, the full history and the graveyard with "
     "macros expanded and returned the zero count. Written by a rival, which is why the count "
     "carries the weight it does.",
     ("file", f"{GENESIS}/adversarial/audits/check_5_edges.md",
      "No computed bridge between the two calculi exists anywhere in the tree"), {}),

    # ---- part 5: the join ---------------------------------------------------
    ("def:the-join", "object", GOAL_ID, "the join",
     "THE HALF-BUILT BRIDGE: an action defined over paths in description space, assembled almost "
     "wholly out of theorems already sitting in the corpus doing work they were never hired for. "
     "Five obligations discharged, two failed informatively, and every route arrives at the same "
     "lone missing equation.",
     ("story-part", 5), {}),

    ("def:description-space-arena", "object", "def:the-join", "the arena",
     "A description is a point: the coefficient vector of whichever observables were retained "
     "inside an exponential-form represented law. A description-PATH is then a sequence of "
     "revisions, with revision depth serving as the time parameter — depth as renormalisation "
     "time being an identification the corpus has already published.",
     ("story", "A description is a point"), {}),

    ("def:log-rank-cost", "object", "def:the-join", "K(r) = log r",
     "THE PRICE LAW of the variational half: resolving detail at rank r costs K(r) = log r, "
     "forced twice over by derivations with no step in common — one axiomatic, about rankings "
     "invariant under relabelling, one physical, about registers that must hold distinguishable "
     "states. The same theorem reappears unrecognised as the price of borrowing.",
     ("story", "the price of resolving detail at rank r must be"), {}),

    ("def:the-action-S", "object", "def:the-join", "the action",
     "THE ASSEMBLED OBJECT: cost accumulates along a path through description space out of three "
     "contributions — a metric charge for continuous revision, a standing rank potential for "
     "whichever description is held at the time, and a borrow charge for warrant no continuous "
     "route reaches. Everything about it is pinned down except one ratio of coefficients.",
     ("story", "S[path] ="), {}),

    ("def:borrow-term", "object", "def:the-join", "the borrow term",
     "The jump price for imported authority, and it is forced rather than chosen. Grant three "
     "weak properties — no negative borrowings, additivity across independent lenders, "
     "monotonicity with respect to an authority PREORDER (never a scalar) — and the corpus's own "
     "log-cost theorem transfers onto that second ordering unchanged. The price of borrowing had "
     "been a rank price all along; nobody had read it that way.",
     ("story", "B = "), {}),

    ("def:no-free-symmetry", "principle", "def:the-join", "no free symmetry",
     "HIS PRINCIPLE, made exact: no operation on a description is without effect, or it would not "
     "have been an operation on a description. As geometry that is ker g = 0 — description space "
     "carries no free direction except pure relabelling. Its contrapositive diagnoses the fused "
     "word: wherever gauge freedom shows up the register is over-complete, and every lineage paid "
     "for that slack.",
     ("story", "It is the statement ker g = 0"), {}),

    ("def:conservation-charge-E", "object", "def:the-join", "the conserved charge E",
     "THE ONE FALSIFIABLE PREDICTION NOBODY HAS SCORED: invariance of the action under depth "
     "translation yields exactly one Noether charge — revision rate squared minus the standing "
     "rank cost — and no-free-symmetry forbids a second. Held flat along a lineage it says the "
     "join's dynamics tracks something real; observed to drift it kills the equation of motion in "
     "its present form. No measurement of it exists.",
     ("story", "Depth-translation invariance yields one conserved quantity"), {}),

    ("def:exchange-rate-open-problem", "open-problem", "def:the-join",
     "the exchange rate beta/lambda",
     "THE ONE MISSING EQUATION, and the terminal form of the programme's question. The action "
     "carries two rank costs denominated differently: one prices typicality by counting and has "
     "an equation of state; the other prices authority and has none, because nothing fixes what a "
     "unit of borrowed warrant buys in counting units. The sharing derivations hit the identical "
     "wall from the far side — a spectral multiplicity matched to a rank count by trace alone. "
     "Supply the equation and the halves are joined by mathematics; prove that no such equation "
     "exists and the hole at the centre becomes a theorem one number wide.",
     ("story", "Derive the exchange rate between the counting currency"), {}),

    ("thm:fisher-metric-from-relative-entropy", "derived-theorem", "def:the-join",
     "the metric is free",
     "The comparison functional between descriptions was already proved to be uniquely the "
     "relative entropy; expanded to second order in an infinitesimal revision it yields the "
     "unique quadratic form, computable wherever the cost is written explicitly. It is the "
     "line the corpus derived and then deleted, reinstated here as the kinetic term.",
     ("story", "the Fisher metric, computable at any site"), {}),

    ("thm:static-limit-is-the-zeta-function", "derived-theorem", "def:the-join",
     "the static limit is the zeta function",
     "Paths of zero depth are single descriptions, and the sum over them reproduces exactly the "
     "partition function of the cost-of-complexity paper. Stronger still: that paper's "
     "depth-indexed sum over nested chart refinements already IS this path integral, cut down to "
     "self-funded paths — and what the cut removes is precisely the borrow term.",
     ("story", "the cost-of-complexity paper's partition function, recovered on the nose"), {}),

    ("thm:critical-point-at-infinite-fisher-distance", "derived-theorem", "def:the-join",
     "the centre, priced",
     "On the rank line the metric coincides with the rank ensemble's own susceptibility and blows "
     "up at the critical exponent, so the distance out to that point grows without bound, "
     "logarithmically. His prediction — that the hole at the centre never seals and only grows "
     "dearer to narrow — thereby becomes arithmetic. One qualifier travels with it: a finite "
     "vocabulary keeps the distance finite, so constitutive absence needs an unbounded one.",
     ("story", "the critical point lies at infinite distance"), {}),

    ("thm:sharing-is-never-cheaper-when-exact", "derived-theorem", "def:the-join",
     "the sharing lemma",
     "Exactness kills the bargain. If one register must serve both descriptions without loss, its "
     "log-rank price never undercuts the price of two private registers; any saving at all "
     "requires deliberate imprecision. So the conjugacy clause he wrote down as an assumption is "
     "available to him as a theorem.",
     ("story", "a register exact for both descriptions is"), {}),

    ("thm:conflict-penalty-is-the-rank-deficit", "derived-theorem", "def:the-join",
     "the conflict penalty",
     "One paper gave three mutually inconsistent accounts of a single object, and the lawful form "
     "of the penalty for that is unique, forced by the same functional equation that forced the "
     "log-rank price. It is the rank deficit — refinement demanded and never paid for. The "
     "quadratic version actually implemented is refuted as a double count.",
     ("story", "it comes out as the rank deficit"), {}),

    ("thm:rank-two-crossover", "derived-theorem", "def:the-join", "the crossover at rank two",
     "Shared imperfection overtakes private perfection exactly above rank two, which makes the "
     "two-level system the EXACT boundary case of co-tenancy — reached by two derivations with no "
     "step in common. At the shared optimum the iso-cost contours are hyperbolas tangent to a "
     "straight rank budget: an uncertainty product, derived as economics.",
     ("story", "the two-level system is the *exact* marginal case"), {}),

    ("thm:rent-plus-blur-equals-two", "derived-theorem", "def:the-join", "rent plus blur",
     "The self-modelling paper's doubling result slots in here once its faithfulness requirement "
     "is loosened to a frame constant: rent plus round-trip blur sums to two and stays there. A "
     "describer that embodies itself therefore pays a fixed total, and all it governs is how that "
     "total divides between multiplicity and imprecision. This 2 weighs a spectrum; the "
     "crossover's 2 counts a rank. That mismatch is the missing equation seen from the other end.",
     ("story", "so rent plus blur equals two, invariantly"), {}),

    ("res:funding-mix-is-a-flat-direction", "finding", "def:the-join",
     "funding is a flat direction",
     "TYPED FAILURE, full value: the observed fall in fresh derivation over a lineage does NOT "
     "come out of the action as any equation of motion — the action puts a price on the move, "
     "never on where the funding came from. The fall re-derives instead as entropy: a finite internal stock drawn "
     "against an unbounded external one, which fixes sign and monotonicity and supplies no slope.",
     ("story", "so funding is a flat direction"), {}),

    ("res:saddle-dichotomy-refuted", "finding", "def:the-join", "the saddle dichotomy, refuted",
     "TYPED FAILURE, full value: the conjecture of one privileged saddle where descriptions "
     "commute plus families where they do not fails at the level of mechanism. Wherever gluing "
     "breaks down no common chart exists, so what looked like a single path integral is a "
     "patchwork stitched together by holonomy. The relational half therefore enters the join as "
     "the obstruction to writing one sum, not as a family of saddles.",
     ("story", "is refuted in mechanism"), {}),

    # ---- part 6: what fell ---------------------------------------------------
    ("res:the-price-law-fell", "finding", GOAL_ID, "the price law fell",
     "THE REVERSAL, told as a win: the project's most quotable claim — that a lineage's retreats "
     "grow dearer as it ages — was killed twice by in-house instruments and finally came back "
     "with the opposite sign. It stands here at the same rank as the surviving results, because "
     "these reversals are the reason to credit anything else in the list.",
     ("story-part", 6), {}),

    ("res:sweep-correction-downgrade", "finding", "res:the-price-law-fell",
     "the sweep correction",
     "FIRST KILL: a confound audit discovered that the costliest event in four lineages out of "
     "five was one and the same event — a single four-second batch build, committed once. Counted "
     "once, the pre-registered significance evaporated and the verdict was withdrawn on the "
     "record. It is the project's most checkable datum: four file timestamps.",
     ("claim", "C4"), {}),

    ("res:price-law-reversal-on-census", "finding", "res:the-price-law-fell",
     "the census reversed it",
     "SECOND KILL: the census built to save the finding flipped its sign instead. It priced every "
     "on-disk transition from diffs, blind to the narrated histories. The curated record had been "
     "a roster of retreats, so choosing events by their being retreats and then asking whether "
     "retreats grow dearer later was itself the selection that produced the rise. Nothing in the "
     "robustness family brings it back.",
     ("claim", "C5"), {}),

    ("portal:the-confound-audit", "portal-ref", "res:the-price-law-fell", "the confound audit",
     "PORTAL: the in-house audit that noticed the shared event and re-ran both permutation "
     "tests with it counted once.",
     ("file", f"{GENESIS}/adversarial/audits/check_confounds.md", "neither clears 0.05"), {}),

    ("portal:the-census", "portal-ref", "res:the-price-law-fell", "the re-powered census",
     "PORTAL: the 35-event census, its scoring rule, its event table and its threats section "
     "— the run that reversed the headline and named the selection bias that made it.",
     ("file", f"{GENESIS}/adversarial/discriminant/price_curve_repowered.md",
      "Rising price: refuted, not merely unsupported."), {}),

    # ---- part 7: what to do next ---------------------------------------------
    ("def:the-forward-programme", "object", GOAL_ID, "the forward programme",
     "WHAT THE DEFINITION OWES, in his ordering: inspect the fall himself; derive the exchange "
     "rate or show it cannot exist; run the conservation test; hunt for a single free move; price "
     "a control corpus; rescue the stranded theorem and split the fused word in two; supply the "
     "lateral half a real instance; and only after all of that, the treatise.",
     ("story-part", 7), {}),

    ("def:the-stranded-theorem-and-the-unfusing", "object", "def:the-forward-programme",
     "bring the theorem home, split the word",
     "The two free repairs: publish the memory-kernel identity in the frame that admits its proof "
     "instead of leaving it outside every build, and from here on give the two remainders "
     "separate names. Neither asks for new mathematics, and the second costs nothing whatever.",
     ("story", "Rescue the stranded theorem, and un-fuse the word"), {}),

    ("def:response-function-synthetics", "open-port", "def:the-forward-programme",
     "the response-function sense (N37)",
     None,   # composed from OPEN_STACK's own row at compile time
     ("file", OPEN_STACK,
      "we need to feed you synthetics as Matias has given you some nice stuff"), {}),

    ("technique:atlas-joint-experiments", "experiment-spec", "def:the-forward-programme",
     "the atlas touchpoint",
     "A SPEC, NOT A RESULT — two experiments the atlas could run against this definition, both "
     "gated on atlas Phases 4-5, which are ABSENT (Phase 3's pre-registered stop fired and the "
     "diagnosis was banked before any organ was built). (1) The lateral remainder made "
     "measurable: place one leaf under two lens placements of the multi-lens fibre arm at "
     "12k-leaf scale and measure the obstruction between the two placements — the lateral "
     "object with a real instance instead of a 3x3 toy. (2) The price-pair ledger run as an "
     "instrument: score counting cost and authority cost separately over fold events and see "
     "whether an empirical exchange rate appears where the derivation has none. Neither is "
     "claimed; both are named so the gate is visible.",
     ("file", ATLAS_DESIGN, "Run all five over the existing 12,000-plus-leaf corpus"), {}),

    ("portal:atlas-phase3-stop", "portal-ref", "technique:atlas-joint-experiments",
     "the atlas Phase 3 stop",
     "PORTAL, and the GATE on the node above: the atlas's pre-registered Phase 3 stop "
     "condition FIRED — the incumbent architecture lost to a flat dense index at comparable "
     "spend, so the measured advantage was diagnosed as a wake advantage, not a retrieval "
     "one, and the diagnosis was banked before any organ was built. Phases 4 and 5, which the "
     "two experiments need, do not exist on this tree.",
     ("file", ATLAS_PHASE3, "the pre-registered stop **FIRED**"), {}),

    ("portal:the-cold-read", "portal-ref", "def:the-forward-programme", "the cold read",
     "PORTAL: the outside reader's own scoring, verbatim in its own file — including the "
     "technical correction that was accepted (element versus map is a matter of transformation "
     "law, not an absolute dichotomy) and their blunt ceiling, that the measurements here are "
     "measurements of manuscripts rather than of nature.",
     ("story", "The cold read is banked verbatim"), {}),

    # ---- the imported literature (the authority side of the price pair) ------
    ("def:imported-literature", "object", GOAL_ID, "the imported literature",
     "THE AUTHORITY SIDE, made countable: the container for every outside work this graph borrows "
     "from. Its anchor is the line that turns imported warrant into a priced object — the borrow "
     "term in the action — because that, not any list, is what makes these countable in this "
     "project's terms; each member below carries its own naming line. They are counted in "
     "prices.jsonl on their own column and never summed with the counting cost.",
     ("story", "a borrow term for imported warrant"), {}),
]

# the literature nodes: (id, term, essence, story needle, the claim node each bears)
CITATIONS = [
    ("ref:zipf", "Zipf's law",
     "The empirical rank-frequency regularity the price half exists to explain: a few "
     "components dominate and finer detail costs ever more.",
     "Zipf-like law", "def:log-rank-cost"),
    ("ref:landauer", "Landauer erasure",
     "The physical route to the log-rank price: registers holding distinguishable states pay "
     "for distinguishability. It is the second, independent derivation whose agreement with "
     "the axiomatic route is the evidence the form is forced.",
     "a Landauer-style physical one", "def:log-rank-cost"),
    ("ref:chentsov-petz", "Chentsov, and Petz's quantum family",
     "The classical uniqueness theorem for information metrics and its quantum family. The "
     "third withdrawal is about this citation: the corpus did not miss it — it named it, "
     "selected the metric with full warrant, carried it four versions, and deleted it.",
     "Chentsov's, with Petz's quantum family beside it", "res:chentsov-petz-uncited"),
    ("ref:nakajima-zwanzig", "the Nakajima-Zwanzig identity",
     "The projection-operator memory-kernel formalism the relational half's strongest theorem "
     "is an exact instance of.",
     "Nakajima", "thm:memory-kernel-identity"),
    ("ref:fisher-from-kl", "the Fisher metric from relative entropy",
     "The standard second-order expansion of relative entropy into the Fisher information "
     "metric — derived inside the corpus, then deleted from it, and reinstated by the join as "
     "its kinetic term.",
     "the Fisher-from-KL line you derived and then deleted", "thm:fisher-metric-from-relative-entropy"),
    ("ref:noether", "Noether's theorem",
     "The symmetry-to-conservation correspondence the join uses to extract its one charge from "
     "depth-translation invariance.",
     "Noether charge available", "def:conservation-charge-E"),
    ("ref:feshbach", "the Feshbach projection",
     "The closed-form subspace correction the eigensolver paper derives and then honestly "
     "proves generically intractable — the relational half's clearest example of an exact "
     "object no real algorithm can hold.",
     "the Feshbach metric", "def:relational-half"),
    ("ref:wigner-friend", "Wigner's friend",
     "The measurement-observer problem whose one-hour scratch exploration is the only page in "
     "the corpus that writes both remainder-objects down with their types visible — the "
     "fusion's dated site.",
     "scratch exploration of Wigner's friend", "def:the-fused-word"),
    ("ref:schrodinger-operator", "the Schrodinger-type operator",
     "The posited apex of the learning-theory paper, from which known trainability phenomena "
     "are re-derived as consequences of one object rather than a collection.",
     "a Schr", "def:variational-half"),
]

# the 13 §3 findings, in section order: (id, term, authored essence, claim id or None,
# the literature node the finding rests on, the portal carrier or None)
FINDINGS = [
    ("res:two-halves-one-unbuilt-join", "two bodies of work, not one",
     "There are two programmes here, not one. The sweep took in every working file and every "
     "distinct historical version across the repository's whole history, macros expanded, and "
     "found no cross-half equation anywhere. Stronger still, the two vocabularies run "
     "anti-correlated in time: no single version of anything ever carried both.", "C10", "ref:feshbach", "portal:the-edge-audit"),
    ("res:the-fusion-has-a-date-and-a-site", "the fusion has a date and a site",
     "One document, and only one, ever set both remainder-objects on the page with their types on "
     "show. It was folded into another paper, its calculation dropped, and the name they had "
     "shared outlived them. From then on a paper facing an unpayable derivation could quietly "
     "swap what its central object was, and those swaps sit precisely where the record shows the "
     "missing step. The diagnosis was pre-committed: it had to change how the source papers "
     "scan when reread, and on four separate occasions it did.",
     "C9", "ref:wigner-friend", "portal:genesis-jsonl"),
    ("res:every-change-is-billed", "every change gets billed",
     "Add up a paper's life and the two credit columns — authority taken in, derivation put out — "
     "overshoot the claim strength given up. The ledger fails to close, and it fails the same way "
     "under three separate codings, one of them made without sight of any narrative history. The "
     "sharpest case: the corpus's most thoroughly derived revision took on no outside authority "
     "whatever and was still charged 9 out of 15. The charge follows the move; how it was funded "
     "does not discharge it.",
     "C8", "ref:landauer", "portal:the-census"),
    ("res:honesty-is-cost-negative", "honesty is cost-negative",
     "Exactly one lineage bills less as it goes on, and the decline is strictly ordered across "
     "every transition it makes. It is also the only lineage sitting under a standing outside "
     "verdict gate, and the one that once let its own numerics destroy a headline it had "
     "registered, retiring claim and machinery in a single move. Neither statistical correction "
     "that wrecked other findings touches it. Retiring debt is the sole revision behaviour here "
     "that gets cheaper with repetition.",
     "C6", "ref:schrodinger-operator", "portal:the-census"),
    ("res:two-level-system-is-the-margin", "the smallest quantum system is the margin",
     "Rank two is where co-tenancy stops paying. Below it a shared, deliberately imperfect "
     "register costs more than a private exact one apiece; above it, less; at exactly two the "
     "advantage is nil. Two derivations with no step in common arrive at the same threshold, and "
     "the trade between sharpening and blurring appears as a tangency condition against a linear "
     "budget — an uncertainty relation obtained as economics rather than assumed.", None, "ref:zipf", None),
    ("res:the-primer-transmits", "it transmits",
     "A physicist with no prior contact read the primer once, cold, and afterwards could "
     "reconstruct the architecture, the distinction between the two failures, and the precise "
     "evidential grade of each price claim without going back to the text — and returned one "
     "correct technical sharpening, which was taken up. They put their own ceiling at "
     "verification rather than understanding.",
     None, "ref:chentsov-petz", "portal:the-cold-read"),
    ("res:derivation-supply-depletes", "derivation supply dries up",
     "Only one of the priced components trends along a lineage: the amount of new derivation "
     "offered, which declines — real, but under the pre-registered threshold. The partner claim, "
     "that borrowing climbs to fill the gap, failed: what actually happens is that later "
     "revisions move less of every component. Read it as exhaustion followed by silence.",
     None, "ref:landauer", "portal:the-census"),
    ("res:maturity-is-cheap", "maturity is cheap",
     "Across the census, price per revision declines as a paper ages — again under the "
     "pre-registered threshold, so a direction rather than a law. Costly moves cluster near the "
     "beginning. This is what the fallen finding becomes once corrected.", None, "ref:zipf", "portal:the-census"),
    ("res:the-naming-was-the-costliest-act", "naming the programme was the costliest act",
     "Naming the programme was also the most expensive single act it records. Four terminal "
     "manuscripts finished seconds apart, then one commit moved them all under the Synthetics "
     "banner, wired citations to papers nobody had written, and added the only three sentences "
     "anywhere that verbally span the two halves. Scored as one event: 14 out of 15, against a "
     "census average of 6. It was found after the scoring scheme had been fixed, and it rests on "
     "one event, so it is typed as an observation.", "C7", "ref:zipf", "portal:the-confound-audit"),
    ("res:generator-free-obstruction-toy", "an obstruction no inference formalism reaches",
     "A residue that refuses to vanish between two classical averaging maps, each demonstrably a "
     "sufficient statistic for whatever dynamics you care to impose — so no story about lost "
     "information or updated belief can explain it, and no generator enters the calculation "
     "anywhere. This is the argument that settles whether the relational half is disguised "
     "Bayesian inference; it is not. It is also a 3x3 toy with two partitions written by hand. "
     "The argument needs nothing larger; the physics does.", None, "ref:feshbach", None),
    ("res:rising-retreat-price", "retreats get dearer as a lineage ages",
     "WITHDRAWN — the project's most quotable claim. Pre-registered with the null's prediction "
     "named in advance, priced by two extractors blind to each other on deliberately different "
     "metrics, and it cleared its bar. Then it was killed twice by in-house instruments and "
     "reversed in sign on the full census. It stands in this ledger at full length because the "
     "reversal is worth more than the finding was.", "C4", "ref:zipf", "portal:the-census"),
    ("res:scope-for-warrant-exchange", "the scope-for-warrant exchange",
     "WITHDRAWN. The proposed conserved barter — give up reach, take on borrowed standing — came "
     "through the first correction sharper than before and then died on the census, which found "
     "no upward trend in borrowed standing over a paper's lifetime at all. One residue survives: "
     "how much authority a revision borrows PREDICTS its price better than any other component "
     "does. That is a statement about what costly revisions spend, not about what accumulates.", "C12", "ref:landauer", "portal:the-census"),
    ("res:chentsov-petz-uncited", "the missing theorem is uncited because unknown",
     "WITHDRAWN, and the strangest of the three. An early primer asserted that the uniqueness "
     "result for classical information metrics is cited nowhere in the corpus — which would have "
     "made this programme an unknowing lap around a gap the literature had already closed. It "
     "is false: four versions "
     "of one paper argue their state space classical, invoke that theorem explicitly, and select "
     "the metric with full warrant — after which the section is deleted and its principle "
     "downgraded from a derived statement to a postulate. That metric was bought, held, and then paid "
     "away.", None, "ref:chentsov-petz", "portal:genesis-jsonl"),
]

# thematic (non-structural) edges: (node, target, rel)
THEMATIC_EDGES = [
    (GOAL_ID, "def:synthesises-not-inherits", "derives-from"),
    (GOAL_ID, "def:relational-half", "derives-from"),
    (GOAL_ID, "def:variational-half", "derives-from"),
    (GOAL_ID, "def:exchange-rate-open-problem", "derives-from"),
    ("def:two-halves-and-the-fused-word", "def:relational-half", "derives-from"),
    ("def:two-halves-and-the-fused-word", "def:variational-half", "derives-from"),
    ("def:relational-half", "def:lateral-remainder", "derives-from"),
    ("def:relational-half", "ref:feshbach", "rests-on-literature"),
    ("def:variational-half", "def:log-rank-cost", "derives-from"),
    ("def:variational-half", "ref:zipf", "rests-on-literature"),
    ("def:lateral-remainder", "def:the-fused-word", "derives-from"),
    ("def:vertical-remainder", "def:the-fused-word", "derives-from"),
    ("def:vertical-remainder", "thm:memory-kernel-identity", "derives-from"),
    ("def:the-fused-word", "ref:wigner-friend", "rests-on-literature"),
    ("def:synthesises-not-inherits", "ref:nakajima-zwanzig", "rests-on-literature"),
    ("thm:memory-kernel-identity", "ref:nakajima-zwanzig", "rests-on-literature"),
    ("def:the-join", "def:the-action-S", "derives-from"),
    ("def:the-join", "ref:fisher-from-kl", "rests-on-literature"),
    ("def:the-action-S", "thm:fisher-metric-from-relative-entropy", "derives-from"),
    ("def:the-action-S", "def:log-rank-cost", "derives-from"),
    ("def:the-action-S", "def:borrow-term", "derives-from"),
    ("def:the-action-S", "def:description-space-arena", "derives-from"),
    ("def:borrow-term", "def:log-rank-cost", "derives-from"),
    ("def:conservation-charge-E", "def:the-action-S", "derives-from"),
    ("def:conservation-charge-E", "def:no-free-symmetry", "derives-from"),
    ("def:conservation-charge-E", "ref:noether", "rests-on-literature"),
    ("def:exchange-rate-open-problem", "def:borrow-term", "derives-from"),
    ("def:exchange-rate-open-problem", "thm:rank-two-crossover", "derives-from"),
    ("def:exchange-rate-open-problem", "thm:rent-plus-blur-equals-two", "derives-from"),
    ("def:exchange-rate-open-problem", "ref:chentsov-petz", "rests-on-literature"),
    ("thm:fisher-metric-from-relative-entropy", "ref:fisher-from-kl", "rests-on-literature"),
    ("thm:static-limit-is-the-zeta-function", "def:log-rank-cost", "derives-from"),
    ("thm:static-limit-is-the-zeta-function", "ref:zipf", "rests-on-literature"),
    ("thm:critical-point-at-infinite-fisher-distance", "ref:fisher-from-kl", "rests-on-literature"),
    ("thm:critical-point-at-infinite-fisher-distance",
     "thm:fisher-metric-from-relative-entropy", "derives-from"),
    ("thm:sharing-is-never-cheaper-when-exact", "ref:landauer", "rests-on-literature"),
    ("thm:sharing-is-never-cheaper-when-exact", "def:log-rank-cost", "derives-from"),
    ("thm:conflict-penalty-is-the-rank-deficit", "ref:landauer", "rests-on-literature"),
    ("thm:conflict-penalty-is-the-rank-deficit", "def:log-rank-cost", "derives-from"),
    ("thm:rank-two-crossover", "ref:schrodinger-operator", "rests-on-literature"),
    ("thm:rank-two-crossover", "thm:sharing-is-never-cheaper-when-exact", "derives-from"),
    ("thm:rent-plus-blur-equals-two", "ref:feshbach", "rests-on-literature"),
    ("res:funding-mix-is-a-flat-direction", "ref:landauer", "rests-on-literature"),
    ("res:funding-mix-is-a-flat-direction", "def:the-action-S", "derives-from"),
    ("res:funding-mix-is-a-flat-direction", "res:derivation-supply-depletes", "derives-from"),
    ("res:saddle-dichotomy-refuted", "ref:feshbach", "rests-on-literature"),
    ("res:saddle-dichotomy-refuted", "def:lateral-remainder", "derives-from"),
    ("res:the-graded-findings", "ref:chentsov-petz", "rests-on-literature"),
    ("res:the-price-law-fell", "ref:zipf", "rests-on-literature"),
    ("res:the-price-law-fell", "technique:pre-registered-discriminant", "derives-from"),
    ("res:sweep-correction-downgrade", "ref:zipf", "rests-on-literature"),
    ("res:sweep-correction-downgrade", "portal:the-confound-audit", "evidenced-by"),
    ("res:sweep-correction-downgrade", "res:the-naming-was-the-costliest-act", "derives-from"),
    ("res:price-law-reversal-on-census", "ref:zipf", "rests-on-literature"),
    ("res:price-law-reversal-on-census", "portal:the-census", "evidenced-by"),
    ("res:price-law-reversal-on-census", "res:sweep-correction-downgrade", "derives-from"),
    ("res:zero-cross-half-equations", "ref:nakajima-zwanzig", "rests-on-literature"),
    ("res:zero-cross-half-equations", "portal:the-edge-audit", "evidenced-by"),
    ("res:tuple-not-a-derivation", "ref:nakajima-zwanzig", "rests-on-literature"),
    ("res:tuple-not-a-derivation", "portal:the-edge-audit", "evidenced-by"),
    ("res:rqm-rival-win", "ref:wigner-friend", "rests-on-literature"),
    ("res:rqm-rival-win", "technique:pre-registered-discriminant", "derives-from"),
    ("res:pt1-cut", "ref:chentsov-petz", "rests-on-literature"),
    ("res:pt1-cut", "portal:genesis-jsonl", "evidenced-by"),
    ("res:e2-partially-superseded", "ref:chentsov-petz", "rests-on-literature"),
    ("res:e2-partially-superseded", "portal:genesis-claims-ledger", "evidenced-by"),
    ("res:corrections-are-the-instrument", "ref:chentsov-petz", "rests-on-literature"),
    ("res:corrections-are-the-instrument", "portal:genesis-claims-ledger", "evidenced-by"),
    ("res:external-anchor-residue", "ref:nakajima-zwanzig", "rests-on-literature"),
    ("res:external-anchor-residue", "portal:genesis-claims-ledger", "evidenced-by"),
    ("def:response-function-synthetics", "def:relational-half", "derives-from"),
    ("technique:atlas-joint-experiments", "def:lateral-remainder", "derives-from"),
    ("technique:atlas-joint-experiments", "def:exchange-rate-open-problem", "derives-from"),
    ("def:the-stranded-theorem-and-the-unfusing", "thm:memory-kernel-identity", "derives-from"),
    ("def:the-stranded-theorem-and-the-unfusing", "def:the-fused-word", "derives-from"),
    ("def:the-forward-programme", "def:exchange-rate-open-problem", "derives-from"),
    ("def:the-forward-programme", "def:conservation-charge-E", "derives-from"),
    ("def:the-forward-programme", "def:no-free-symmetry", "derives-from"),
    ("def:the-ten-papers", "def:the-prompt-as-fragment", "derives-from"),
    ("technique:the-reconstruction-method", "technique:pre-registered-discriminant",
     "derives-from"),
    ("def:imported-literature", "def:borrow-term", "derives-from"),
]


# ---------------------------------------------------------------------------
# composition
# ---------------------------------------------------------------------------

#: The measured half of the residue node, banked from ONE dated run rather than recomputed
#: at compile time. Recomputing would make the declaration's bytes depend on whether the
#: physics corpus happens to be mounted on the compiling machine — the artefacts would
#: differ between two honest machines and the byte-stability door would fire. So the run is
#: NAMED (contact law) and its numbers are quoted from its own results file, which is a
#: local carrier this graph may ref. Re-run the verifier and update this block when the
#: corpus head advances; the split (derived counts above, measured counts here) is the point.
REVERIFY_RUN = "synthetics papers/synthetics-definition/experiments/RESULTS_anchor_reverification.md"
REVERIFY = {
    "date": "2026-08-13",
    "producer": "experiments/verify_anchors.py",
    "corpus_head": "13da1c1",
    "corpus_commits": 101,
    "verified": 667,
    "total": 667,
    "corpus_verified": 592,
    "corpus_total": 592,
    "drifted": 0,
    "missing": 0,
    "range_broken": 0,
    "corpus_commits_present": 7,
    "corpus_commits_recorded": 7,
    # The 2026-08-13 run measured 0/8 workspace commits reachable behind a shallow-clone
    # boundary of 2026-08-10 and typed the question undecidable without a deepening fetch.
    # The orchestrator ran that fetch on 2026-08-14 (git fetch --unshallow origin -> 1,791
    # commits) and re-ran the verifier: all 8 resolve, no anchor unbacked. Both runs are in
    # the results carrier named by REVERIFY_RUN.
    "workspace_commits_present": 8,
    "workspace_commits_recorded": 8,
    "workspace_anchors_unbacked": 0,
    "unshallow_run": "2026-08-14",
    "workspace_commits_after_unshallow": 1791,
}


def _residue_essence(census: dict) -> str:
    """DECLARED RESIDUE, not evidence (ruling R5). The SPLIT counts are computed from
    anchors.json here, so the node can never overstate its own population; the VERIFIED
    counts are quoted from the dated re-verification run named in the essence, because
    they depend on trees this repo does not contain."""
    r = REVERIFY
    return (
        "DECLARED RESIDUE, not evidence. Of the reconstruction's banked quote anchors, "
        f"{census['residue_foreign']}/{census['residue_total']} residue anchors and "
        f"{census['claim_foreign']}/{census['claim_total']} claim anchors resolve against "
        f"{census['corpus_root']} — the physics corpus. That corpus was ABSENT when this "
        "residue was first declared; it is now PRESENT as a full clone of "
        f"{r['corpus_commits']} commits at head {r['corpus_head']}, so the anchors could "
        f"finally be checked. They were, on {r['date']}, by {r['producer']} "
        f"(results: {REVERIFY_RUN}): {r['verified']} of {r['total']} verify byte-for-byte "
        f"at their recorded offset AND line — including all {r['corpus_verified']} of the "
        f"{r['corpus_total']} formerly unverifiable ones — with {r['drifted']} drifted, "
        f"{r['missing']} missing and {r['range_broken']} out of range. Read that rate with "
        "its cause: the corpus head predates the audit and its tree is clean, so nothing "
        "moved to drift. The commit leg closed in two steps, both in the results carrier: "
        f"the {r['date']} run found all {r['corpus_commits_recorded']} recorded corpus "
        f"commits reachable but 0 of {r['workspace_commits_recorded']} workspace ones "
        "(this repo was then a shallow clone) and typed that undecidable; a deepening "
        f"fetch on {r['unshallow_run']} ({r['workspace_commits_after_unshallow']} commits) "
        f"resolved all {r['workspace_commits_present']}, leaving "
        f"{r['workspace_anchors_unbacked']} anchors unbacked — 15 of 15 recorded commits "
        "now reachable, so content and provenance both hold. WHAT REMAINS RESIDUE, "
        "narrowed twice and still real: the whole census was taken against a STATIC "
        "corpus (head six weeks older than the audit), so anchor survival under corpus "
        "MOTION has never been observed — the synthetic mutation controls in the "
        "verifier are the only evidence drift would even be caught. And every ref in "
        "this conceptric still points at a LOCAL carrier: the corpus is mounted on this "
        "machine at this hour, which is a fact about the machine and not about the "
        "graph, and a ref into it would break on any machine without the mount — a "
        "contact-law breach in graph form."
    )


def _n37_essence(src: Sources) -> str:
    """The N37 open port: declared, unresolved, and explicitly not touched (ruling R8)."""
    return (
        "A DECLARED OPEN PORT, NOT AN ANSWER. There is a second sense of 'synthetics' in his "
        "own usage that this definition does not cover: the RESPONSE-FUNCTION sense — his ask "
        "of 2026-06-11, \"we need to feed you synthetics as Matias has given you some nice "
        "stuff on your operatorial loss paper\" — where a synthetic is an outside reader's "
        "comments folded in as probes wired to the sections they probe, both sides kept, "
        "intelligence paid once at the fold and mechanical forever after. It is BLOCKED, and "
        "the block is his: nobody has named where Matias's feedback lives (file, email or "
        "export). The TRIGGER is exactly that pointer. This node does not answer, close, "
        "narrow or modify that open row — it exists so the definition is honest about its own "
        "incompleteness instead of being quietly narrower than the word it defines."
    )


# ---------------------------------------------------------------------------
# the privacy gate: no essence may elide THE_STORY's prose
# ---------------------------------------------------------------------------
#: THE_STORY is his. The graph POINTS at it (every node carries a `<path>:<line>` ref) and
#: must never carry it: an essence stitched out of his sentences is a copy of his paragraph
#: wearing a node id, and anything that sweeps this project dir or the ledger then carries
#: his prose instead of a pointer to it. Shared technical vocabulary is unavoidable ("the
#: log-rank cost", "the closure residue"); a long contiguous run of his words is not. The
#: compiler REFUSES to emit an essence carrying a verbatim run this long or longer, measured
#: on case-folded word tokens with punctuation and dashes stripped, so the leak cannot come
#: back by inattention in a later edit. The door test re-measures the same thing on the
#: emitted declaration at the threshold the review pre-registered (12).
MAX_VERBATIM_RUN = 9


def _words(text: str) -> list[str]:
    """Case-folded word tokens: the comparison unit for the privacy gate."""
    flat = (text.replace("—", " ").replace("–", " ")
                .replace("’", "'").replace("“", '"').replace("”", '"'))
    return re.findall(r"[a-z0-9']+", flat.lower())


def longest_verbatim_run(essence: str, story_words: list[str]) -> tuple[int, str]:
    """The longest contiguous word run shared by ``essence`` and THE_STORY, and its text."""
    grams: dict[int, set[tuple[str, ...]]] = {}

    def has(n: int, gram: tuple[str, ...]) -> bool:
        if n not in grams:
            grams[n] = {tuple(story_words[i:i + n]) for i in range(len(story_words) - n + 1)}
        return gram in grams[n]

    words = _words(essence)
    best, span = 0, ""
    for i in range(len(words)):
        n = best + 1
        while i + n <= len(words) and has(n, tuple(words[i:i + n])):
            best, span, n = n, " ".join(words[i:i + n]), n + 1
    return best, span


def check_no_story_prose(src: "Sources", goal: dict, nodes: list[dict]) -> None:
    story_words = _words("\n".join(src.lines(STORY)))
    for item in [goal] + nodes:
        run, span = longest_verbatim_run(item["essence"], story_words)
        if run >= MAX_VERBATIM_RUN:
            raise CompileError(
                f"essence of {item['id']} carries a {run}-word verbatim run from {STORY} "
                f"(limit {MAX_VERBATIM_RUN - 1}): {span!r}. Node essences are authored short "
                f"descriptions; the graph refs his prose, it does not copy it.")


def compile_declaration(repo: Path) -> tuple[dict, dict]:
    src = Sources(repo)
    ctx = {
        "parts": src.story_parts(),
        "findings": src.story_findings(),
        "claims": src.claims(),
        "genesis": src.genesis(),
        "cards": src.cards(),
    }
    census = src.anchor_census()

    # -- the goal --------------------------------------------------------
    goal = {
        "id": GOAL_ID,
        "kind": "programme-goal",
        "term": "the definition of synthetics",
        "essence": GOAL_ESSENCE,
        "ref": src.ref_of(STORY, "As written, Synthetics is two rigorous halves"),
        "projection": {
            "epistemic_status": "standing",
            "epistemic_status_source": "projection/claims.json C10 (the architecture claim)",
            "latex_label": GOAL_ID,
            "wording_ruling": "R4 — transport of a surface he has already read; awaiting his redline",
        },
    }

    nodes: list[dict] = []
    edges: list[dict] = []
    parent_of: dict[str, str] = {}

    def add(nid: str, kind: str, parent: str, term: str, essence: str,
            ref: str, projection: dict) -> None:
        proj = dict(projection)
        if nid.split(":", 1)[0] in ("def", "thm", "ref", "fig", "eq"):
            proj.setdefault("latex_label", nid)
        nodes.append({"id": nid, "kind": kind, "parent": parent, "term": term,
                      "essence": essence, "ref": ref,
                      **({"projection": proj} if proj else {})})
        parent_of[nid] = parent

    # -- the spec table, in order ----------------------------------------
    for nid, kind, parent, term, essence, ref_spec, proj in NODES:
        if essence is None:
            essence = (_residue_essence(census) if nid == "res:external-anchor-residue"
                       else _n37_essence(src))
        add(nid, kind, parent, term, essence, resolve_ref(src, ref_spec, ctx), dict(proj))

        # the 13 §3 findings hang under the findings ledger, in section order
        if nid == "res:the-graded-findings":
            for i, (fid, fterm, fessence, cid, _lit, _portal) in enumerate(FINDINGS):
                tier = ctx["findings"][i]["tier"]
                fproj = {
                    "epistemic_status": tier,
                    "epistemic_status_source": "THE_STORY §3 tier word",
                    "story_order": i + 1,
                }
                if cid:
                    fproj["claim_id"] = cid
                    fproj["claim_status"] = ctx["claims"][cid]["status"]
                add(fid, "finding", "res:the-graded-findings", fterm, fessence,
                    resolve_ref(src, ("story-finding", i), ctx), fproj)

        # the literature nodes hang under the imported-literature container
        if nid == "def:imported-literature":
            for rid, rterm, ressence, needle, _bears in CITATIONS:
                add(rid, "literature", "def:imported-literature", rterm, ressence,
                    resolve_ref(src, ("story", needle), ctx),
                    {"epistemic_status": "imported-warrant",
                     "epistemic_status_source": "this project's own borrow typing (def:borrow-term)"})

    # -- the claim-derived statuses on the non-§3 finding nodes -----------
    claim_of = {
        "res:zero-cross-half-equations": "C1",
        "res:tuple-not-a-derivation": "C2",
        "res:rqm-rival-win": "C3",
        "res:pt1-cut": "C11",
        "res:e2-partially-superseded": "C12",
        "res:corrections-are-the-instrument": "C13",
        "res:sweep-correction-downgrade": "C4",
        "res:price-law-reversal-on-census": "C5",
    }
    by_id = {n["id"]: n for n in nodes}
    for nid, cid in claim_of.items():
        proj = by_id[nid].setdefault("projection", {})
        proj["epistemic_status"] = ctx["claims"][cid]["status"]
        proj["epistemic_status_source"] = "projection/claims.json status"
        proj["claim_id"] = cid
        proj["claim_status"] = ctx["claims"][cid]["status"]
    # the two typed failures of §5 and the residue: statuses their own carriers state
    for nid, status, source in (
            ("res:funding-mix-is-a-flat-direction", "typed-failure", "THE_STORY §5 (failed usefully)"),
            ("res:saddle-dichotomy-refuted", "typed-failure", "THE_STORY §5 (failed usefully)"),
            ("res:external-anchor-residue", "declared-residue", "ruling R5 (not evidence)"),
            ("res:the-graded-findings", "standing", "projection/claims.json C13 (the method claim)"),
            ("res:the-price-law-fell", "withdrawn",
             "THE_STORY §6 — the headline, formally withdrawn and then reversed in sign")):
        proj = by_id[nid].setdefault("projection", {})
        proj["epistemic_status"] = status
        proj["epistemic_status_source"] = source

    # -- the structural wire: every member names its container ------------
    for n in nodes:
        edges.append({"node": n["id"], "target": n["parent"], "rel": "in-part",
                      "axis": REL_MAP["in-part"]})

    # -- every container describes itself by the level below ---------------
    # Both directions of the tree are wired on purpose. The child->parent leg is the
    # `contains` grammar (a member names its container). The parent->child leg is what
    # check_coherence reads (a coarse res:/thm:/goal: shell drawing from nothing below it
    # is content-free) and what check_connectivity walks out of the spine — a beat whose
    # members are unreachable from it renders as a spine with no body.
    live = {n["id"] for n in nodes} | {GOAL_ID}
    children: dict[str, list[str]] = {}
    for n in nodes:
        children.setdefault(n["parent"], []).append(n["id"])
    for parent in [GOAL_ID] + [n["id"] for n in nodes]:
        for child in children.get(parent, []):
            edges.append({"node": parent, "target": child, "rel": "draws-from",
                          "axis": REL_MAP["draws-from"]})

    # -- each §3 finding names the literature it rests on and its carrier --
    for i, (fid, _t, _e, _c, lit, portal) in enumerate(FINDINGS):
        edges.append({"node": fid, "target": lit, "rel": "rests-on-literature",
                      "axis": REL_MAP["rests-on-literature"]})
        if portal:
            edges.append({"node": fid, "target": portal, "rel": "evidenced-by",
                          "axis": REL_MAP["evidenced-by"]})

    # -- the literature bears its claim (the schema.AXES grammar direction) -
    for rid, _t, _e, _n, bears in CITATIONS:
        edges.append({"node": rid, "target": bears, "rel": "bears-claim",
                      "axis": REL_MAP["bears-claim"]})

    # -- the thematic wire -------------------------------------------------
    for node, target, rel in THEMATIC_EDGES:
        edges.append({"node": node, "target": target, "rel": rel, "axis": REL_MAP[rel]})

    for e in edges:
        if e["node"] not in live or e["target"] not in live:
            raise CompileError(f"edge endpoint not built: {e['node']} -> {e['target']}")

    # -- the arc: THE_STORY's seven parts, in its own order (ruling R4) ----
    beats = []
    for (bid, handle), part in zip(BEATS, ctx["parts"]):
        beats.append({"node": bid,
                      "narrative": BEAT_NARRATIVE[bid],
                      "story_part": f"{part['n']}. {part['title']} ({handle})"})
    for b in beats:
        if b["node"] not in live:
            raise CompileError(f"arc beat names a node the compiler did not build: {b['node']}")

    n_total = 1 + len(nodes)
    if not 45 <= n_total <= 80:
        raise CompileError(f"graph size {n_total} outside the declared 45-80 band")

    # -- the privacy gate: no essence may be an elision of his paragraph ---
    check_no_story_prose(src, goal, nodes)

    # -- the edge census the price sidecar bills ---------------------------
    seen: dict[tuple[str, str, str], list[str]] = {}
    for e in edges:
        seen.setdefault((e["node"], e["target"], e["axis"]), []).append(e["rel"])
    distinct_edges = seen
    collapses = [f"{n} -> {t} [{'+'.join(sorted(rels))} -> {ax}]"
                 for (n, t, ax), rels in seen.items() if len(rels) > 1]
    collapses.sort()

    decl = {
        "corpus": PROJECT,
        "ts": TS,
        "_producer": PRODUCER,
        "_producer_note": (
            "DERIVED — do not hand-edit. Re-run the producer to rebuild, then "
            "`scripts/build_overlay_conceptric.py --project synthetics-definition`. Every ref, "
            "every epistemic_status and every census number below is located inside a banked "
            "root document at compile time; the node essences are authored short descriptions, "
            "gated at compile time against carrying verbatim runs of THE_STORY's prose "
            "(check_no_story_prose) — the graph refs his text, it never copies it."),
        "source": [STORY, CLAIMS, ANCHORS, GENESIS_LEDGER, f"{CARDS}/*.md",
                   OPEN_STACK, ATLAS_DESIGN, ATLAS_PHASE3, RULINGS],
        "rulings": RULINGS,
        "note": (
            "The DEFINITION of synthetics, poured through the encoded-doors path (R3). The "
            "campaign home stays synthetics-genesis and is referenced, never annexed (R2); its "
            "own deferred pour is untouched. Node ids carry the house prefixes so the substrate "
            "and projection-label gates bind non-vacuously (R7); kinds are real, so "
            "PROVENANCE_EXEMPT does not swallow the graph."),
        "kind_map": KIND_MAP,
        "rel_map": REL_MAP,
        "goal": goal,
        "nodes": nodes,
        "edges": edges,
        "arc": {"label": "THE_STORY's seven parts, in its own reading order (R4)",
                "beats": beats},
    }
    census_out = {
        "nodes": n_total,
        "edges": len(edges),
        # What the reader actually gets. The emitter keys an edge on (node, target, AXIS),
        # so two declared relations that rel_map sends to one axis arrive as ONE edge in the
        # served graph. The declared count is the honest count of what this compiler wrote;
        # the distinct count is the honest count of what the corpus serves, and the price
        # sidecar bills the second — a census that overstates the counting price is a defect
        # in exactly the artefact whose subject is the price of counting.
        "edges_distinct_axis": len(distinct_edges),
        "edge_relation_collapses": collapses,
        "beats": len(beats),
        "literature_refs": len(CITATIONS),
        "findings_graded": len(FINDINGS),
        "anchor_census": census,
        "cards": len(ctx["cards"]),
    }
    return decl, census_out


# ---------------------------------------------------------------------------
# the derived artefacts
# ---------------------------------------------------------------------------

def _json_bytes(doc: Any) -> str:
    return json.dumps(doc, indent=1, ensure_ascii=False) + "\n"


def prices_text(census: dict) -> str:
    """The price-pair sidecar (ruling R6): TWO typed prices, never summed, at file grade so
    the atlas exporter sweeps it. The recipe is provisional BY CONSTRUCTION — the exchange
    rate that would license comparing the two columns is this project's own open object."""
    schema = {
        "_": ("price-pair ledger for the synthetics-definition conceptric. TWO SEPARATELY "
              "TYPED PRICES, NEVER SUMMED: price_counting is a count of description elements "
              "(the typicality/counting currency, lambda-priced); price_authority is a count "
              "of imported outside warrant (the authority currency, beta-priced). Adding them "
              "would presuppose exactly the exchange rate this project records as underived "
              "(def:exchange-rate-open-problem). On-thesis for THIS project because its "
              "subject IS that exchange rate."),
        "kind": "schema",
        "price_recipe_version": "v0-provisional",
        "fields": {
            "price_counting": "object of integer counts of graph elements minted",
            "price_authority": "object of integer counts of imported-literature references",
        },
        "law": "never summed; never compared across the two columns without a derived beta/lambda",
        "ruling": f"R6 — {RULINGS}",
        "producer": PRODUCER,
    }
    birth = {
        "_": "the birth event: the price of bringing this conceptric into existence",
        "kind": "price",
        "event": "birth",
        "ts": TS,
        "price_recipe_version": "v0-provisional",
        "price_counting": {
            "nodes": census["nodes"],
            "edges": census["edges_distinct_axis"],
            "edges_declared": census["edges"],
            "edges_collapsed_by_axis": census["edge_relation_collapses"],
            "beats": census["beats"],
            "unit": ("graph elements the corpus SERVES. `edges` counts distinct "
                     "(node, target, axis) triples, which is what the emitter's edge index "
                     "holds; `edges_declared` counts the relations this compiler wrote. They "
                     "differ where two declared relations map to one axis — those pairs are "
                     "named above rather than quietly averaged away. Billing the declared "
                     "number would overstate the counting price of the build."),
        },
        "price_authority": {
            "imported_literature_refs": census["literature_refs"],
            "unit": "citation nodes for literature named outside this corpus",
        },
        "note": ("The recipe is PROVISIONAL: no derivation fixes what one imported reference "
                 "is worth in units of minted graph elements, and finding that number is this "
                 "project's own open problem. Until it exists the two columns are reported "
                 "side by side and never reconciled."),
        "producer": PRODUCER,
    }
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in (schema, birth))


def state_text(census: dict) -> str:
    """The run-state surface the registry manifest declares. It rides NO release ladder:
    this project has no manuscript, no release and no pour — and says so, rather than
    letting a second machine's vocabulary imply a run that never happened."""
    return _json_bytes({
        "project": PROJECT,
        "kind": "conceptric",
        "ladder": ("declaration — NOT the release ladder. This project has no manuscript "
                   "and no release; the conceptric IS the object. No `state` key is written "
                   "here on purpose: a release-ladder value would be a second, false "
                   "run-state home."),
        "phase": "DECLARED — the graph is built and served; no pour, no release, no loop",
        "built_from": [STORY, CLAIMS, ANCHORS, GENESIS_LEDGER, f"{CARDS}/*.md"],
        "census": census,
        "open_objects": [
            "def:exchange-rate-open-problem — the one missing equation (his item 2)",
            "def:conservation-charge-E — never scored on any lineage (his item 3)",
            "def:response-function-synthetics — N37, blocked on his pointer, untouched",
            "technique:atlas-joint-experiments — a spec, gated on atlas Phases 4-5 (absent)",
            "res:external-anchor-residue — the anchor prose now verifies 667/667; the "
            "commit provenance of the 75 local anchors does not, and this shallow clone "
            "cannot decide whether those commits were truncated or never pushed",
        ],
        "awaiting_author": ("R4 wording redline (the goal essence and the arc order), and a "
                            "display_name if he wants one — none is invented here"),
        "producer": PRODUCER,
    })


MAIN_TEX = """\
% Stub tex root for the DEFINITION conceptric (corpus 'synthetics-definition').
% The graph is authored entirely as friction records in
% corpus_friction/synthetics-definition.jsonl, re-emitted deterministically by
% scripts/build_overlay_conceptric.py from a declaration this project's own
% compiler derives (scripts/compile_synthetics_definition_overlay.py).
% This stub exists only so corpus_ingest.resolve_corpus accepts the corpus
% (it requires main.tex). No sections, no bibliography by design: there is no
% manuscript here, and inventing one would claim a pour that has not happened.
\\documentclass{article}
\\begin{document}
\\title{Synthetics, defined}
The definition lives in the conceptric, not in this tex.
\\end{document}
"""


ARTEFACTS = ("conceptric_overlay.json", "prices.jsonl", "STATE.json", "manuscript/main.tex")


def build(repo: Path) -> tuple[dict[str, str], dict]:
    decl, census = compile_declaration(repo)
    return {
        "conceptric_overlay.json": _json_bytes(decl),
        "prices.jsonl": prices_text(census),
        "STATE.json": state_text(census),
        "manuscript/main.tex": MAIN_TEX,
    }, census


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--check", action="store_true",
                    help="verify the on-disk artefacts already equal a fresh compile")
    args = ap.parse_args()
    repo = Path(args.repo_root).resolve()

    try:
        texts, census = build(repo)
    except CompileError as e:
        print(f"COMPILE: {e}", file=sys.stderr)
        return 2

    base = repo / PROJECT_DIR
    if args.check:
        drift = [rel for rel in ARTEFACTS
                 if not (base / rel).is_file()
                 or (base / rel).read_text(encoding="utf-8") != texts[rel]]
        if drift:
            print(f"DRIFT: {drift} != a fresh compile (re-run without --check)", file=sys.stderr)
            return 1
        print(f"byte-stable: {len(ARTEFACTS)} artefacts under {PROJECT_DIR} match a fresh compile")
        print(json.dumps(census, indent=2))
        return 0

    for rel, text in texts.items():
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {PROJECT_DIR}/{rel}")
    print(json.dumps(census, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
