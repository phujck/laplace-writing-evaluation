"""scaffold_wipe — verify the erasure (Phase B, the conjugate of the emit boundary).

Gerard's organising principle: *the final step of projection is wiping away the
scaffolding required to build the object.* The generating questions, evidence
classes, provenance stamps, parallel legacy notation and pure-intermediate
numbering are load-bearing while the manuscript is built and meaningless artefacts
in the finished object. So, per surface:

    the SUBSTRATE keeps the scaffold · the OBJECT erases it at emit · the
    CHECKLIST verifies the erasure.

The emit-boundary erasures live where each surface is produced — ``figstyle.save``
scrubs the figure type-tag stamps, ``tex_backend.render_figure_env`` reduces the
caption. THIS module is the conjugate: it detects construction scaffold that
leaked into the rendered ``.tex`` — the mechanical peer of ``verify.check_meta_leak``
generalised across surfaces.

Each pass returns a list of findings, every finding a dict::

    {"where": <section/label/anchor>, "quote": <the offending text>,
     "issue": <what leaked>, "fix": <the erasure>, "kind": <finding class>}

``kind`` names the finding class; :data:`FINDING_KIND_STAGE` maps every kind to
its owning stage (the Phase-F routing manifest). The passes REUSE the Phase-A
substrate (``graph.CanonGraph.from_manuscript`` / ``graph._gather_manuscript_text``)
and the existing gates (``verify.check_meta_leak``, ``verify.check_glossary``'s
deprecated-vocabulary set) BY IMPORT — none of them is edited here. Where a pass
genuinely wants a core gate widened, it does the extra work locally and declares
the desired central wiring in :func:`core_extension_flags`.
"""
from __future__ import annotations

import re
from typing import Any

from laplace.pipeline.graph import CLAIM_LABEL_PREFIXES, CanonGraph, _gather_manuscript_text

# ---------------------------------------------------------------------------
# The finding-kinds manifest — every kind → its owning stage (Phase F routing).
# Stage names are the WORK_TO_LAYER vocabulary in ``pipeline.schema``.
# ---------------------------------------------------------------------------
FINDING_KIND_STAGE: dict[str, dict[str, Any]] = {
    # surface           primary owning stage   (all stages a leak touches)
    "figure-debris":    {"primary": "figures",    "stages": ["figures"]},
    "caption-scaffold": {"primary": "figures",    "stages": ["figures", "prose"]},
    "prose-scaffold":   {"primary": "prose",      "stages": ["prose"]},
    "legacy-notation":  {"primary": "projection", "stages": ["projection"]},
    "citation-cluster": {"primary": "prose",      "stages": ["prose"]},
    "legacy-term":      {"primary": "projection", "stages": ["projection"]},
    "matter-scaffold":  {"primary": "narrative",  "stages": ["narrative", "prose"]},
}

# node-id references (def:foo, eq:bar) are PROVENANCE, not usage — mirrors the
# ``_id_re`` inside ``verify.check_glossary`` so a retired term named as a node id
# never trips a usage gate.
_ID_RE = re.compile(
    r"\b(?:def|irf|res|thm|ds|fig|ref|sup|goal|fork|flag|eq):[A-Za-z0-9_\-]+")

_SECTION_RE = re.compile(r"\\(?:sub)?section\*?\{([^}]+)\}")
_SECTION_TOP_RE = re.compile(r"\\section\*?\{([^}]+)\}")
_CITE_RE = re.compile(r"\\cite[tp]?\*?(?:\[[^\]]*\])?\{([^}]*)\}")


# ---------------------------------------------------------------------------
# small shared helpers
# ---------------------------------------------------------------------------
def _section_at(text: str, pos: int) -> str:
    """The heading of the section the character offset ``pos`` sits under."""
    title = None
    for m in _SECTION_RE.finditer(text):
        if m.start() > pos:
            break
        title = m.group(1)
    return title or "(front-matter)"


def _span_snippet(text: str, start: int, end: int, pad: int = 60) -> str:
    a = max(0, start - pad)
    b = min(len(text), end + pad)
    s = " ".join(text[a:b].split())
    return ("…" if a > 0 else "") + s + ("…" if b < len(text) else "")


