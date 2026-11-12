"""final_layer — the RHETORICAL de-scaffolding wash (the last projection layer).

Gerard's organising principle, already the founding docstring of
:mod:`scaffold_wipe`: *the final step of projection is wiping away the scaffolding
required to build the object.* ``scaffold_wipe`` is the MECHANICAL peer — it catches
construction scaffold that leaked into the rendered ``.tex`` (evidence-class stamps,
provenance, parallel legacy notation, unreferenced numbering). THIS module is the
conjugate one level up: the RHETORICAL scaffold — the four voice registers a
manuscript grows while defending itself to an imagined referee, and the negative
framing that lets the EXCLUSIONS define the reader's idea of the paper.

It is the sibling of the VOICE WASH (:mod:`voice_retrieval`): that wash writes the
prose FROM the author's real sealed corpus and runs on HIS machine (it fails loud
without the ``corpus_stores/`` store); THIS wash is mechanical, needs no corpus, and runs
HERE. Both are gated END-STAGE layers, invoked only after the content converges.

The affirmative-hierarchy brief (his hold-out editorial review, 2026-07-10) names
four scaffolding voices to buff out, each by its phrase-signature:

  * REFEREE-RESPONSE — answering an imagined objection in the body ("does not
    establish", "no statement is made about", "neither establishes nor rules out",
    "not an estimator defect", "is not a lower bound", "no claim rests on"). Answer
    an objection at MOST once; repetition gives an imagined critic control of the
    prose.
  * AUDIT-REPORT — the machine-generated ledger voice ("Every numerical statement
    carries one of four evidence classes", "names the method behind it", "the figure
    supports one statement", "every supported statement carries exactly one
    category"). Useful in the annexes; in the body it reads generated.
  * DISCLOSURE — the patent-claim-chart voice ("input-output contract", "fixed by
    its contract", candidate-embodiments / exactness-taxonomies). Suits the
    disclosure appendix; "contract" earns ONE use in the body.
  * DEFENSIVE-COMPLEXITY — the cumulative "this is not a complexity result" register
    (entanglement-isn't-hardness, bond-growth-isn't-a-lower-bound, stoquasticity,
    growth-not-hardness, planted-isn't-advantage). Technically sharp; en masse it
    makes the paper read as though its purpose was complexity separation.

Plus two structural tells: the ABSTRACT negative-inventory (the trailing run of
absent-accomplishment clauses) and the SELF-DEMOTION (the §VII / conclusion final
paragraph that recasts the established architecture as a consolation prize —
"sensing-grade instrumentation ... makes no hardness or advantage claim").

Finally it applies the disclaimer-treatment table by REUSING the tic detector's
six-class disclaimer census (:mod:`tics`): each class has ONE canonical home; the
first hit there is kept, every other appearance is flagged surplus (keep-once-where /
remove-elsewhere). This is the mechanical driver of the de-duplication the RUN makes.

Each finding is a dict in ``scaffold_wipe``'s idiom::

    {"where": <section/label/anchor>, "quote": <the offending text>,
     "issue": <what leaked>, "fix": <the erasure>, "kind": <finding class>}

Read-only. It REUSES the substrate (``graph._gather_manuscript_text``), the section
map (``apparatus_common``), ``scaffold_wipe``'s span/caption helpers and ``tics``'s
disclaimer classes BY IMPORT — none of them is edited here.
"""
from __future__ import annotations

import re
from typing import Any

from laplace.pipeline.graph import _gather_manuscript_text
from laplace.pipeline import scaffold_wipe as _sw
from laplace.pipeline import tics as _tics
from laplace.pipeline.apparatus_common import section_of, section_spans

# ---------------------------------------------------------------------------
# the finding-kinds manifest — every kind -> its owning stage (mirrors
# scaffold_wipe.FINDING_KIND_STAGE; all rhetorical scaffold is prose-owned, the
# abstract inventory is a narrative-level reframe).
# ---------------------------------------------------------------------------
FINDING_KIND_STAGE: dict[str, dict[str, Any]] = {
    "referee-voice":               {"primary": "prose",     "stages": ["prose"]},
    "audit-voice":                 {"primary": "prose",     "stages": ["prose"]},
    "disclosure-voice":            {"primary": "prose",     "stages": ["prose"]},
    "defensive-complexity-voice":  {"primary": "prose",     "stages": ["prose"]},
    "abstract-negative-inventory": {"primary": "narrative", "stages": ["narrative", "prose"]},
    "self-demotion":               {"primary": "prose",     "stages": ["prose"]},
    "disclaimer-surplus":          {"primary": "prose",     "stages": ["prose"]},
}