def _merged_hits(text: str, regex: re.Pattern, gap: int = 40) -> list[tuple[int, int]]:
    """Match spans, with near-adjacent spans (within ``gap`` chars) merged, so a
    class whose alternations both fire on one sentence yields ONE finding."""
    spans = sorted((m.start(), m.end()) for m in regex.finditer(text))
    out: list[list[int]] = []
    for s, e in spans:
        if out and s <= out[-1][1] + gap:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [(s, e) for s, e in out]


def _iter_paragraphs(text: str):
    """(offset, paragraph) over blank-line-separated blocks, offsets preserved."""
    last = 0
    for m in re.finditer(r"\n[ \t]*\n", text):
        yield last, text[last:m.start()]
        last = m.end()
    yield last, text[last:]


def _caption_bodies(text: str) -> list[tuple[int, str]]:
    """(offset, body) for every ``\\caption{...}``, brace-matched so nested math
    (``\\sqrt{\\tau}``, ``e^{-\\tau}``) is captured whole."""
    out: list[tuple[int, str]] = []
    key = r"\caption{"
    i = 0
    while True:
        j = text.find(key, i)
        if j == -1:
            break
        open_idx = j + len(key) - 1        # the '{'
        depth = 0
        k = open_idx
        for k in range(open_idx, len(text)):
            c = text[k]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    out.append((j, text[open_idx + 1:k]))
                    break
        i = k + 1
    return out


def _first_section_body(text: str):
    ms = list(_SECTION_TOP_RE.finditer(text))
    if not ms:
        return None
    end = ms[1].start() if len(ms) > 1 else len(text)
    return ms[0].start(), text[ms[0].end():end]


# ---------------------------------------------------------------------------
# B1 — prose scaffold (reuse check_meta_leak + the internal-planning-object classes)
# ---------------------------------------------------------------------------
#: The classes the plan names that ``check_meta_leak`` does not yet cover. DATA,
#: like ``schema.META_LEAK_PATTERNS`` — the desired central home is flagged in
#: :func:`core_extension_flags`, not edited into the registry here.
_PLANNING_OBJECT_PATTERNS: dict[str, tuple[str, ...]] = {
    # section contracts / reader-state bookkeeping
    "contract": (
        r"\bsection contract\b", r"\breader (?:entry|exit) state\b",
        r"\b(?:entry|exit) state\b", r"\bpermitted recap\b",
        r"\bon entry,? the reader\b", r"\bforward use[sd]?\b",
    ),
    # evidence ledgers / claim taxonomies surfaced as prose
    "evidence-ledger": (
        r"\bevidence (?:class|ledger)\b", r"\btyped by evidence\b",
        r"\bexactness class\b", r"\bresult ledger\b", r"\bepistemic (?:status|ledger)\b",
        r"\bclassification of (?:every|each)\b[^.]{0,40}\bstatement\b",
        r"\bstatements?\b[^.]{0,20}\bare typed\b",
    ),
    # document-management notes
    "doc-management": (
        r"\bTODO\b", r"\bFIXME\b", r"\bXXX\b", r"\bplaceholder\b",
        r"\bto be (?:written|added|filled(?: in)?|completed|drafted)\b",
        r"\bdraft note\b", r"\[(?:ref|cite|fig|todo)[^\]]*\]",
    ),
    # "explicit about what's new" — novelty narration
    "novelty-narration": (
        r"\bexplicit about what(?:'s| is) new\b",
        r"\bto be (?:clear|explicit) about (?:our |the )?(?:novelty|contribution|what is new)\b",
        r"\bwhat is new here\b", r"\bwe (?:now )?(?:state|make explicit) what is new\b",
    ),
    # narrator interpreting the manuscript's own honesty / importance / caution
    "self-narration": (
        r"\bwe are (?:being )?(?:careful|honest|cautious|modest)\b",
        r"\bthis (?:paper|manuscript|section|work) is (?:careful|honest|modest|deliberately \w+)\b",
        r"\bwe want to be (?:clear|honest|careful|explicit)\b",
        r"\bin all honesty\b", r"\bto be honest\b",
        r"\bwe (?:stress|caution) (?:that|the)\b", r"\bthe honest (?:answer|boundary|claim)\b",
    ),
}
_PLANNING_FIX = {
    "contract": "the section contract is substrate; the prose enacts it, it does not recite it",
    "evidence-ledger": "let each claim carry its own qualification in place; drop the ledger vocabulary",
    "doc-management": "resolve or remove the note — it is a build artefact, not prose",
    "novelty-narration": "state the new result; do not announce that it is new",
    "self-narration": "exhibit the care in the claim itself; do not narrate the manuscript's honesty",
}


def check_prose_scaffold(target, project: str | None = None) -> list[dict]:
    """B1. The existing meta_leak gate (reused by import) PLUS the internal
    planning-object classes: contracts, evidence ledgers, claim taxonomies,
    doc-management notes, novelty narration, and the narrator interpreting the
    manuscript's own honesty/importance/caution."""
    findings: list[dict] = []
    if project:
        try:
            from laplace.pipeline.verify import check_meta_leak
            ml = check_meta_leak(project)
            for h in ml.get("hits", []) or []:
                where = h.get("file", "")
                if h.get("line"):
                    where = f"{where}:{h['line']}"
                findings.append({
                    "where": where or "(compiled tex)",
                    "quote": h.get("match", ""),
                    "issue": f"meta-leak ({h.get('class', 'policy')}): construction "
                             f"vocabulary surfaced in prose",
                    "fix": "remove the meta-instruction; the object states, it never narrates itself",
                    "kind": "prose-scaffold",
                })
        except Exception:
            pass  # gate unavailable (no compiled tex dir) — the extra scan still runs
    text = _gather_manuscript_text(target)
    for cls, pats in _PLANNING_OBJECT_PATTERNS.items():
        rx = re.compile("|".join(pats), re.IGNORECASE)
        for s, e in _merged_hits(text, rx):
            findings.append({
                "where": _section_at(text, s),
                "quote": _span_snippet(text, s, e),
                "issue": f"prose-scaffold ({cls}): internal planning object surfaced in prose",
                "fix": _PLANNING_FIX[cls],
                "kind": "prose-scaffold",
            })
    return findings


# ---------------------------------------------------------------------------
# B2 conjugate — caption scaffold (reuse tex_backend's ONE caption reducer)
# ---------------------------------------------------------------------------
def check_caption_scaffold(target) -> list[dict]:
    """B3 conjugate. A rendered ``\\caption`` should already be the reader-facing
    reduction. Run the SAME reducer ``tex_backend`` uses at emit; if it would move
    a Q3 claim-support sentence to the body or park surplus Q4 non-claims, that
    scaffold leaked into the object."""
    from laplace.pipeline.tex_backend import _reduce_caption
    findings: list[dict] = []
    text = _gather_manuscript_text(target)
    for pos, body in _caption_bodies(text):
        red = _reduce_caption(body)
        where = _section_at(text, pos)
        for s in red["to_body"]:
            findings.append({
                "where": where, "quote": s.strip()[:180],
                "issue": "caption carries Q3 claim-support scaffold — belongs in the body prose",
                "fix": "move the 'supports the claim' sentence to the prose that discusses the figure",
                "kind": "caption-scaffold",
            })
        for s in red["to_metadata"]:
            findings.append({
                "where": where, "quote": s.strip()[:180],
                "issue": "caption carries surplus Q4 non-claim scaffold beyond one qualification",
                "fix": "keep at most one qualification in the caption; the rest is metadata",
                "kind": "caption-scaffold",
            })
    return findings


# ---------------------------------------------------------------------------
# B4 — equation scaffold (Phase-A equation nodes + reading order)
# ---------------------------------------------------------------------------
_LEGACY_NOTATION_RE = re.compile(
    r"\bformerly (?:denoted|written|called|known as)\b"
    r"|\bpreviously (?:denoted|written|called)\b"
    r"|\bin the (?:old|older|legacy|former|previous|v\d) notation\b"
    r"|\bwe (?:used to|previously) (?:call|denote|write)\b"
    r"|\bthe (?:parent|legacy|original|former) (?:\w+ )?(?:convention|notation)\b"
    r"|\brenamed from\b|\bwhat was (?:previously |formerly )?(?:called|denoted)\b",
    re.IGNORECASE)