# ---------------------------------------------------------------------------
# (A) the four scaffolding voice registers, by phrase-signature
# ---------------------------------------------------------------------------
#: register -> (compiled alternation, the fix idiom). Each pattern matches a
#: DEFENSIVE / SELF-NARRATING move, not a bare mention of the topic — so a single
#: substantive use never trips, only the register the review flagged.
VOICE_REGISTERS: dict[str, dict[str, Any]] = {
    "referee-voice": {
        "patterns": (
            r"\bdoes not establish\b", r"\bdo(?:es)? not settle\b",
            r"\bno statement is made about\b",
            r"\bneither establishes nor rules out\b",
            r"\bneither .{0,25} nor rules out\b",
            r"\bnot an? (?:estimator )?\w*\s?defect\b", r"\bnot a defect of the\b",
            r"\bshort of certification\b",
            r"\bno claim (?:rests|hangs) on\b", r"\bno .{0,20}claim rests\b",
            r"\bis not a lower bound\b", r"\bnot a lower bound on\b",
            r"\bestablishes? no(?:thing)?\b[^.]{0,40}(?:hardness|separation|"
            r"structural|law)",
            r"\bit does not establish\b", r"\bthe figure does not establish\b",
            r"\bpresent evidence neither\b",
        ),
        "fix": "answer the objection at most once, at its natural home in the "
               "limits section; state the achieved result affirmatively here",
    },
    "audit-voice": {
        "patterns": (
            r"\bevery numerical statement\b",
            r"\bcarries one of (?:four|the four|four evidence)\b",
            r"\bone of four evidence classes\b",
            r"\bnames the method behind it\b", r"\beach .{0,20}names the method\b",
            r"\bthe figure supports (?:one statement|the |a single)\b",
            r"\beach element receives one\b", r"\bfive-column row\b",
            r"\bevery supported statement carries\b",
            r"\bcarries exactly one (?:category|row|class)\b",
            r"\bevery statement that follows is typed\b",
        ),
        "fix": "the evidence typing is annex substrate; let each result carry its "
               "own qualification in place, lead the section with the finding",
    },
    "disclosure-voice": {
        "patterns": (
            r"\binput-output contract\b", r"\bfixed by its (?:input-output )?contract\b",
            r"\bcandidate[- ]embodiment", r"\bexactness taxonom",
            r"\belements?/conditions?\b", r"\bthe contract is\b",
            r"\bby (?:its|the) contract\b",
        ),
        "fix": "the disclosure genre belongs in the disclosure appendix; state the "
               "definition as physics, and use 'contract' at most once",
    },
    "defensive-complexity-voice": {
        "patterns": (
            r"\bentangling does not mean\b", r"\bentanglement (?:is|does) not\b",
            r"\bgrowth,? not hardness\b", r"\bdemonstrates growth, not hardness\b",
            r"\bnot (?:by itself )?a hardness (?:statement|claim|no-go|argument)\b",
            r"\bnot a lower bound on all classical\b",
            r"\bno quantum monte carlo hardness\b",
            r"\bhardness no-go\b", r"\bfinite-size compressibility is no\b",
            r"\bnever a hardness argument\b", r"\bmakes? no hardness\b",
            r"\bis no hardness no-go\b",
        ),
        "fix": "concentrate every global complexity boundary in the one limits "
               "section; do not re-fight the complexity objection per section",
    },
}
_VOICE_RX: dict[str, re.Pattern] = {
    name: re.compile("|".join(cfg["patterns"]), re.IGNORECASE)
    for name, cfg in VOICE_REGISTERS.items()
}


def check_voice_registers(target) -> list[dict]:
    """(A) The four scaffolding voice registers, each by its phrase-signature. Every
    hit is a de-scaffold candidate carrying the register kind and the idiomatic fix.
    Near-adjacent hits of one register merge into one finding (``_merged_hits``)."""
    findings: list[dict] = []
    text = _gather_manuscript_text(target)
    for name, rx in _VOICE_RX.items():
        fix = VOICE_REGISTERS[name]["fix"]
        for s, e in _sw._merged_hits(text, rx):
            findings.append({
                "where": _sw._section_at(text, s),
                "quote": _sw._span_snippet(text, s, e),
                "issue": f"{name}: rhetorical scaffold — the manuscript defends "
                         f"itself to an imagined referee instead of stating the result",
                "fix": fix,
                "kind": name,
            })
    return findings


# ---------------------------------------------------------------------------
# (B) the abstract negative-inventory — the trailing run of absent accomplishments
# ---------------------------------------------------------------------------
_ABSTRACT_RE = re.compile(r"\\begin\{abstract\}(.*?)\\end\{abstract\}",
                          re.DOTALL | re.IGNORECASE)