def check_equation_scaffold(target) -> list[dict]:
    """B4. Numbering that exists only to break prose — a numbered display
    equation that is NOT a named result (bare ``eq:``) and is never ``\\ref``/
    ``\\eqref``'d — plus parallel legacy notation kept after translation. Uses the
    Phase-A ``CanonGraph.from_manuscript`` equation nodes."""
    findings: list[dict] = []
    g = CanonGraph.from_manuscript(target)
    referenced = {e.dst for e in g.edges if e.rel == "references"}
    container: dict[str, str] = {}
    for e in g.edges:
        if e.rel == "contains":
            container.setdefault(e.dst, e.src)
    for nid, n in g.nodes.items():
        if n.kind != "equation":
            continue
        label = n.meta.get("label", "") or ""
        if label.startswith(CLAIM_LABEL_PREFIXES):
            continue                       # a named result (def/res/irf/thm) earns its number
        if nid not in referenced:
            findings.append({
                "where": container.get(nid, "?"),
                "quote": label,
                "issue": "numbered equation is never \\ref/\\eqref'd — numbering that exists "
                         "only to break prose",
                "fix": "unnumber it (\\[...\\] or a starred env), fold it into the sentence, "
                       "or wire an \\eqref",
                "kind": "legacy-notation",
            })
    text = _gather_manuscript_text(target)
    for s, e in _merged_hits(text, _LEGACY_NOTATION_RE):
        findings.append({
            "where": _section_at(text, s),
            "quote": _span_snippet(text, s, e),
            "issue": "parallel legacy notation kept after translation",
            "fix": "translate fully to the settled notation; keep at most one explicit bridge, "
                   "confined to metadata",
            "kind": "legacy-notation",
        })
    return findings


# ---------------------------------------------------------------------------
# B5 — citation scaffold (cite-everything clusters, self-citation-as-substitute)
# ---------------------------------------------------------------------------
_SELFCITE_RE = re.compile(
    r"\b(?:our|my|the present authors['’]?|the authors['’]?)\s+"
    r"(?:previous|earlier|prior|recent|own|companion|forthcoming)\s+"
    r"(?:work|paper|study|analysis|results?|manuscript|preprint)\b"
    r"|\bas we (?:showed|proved|demonstrated|argued|established|reported) (?:in|elsewhere)\b"
    r"|\bin (?:our|a companion) (?:previous |earlier |prior |recent |companion )?"
    r"(?:work|paper|study)\b",
    re.IGNORECASE)


def check_citation_scaffold(target) -> list[dict]:
    """B5. Ambiguous end-of-paragraph 'cite-everything' clusters (a single
    ``\\cite`` with many keys, or a pile-up at the paragraph tail) and
    self-citation standing in for the argument."""
    findings: list[dict] = []
    text = _gather_manuscript_text(target)
    for start, para in _iter_paragraphs(text):
        for cm in _CITE_RE.finditer(para):
            keys = [k for k in cm.group(1).split(",") if k.strip()]
            if len(keys) >= 4:
                findings.append({
                    "where": _section_at(text, start + cm.start()),
                    "quote": _span_snippet(para, cm.start(), cm.end()),
                    "issue": f"cite-everything cluster ({len(keys)} keys in one \\cite) — "
                             f"ambiguous which source grounds which point",
                    "fix": "split the cluster so each cite sits by the specific point it grounds",
                    "kind": "citation-cluster",
                })
        tail = para[-180:]
        tail_cites = list(_CITE_RE.finditer(tail))
        if len(tail_cites) >= 3:
            findings.append({
                "where": _section_at(text, start),
                "quote": "…" + " ".join(tail.split())[-140:],
                "issue": f"end-of-paragraph citation pile-up ({len(tail_cites)} \\cite at "
                         f"the paragraph tail)",
                "fix": "attribute each source in-text where its point is made, not as a terminal dump",
                "kind": "citation-cluster",
            })
        for sm in _SELFCITE_RE.finditer(para):
            near = para[max(0, sm.start() - 50):sm.end() + 100]
            if _CITE_RE.search(near):
                findings.append({
                    "where": _section_at(text, start + sm.start()),
                    "quote": _span_snippet(para, sm.start(), sm.end()),
                    "issue": "self-citation standing in for the argument ('our previous work' + \\cite)",
                    "fix": "state the borrowed result and cite it; do not let the citation "
                           "replace the claim",
                    "kind": "citation-cluster",
                })
    return findings


# ---------------------------------------------------------------------------
# B6 — legacy terminology (reuse check_glossary's deprecated-vocabulary set)
# ---------------------------------------------------------------------------
def _deprecated_vocabulary(corpus_name: str | None) -> dict[str, str]:
    """The deprecated-alias → owning-def map, from the one public accessor
    ``verify.deprecated_vocabulary`` (Phase F folded B6's flagged core extension in,
    2026-07-09): the conceptric glossary gate and this rendered-prose scan now share
    one definition instead of each rebuilding it."""
    if not corpus_name:
        return {}
    try:
        from laplace.pipeline.verify import deprecated_vocabulary
    except Exception:
        return {}
    return deprecated_vocabulary(corpus_name)


def _alias_re(dep: str) -> re.Pattern:
    words = [re.escape(w) for w in dep.split() if w]
    body = r"[\s\-]+".join(words)
    return re.compile(r"\b" + body + r"(?:e?s|ies)?\b", re.IGNORECASE)


def _blank_ids(text: str) -> str:
    """Blank node-id spans to equal-length whitespace so a retired term named as a
    node id (``def:spectral-surfacing``) is provenance, not a usage hit — while
    every other character keeps its offset for section attribution."""
    return _ID_RE.sub(lambda m: " " * len(m.group(0)), text)


def check_legacy_terms(target, corpus_name: str | None = None,
                       report: dict | None = None) -> list[dict]:
    """B6. The deprecated-vocabulary set from ``check_glossary`` (imported),
    extended from the conceptric essences to the RENDERED prose: any retired
    legacy term surviving in the ``.tex``.

    When ``corpus_name`` is given but the vocabulary comes back empty (the accessor
    raised, or the corpus carries no deprecated terms), the scan ran against an
    EMPTY vocabulary — a zero-finding result then certifies nothing. ``report``, if
    passed, receives ``vocab_unavailable`` so the caller surfaces that instead of
    reading the empty result as clean."""
    findings: list[dict] = []
    deprecated = _deprecated_vocabulary(corpus_name)
    if report is not None:
        report["vocab_unavailable"] = bool(corpus_name) and not deprecated
    if not deprecated:
        return findings
    text = _gather_manuscript_text(target)
    scan = _blank_ids(text)                 # offsets preserved (equal-length blanks)
    for dep, owner in deprecated.items():
        rx = _alias_re(dep)
        for s, e in _merged_hits(scan, rx, gap=0):
            findings.append({
                "where": _section_at(text, s),
                "quote": _span_snippet(text, s, e),
                "issue": f"deprecated legacy term '{dep}' surviving in rendered prose "
                         f"(canonical: {owner})",
                "fix": f"translate to the term of art owned by {owner}",
                "kind": "legacy-term",
            })
    return findings


# ---------------------------------------------------------------------------
# B7 — front/back matter (abstract roadmap · intro ledger · orphan appendix)
# ---------------------------------------------------------------------------
_ROADMAP_RE = re.compile(
    r"\bin (?:section|sec\.?)~?\s*\\?ref\b|\bsection~?\\ref\b"
    r"|\bthis (?:paper|manuscript|article) is organi[sz]ed\b"
    r"|\bthe (?:paper|remainder|rest) (?:proceeds|is (?:structured|organi[sz]ed))\b"
    r"|\bwe (?:begin|start) by\b|\bwe (?:then|next) (?:turn|proceed|show|derive)\b"
    r"|\bfirst,? we\b[^.]{0,80}\bthen,? we\b",
    re.IGNORECASE)
_LEDGER_RE = re.compile(
    r"\bevidence (?:class|ledger)\b|\btyped by evidence\b|\bexactness class\b"
    r"|\bresult ledger\b|\bepistemic ledger\b"
    r"|\bclassification of (?:every|each)\b[^.]{0,40}\bstatement\b",
    re.IGNORECASE)
_APP_SECTION_RE = re.compile(
    r"\\(?:sub)?section\*?\{([^}]+)\}(?:\s*\\label\{([^}]+)\})?")
_REFS_TO = r"\\(?:ref|autoref|cref|Cref|pageref|eqref)\{{{lab}\}}"