#: the negative-inventory openers: the point where an abstract stops stating what
#: the method DOES and starts listing what it does not do / has not demonstrated.
_NEG_INVENTORY_RE = re.compile(
    r"\basserts?\s+no\b|\bmakes?\s+no\b|\buses?\s+no\b|\bno\s+asymptotic\b"
    r"|\bno\s+quantum\s+(?:advantage|hardware)\b|\bneither\s+asymptotic\b"
    r"|\bnot\s+recoverable\b|\bproof[- ]of[- ]principle\b|\bshort\s+of\b"
    r"|\bchosen\s+for\s+checkability,?\s+not\b", re.IGNORECASE)


def check_abstract_inventory(target, *, min_clauses: int = 2) -> list[dict]:
    """(B) The abstract negative-inventory: the trailing run of scope / absent-
    accomplishment clauses that lets the exclusions define the reader's idea of the
    paper. Flagged when the abstract carries ``>= min_clauses`` negative-framing
    clauses; the fix is to rebuild the abstract around the affirmative hierarchy and
    keep at most one scope sentence."""
    findings: list[dict] = []
    text = _gather_manuscript_text(target)
    m = _ABSTRACT_RE.search(text)
    if not m:
        return findings
    abody = m.group(1)
    hits = list(_NEG_INVENTORY_RE.finditer(abody))
    if len(hits) >= min_clauses:
        first = hits[0].start()
        findings.append({
            "where": "abstract",
            "quote": _sw._span_snippet(abody, first, hits[-1].end(), pad=20),
            "issue": f"abstract-negative-inventory: {len(hits)} absent-accomplishment "
                     f"clauses close the abstract — the exclusions define the paper",
            "fix": "rebuild the abstract around the affirmative hierarchy (capability, "
                   "reuse, surface, responses, costed domain, controlled validation); "
                   "keep at most one scope sentence",
            "kind": "abstract-negative-inventory",
        })
    return findings


# ---------------------------------------------------------------------------
# (C) the §VII / conclusion self-demotion
# ---------------------------------------------------------------------------
_SELF_DEMOTION_RE = re.compile(
    r"\bsensing-grade instrumentation\b"
    r"|\bclaims? sensing-grade\b"
    r"|\bmakes? no hardness or advantage claim\b"
    r"|\bthis paper claims\b[^.]{0,80}\b(?:makes? no|no hardness)\b"
    r"|\bconsolation\b",
    re.IGNORECASE)


def check_self_demotion(target) -> list[dict]:
    """(C) The self-demotion: the interpretation / conclusion sentence that recasts
    the established general architecture as a consolation prize ("this paper claims
    sensing-grade instrumentation ... and it makes no hardness or advantage claim").
    The fix distinguishes the established architecture from the benchmark-specific
    diagnostics and the exploratory complexity extension, and states the open
    problem WITHOUT letting it redefine the achievement."""
    findings: list[dict] = []
    text = _gather_manuscript_text(target)
    for s, e in _sw._merged_hits(text, _SELF_DEMOTION_RE, gap=80):
        findings.append({
            "where": _sw._section_at(text, s),
            "quote": _sw._span_snippet(text, s, e),
            "issue": "self-demotion: the established architecture is recast as a "
                     "consolation prize, letting the open complexity question "
                     "redefine the achievement",
            "fix": "distinguish the established architecture, the benchmark-specific "
                   "diagnostics and the exploratory extension; end on the capability, "
                   "state the open question without demoting the result",
            "kind": "self-demotion",
        })
    return findings


# ---------------------------------------------------------------------------
# (D) the disclaimer-treatment table — keep-once-where / remove-elsewhere
# ---------------------------------------------------------------------------
#: each disclaimer class (the six ``tics`` classes) -> its ONE canonical home
#: section slug (his disclaimer-treatment table). The first hit inside the home is
#: KEPT; every other appearance is flagged surplus. A class whose home never fires
#: keeps its first hit in reading order (so the boundary is stated once, somewhere).
CANONICAL_HOME: dict[str, str] = {
    "no-hardness":                 "limits_and_discussion",           # §VII full analysis
    "no-advantage":                "limits_and_discussion",           # §VII full analysis
    "no-hardware":                 "data_availability_and_machine_manifest",
    "exact-vs-finite-size":        "introduction",                    # notation/derivation
    "guide-not-law":               "limits_and_discussion",           # §VII + beside the guide
    "reference-not-certification": "numerical_validation",            # define validation once
}
#: sections that are LEGITIMATE annex homes for the audit / disclosure / boundary
#: voice — a surplus disclaimer here is tolerated (the annex genre owns it), so the
#: keep-once pass does not flag appendix repetition.
_ANNEX_SLUGS = frozenset({
    "derivations",
    "data_availability_and_machine_manifest",
    "disclosure_crosswalk_and_exactness_taxonomy",
})