def check_matter_scaffold(target) -> list[dict]:
    """B7. Abstract-as-roadmap, intro-as-evidence-ledger, and appendix-as-
    dumping-ground (an appendix section the body never references)."""
    findings: list[dict] = []
    text = _gather_manuscript_text(target)

    am = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", text,
                   re.DOTALL | re.IGNORECASE)
    if am:
        abody = am.group(1)
        for s, e in _merged_hits(abody, _ROADMAP_RE):
            findings.append({
                "where": "abstract",
                "quote": _span_snippet(abody, s, e),
                "issue": "section-by-section roadmap in the abstract — the construction map, not the result",
                "fix": "the abstract states the result; the reading map belongs to the intro's "
                       "last move at most",
                "kind": "matter-scaffold",
            })

    intro = _first_section_body(text)
    if intro:
        istart, ibody = intro
        for s, e in _merged_hits(ibody, _LEDGER_RE):
            findings.append({
                "where": _section_at(text, istart),
                "quote": _span_snippet(ibody, s, e),
                "issue": "evidence-ledger bookkeeping surfaced in the introduction",
                "fix": "the evidence typing is substrate; let each claim carry its own "
                       "qualification in place",
                "kind": "matter-scaffold",
            })

    ap = text.find(r"\appendix")
    if ap != -1:
        appbody = text[ap:]
        for sm in _APP_SECTION_RE.finditer(appbody):
            lab = sm.group(2)
            if not lab:
                continue
            refs = re.findall(_REFS_TO.format(lab=re.escape(lab)), text)
            if not refs:
                findings.append({
                    "where": lab,
                    "quote": sm.group(1),
                    "issue": f"appendix '{sm.group(1)}' is never referenced from the body — "
                             f"appendix as dumping-ground",
                    "fix": "reference the appendix where the body needs it, or fold/cut its content",
                    "kind": "matter-scaffold",
                })
    return findings


# ---------------------------------------------------------------------------
# aggregate + the central-wiring flags
# ---------------------------------------------------------------------------
_PASSES = {
    "prose": check_prose_scaffold,
    "caption": check_caption_scaffold,
    "equation": check_equation_scaffold,
    "citation": check_citation_scaffold,
    "notation": check_legacy_terms,
    "matter": check_matter_scaffold,
}


def scaffold_wipe(target, project: str | None = None,
                  corpus_name: str | None = None) -> dict[str, Any]:
    """Run every verify-erasure pass over ``target`` (a root ``.tex`` or a
    directory) and return the per-pass counts, the de-duplicated findings, the
    routing manifest, and the flagged core extensions."""
    notation_report: dict[str, Any] = {}
    passes: dict[str, list[dict]] = {
        "prose": check_prose_scaffold(target, project),
        "caption": check_caption_scaffold(target),
        "equation": check_equation_scaffold(target),
        "citation": check_citation_scaffold(target),
        "notation": check_legacy_terms(target, corpus_name, report=notation_report),
        "matter": check_matter_scaffold(target),
    }
    seen: set = set()
    flat: list[dict] = []
    for name, items in passes.items():
        for f in items:
            key = (f["where"], f.get("quote", ""), f["kind"], f["issue"])
            if key in seen:
                continue
            seen.add(key)
            f = dict(f, owning_stage=FINDING_KIND_STAGE[f["kind"]]["primary"], pass_=name)
            flat.append(f)
    return {
        "target": str(target),
        "pass": not flat,
        "n": len(flat),
        "counts": {k: len(v) for k, v in passes.items()},
        "findings": flat,
        "manifest": FINDING_KIND_STAGE,
        "core_extensions": core_extension_flags(),
        "vocab_unavailable": notation_report.get("vocab_unavailable", False),
    }


def core_extension_flags() -> list[dict]:
    """Desired central wiring for Phase F — declared, never applied here (verify.py
    / schema.py registries are not edited by this module)."""
    return [
        {
            "target": "schema.META_LEAK_PATTERNS",
            "extension": "add classes 'planning-object' and 'self-narration'",
            "reason": "B1 covers internal-planning-object + narrator-honesty scaffold that "
                      "check_meta_leak does not. The patterns live in "
                      "scaffold_wipe._PLANNING_OBJECT_PATTERNS and are pure data, ready to fold "
                      "into the core lexicon with no gate-code change.",
        },
        {
            "target": "verify.deprecated_vocabulary(corpus_name)",
            "extension": "expose check_glossary's deprecated-alias set as a public function",
            "reason": "B6 rebuilds the deprecated map from _load_corpus_network, duplicating ~6 "
                      "lines inside check_glossary. A public accessor removes the duplication and "
                      "lets the conceptric gate and the rendered-prose scan share one source.",
        },
        {
            "target": "schema.KIND_TO_WORK / schema.WORK_TO_LAYER",
            "extension": "register the scaffold-wipe finding kinds",
            "reason": "figure-debris, caption-scaffold, prose-scaffold, legacy-notation, "
                      "citation-cluster, legacy-term and matter-scaffold must map to their owning "
                      "stages (see FINDING_KIND_STAGE) so routed findings do not raise at the door.",
        },
    ]