def check_disclaimer_treatment(target) -> list[dict]:
    """(D) The disclaimer-treatment table applied mechanically. REUSES the tic
    detector's six-class disclaimer census (``tics.disclaimer_hits``); for each
    class keeps the first hit in its :data:`CANONICAL_HOME` (or the first hit in
    reading order if the home never fires) and flags every OTHER body appearance as
    surplus. Appearances inside an annex (:data:`_ANNEX_SLUGS`) are tolerated — the
    annex genre legitimately restates boundaries. One ``disclaimer-surplus`` finding
    per surplus appearance, carrying the class, the section and the kept location."""
    findings: list[dict] = []
    full = _gather_manuscript_text(target)
    census = _tics.disclaimer_hits(full)      # class -> [{pos, section, quote}]
    for cls, hits in census.items():
        if not hits:
            continue
        hits = sorted(hits, key=lambda h: h["pos"])
        home = CANONICAL_HOME.get(cls)
        kept = next((h for h in hits if h["section"] == home), hits[0])
        for h in hits:
            if h is kept:
                continue
            if h["section"] in _ANNEX_SLUGS:
                continue                       # annex restatement is tolerated
            findings.append({
                "where": h["section"] or "(front-matter)",
                "quote": h["quote"],
                "issue": f"disclaimer-surplus ('{cls}'): the boundary is restated "
                         f"away from its canonical home ({kept['section'] or home})",
                "fix": f"remove here; keep the '{cls}' boundary once, at "
                       f"{home!r} (the disclaimer-treatment table)",
                "kind": "disclaimer-surplus",
                "cls": cls,
                "kept_at": kept["section"],
            })
    return findings


# ---------------------------------------------------------------------------
# aggregate + the census (before/after driver)
# ---------------------------------------------------------------------------
_PASSES = {
    "voice": check_voice_registers,
    "abstract": check_abstract_inventory,
    "demotion": check_self_demotion,
    "disclaimer": check_disclaimer_treatment,
}


def disclaimer_census(target) -> dict[str, Any]:
    """The six-class disclaimer census (count + sections per class + total) — the
    before/after measurement the RUN reports against. A thin affirmative view over
    ``tics.disclaimer_hits``; the target is roughly HALF the pre-wash count."""
    full = _gather_manuscript_text(target)
    hits = _tics.disclaimer_hits(full)
    by_class = {cls: {"count": len(hs),
                      "sections": sorted({h["section"] for h in hs if h["section"]})}
                for cls, hs in hits.items()}
    return {"by_class": by_class,
            "total": sum(v["count"] for v in by_class.values())}


def final_layer(target, *, min_abstract_clauses: int = 2) -> dict[str, Any]:
    """Run every rhetorical-scaffold pass over ``target`` (a root ``.tex`` or a
    directory) and return per-pass counts, the de-duplicated findings, the disclaimer
    census (the before/after driver), the routing manifest and the canonical-home
    map. Read-only: this is the DETECTOR; the RUN (the prose edit) is the eraser.

    The optional END-STAGE organ (his brief): the conjugate of ``scaffold_wipe`` one
    level up — the RHETORICAL scaffold, the four defensive voices, the abstract
    negative-inventory, the self-demotion, and the disclaimer-treatment table."""
    passes: dict[str, list[dict]] = {
        "voice": check_voice_registers(target),
        "abstract": check_abstract_inventory(target, min_clauses=min_abstract_clauses),
        "demotion": check_self_demotion(target),
        "disclaimer": check_disclaimer_treatment(target),
    }
    seen: set = set()
    flat: list[dict] = []
    for name, items in passes.items():
        for f in items:
            key = (f["where"], f.get("quote", ""), f["kind"], f["issue"])
            if key in seen:
                continue
            seen.add(key)
            f = dict(f, owning_stage=FINDING_KIND_STAGE[f["kind"]]["primary"],
                     pass_=name)
            flat.append(f)
    return {
        "target": str(target),
        "pass": not flat,
        "n": len(flat),
        "counts": {k: len(v) for k, v in passes.items()},
        "findings": flat,
        "census": disclaimer_census(target),
        "manifest": FINDING_KIND_STAGE,
        "canonical_home": CANONICAL_HOME,
    }
