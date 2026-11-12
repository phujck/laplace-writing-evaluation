"""The GAP LEDGER + research-intent typing — code beside :mod:`evolution_consumer`
(ARMING_2026-07-16, ROUND 3 STOCK: *growth is steered by a GAP LEDGER, aimed at the
SPINE, gated by HIS REGISTER — never free invention*).

The ledger compiles TYPED GAPS mechanically from two sources — the reader/panel
FINDINGS (promise-absent, source-delta, referee, orphan kinds) and the CONCEPTRIC
DIAGNOSTICS (spine-drift thin beats, def-orphans) — and types each into one of the
four gap classes the arming names:

* ``ungrounded``      — a prose claim with no arguing node (the argumentative
                        substrate is missing: source-delta losses, naked reliances).
* ``thin``            — a beat with an empty ``argues-in`` lane (``spine_drift``
                        already computes these), or a claim judged insufficient.
* ``orphaned``        — the def-orphans: a node/float connected to nothing that must
                        be connected or killed.
* ``evidence-shaped`` — a claim needing a figure/derivation that does not exist
                        (his predicted basin — NAMED when the grower cannot fill it).

The substrate-absent branch (his final question, banked): a gap whose QUARRY
retrieval — the nearest un-mined source-corpus spans — falls below the COSINE FLOOR
re-types as a RESEARCH INTENT, never faked growth. Three classes, three doors:

* ``literature``  — directed external retrieval (the citation-direction organ):
                    ungrounded/citation gaps whose grounding is a missing REFERENCE.
* ``computation`` — a banked computation work-order (the evidence organs): an
                    evidence-shaped gap whose missing substrate is a FIGURE/number.
* ``novel``       — a dispatched derivation attempt landing as a CONJECTURE-TIER
                    node: an ungrounded/thin gap the quarry cannot ground and that
                    is neither a citation nor a computation — genuinely new result.

Ranking: SPINE-CRITICALITY first (a gap on a spine beat outranks one off it),
then reader severity, then his prior rulings — LIVE from ``proxy_verdicts.jsonl``
via :func:`ruling_recall.rulings_boost`, passed by the durable caller
(``detector_organs.run_detector_organs``) and banked in the round evidence under
``gap_ledger.prior_rulings``; capped per round (top N — directed pressure, not a
ballooning agenda). THE METRIC the trajectory reads: gap CLOSURE
rate vs DISCOVERY rate per round — a gap that recurs unclosed names either a grower
failure or a missing organ (his prediction becoming data).

This module is PURE READS + typed intent construction. It never applies. Banking
is through the EXISTING gate: :func:`to_conceptric_intents` emits records in the
:func:`adjudicate.make_conceptric_intent` shape (``status: "open"``, queued, never
executed), and research-intent records carry the substrate class + the epistemic
provenance the arming's LAW demands (*epistemic provenance travels with
substrate*). The unclosable-gap ledger IS the research agenda.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Optional

# --- the four gap classes + the finding-kind -> gap-class map -----------------
GAP_CLASSES = ("ungrounded", "thin", "orphaned", "evidence-shaped")

#: which finding kinds compile into which gap class. Unlisted kinds do NOT become
#: gaps (a typography finding is fix-work, not a substrate gap). The map is DATA so
#: a new detector's kinds join by one line, never a code change.
FINDING_KIND_TO_GAP: dict[str, str] = {
    # promised-but-absent detector (promise_audit)
    "promise-figure-absent": "evidence-shaped",
    "promise-table-absent": "evidence-shaped",
    "promise-citation-absent": "ungrounded",
    "promise-xref-dangling": "orphaned",
    "promise-section-absent": "thin",
    # source-delta reader (readers.source_delta) — the argumentative substrate
    "source-motivation-lost": "ungrounded",
    "source-argument-lost": "ungrounded",
    "source-connective-lost": "ungrounded",
    # referee / cold reader — insufficiency + unrecoverable steps
    "referee-insufficient": "thin",
    "referee-inherited-uncited": "ungrounded",
    "cold-unmotivated-step": "thin",
    "cold-unrecoverable-role": "thin",
    # apparatus / layout orphans
    "float-orphan": "orphaned",
    "figure-contract-orphan": "orphaned",
    "citation-naked-reliance": "ungrounded",
    "unlinked-reliance": "ungrounded",
}

#: the source-delta finding kinds — losses whose substrate lives VERBATIM in his
#: source draft (the lost span IS the finding). A gap of one of these kinds is NEVER
#: novel: its substrate is recoverable from ``PAPER_FALQON_V1.md`` by construction,
#: so it probes against the SOURCE (:func:`source_aware_quarry_fn`) and, if that too
#: comes up empty, re-types to ``source-recoverable`` (re-project from his draft),
#: never ``novel``. These are also the SPAN-IDENTITY kinds: their ``where`` is the
#: constant ``source-vs-projection`` and their ``issue`` is a per-kind template
#: embedding only a 2-decimal score, so the verbatim ``quote`` is the finding's ONLY
#: identity and MUST enter the dedup key (:func:`_gid`) or distinct lost spans
#: silently collide.
SOURCE_DELTA_KINDS = frozenset((
    "source-motivation-lost", "source-argument-lost", "source-connective-lost"))

#: finding kinds whose IDENTITY is their verbatim span (not their where/issue). For
#: these the dedup key folds in a hash of ``quote`` so two different lost sentences
#: never collapse to one gap (true duplicates — same span — still collapse).
SPAN_IDENTITY_KINDS = SOURCE_DELTA_KINDS

#: the research-intent classes (the substrate-absent doors). ``source-recoverable``
#: is the source-delta door: a lost span whose substrate is his OWN draft, routed to
#: RE-PROJECTION FROM SOURCE (mined), never a novel derivation — the arming's
#: source-delta leg ("re-projection conditioned on the source prose where it exists").
RESEARCH_CLASSES = ("literature", "computation", "novel", "source-recoverable")

#: default cosine floor: a gap whose best quarry retrieval scores below this has no
#: mineable substrate in the source corpus and re-types as a research intent. A
#: DIAL (not a constant) — the calibration point the arming names.
DEFAULT_COSINE_FLOOR = 0.62

#: default per-round cap: directed pressure, not a ballooning agenda.
DEFAULT_ROUND_CAP = 8


@dataclass
class Gap:
    """A typed gap. ``research_class`` and ``epistemic`` are set only after the
    substrate-absent branch runs (:func:`retype_substrate_absent`); until then a gap
    is a growth target with a mineable quarry."""
    id: str
    gap_class: str                       # one of GAP_CLASSES
    where: str                           # section / node id / "source-vs-projection"
    section: str
    kind: str                            # the originating finding/diagnostic kind
    issue: str
    quote: str = ""
    severity: float = 0.5                # reader severity in [0,1]
    spine_critical: bool = False         # on a spine beat -> ranks first
    spine_rank: int = 0                  # position in the spine (lower = earlier/core)
    quarry_score: Optional[float] = None  # best cosine retrieval; None = not probed
    substrate_absent: bool = False       # quarry_score < floor
    research_class: Optional[str] = None  # literature | computation | novel
    epistemic: str = "mined"             # mined | cited | computed | conjectured
    source: str = "gap_ledger"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _gid(kind: str, where: str, issue: str, quote: str = "") -> str:
    """Stable gap id. For SPAN-IDENTITY kinds (:data:`SPAN_IDENTITY_KINDS`) the
    verbatim ``quote`` enters the key: their ``where`` is constant and their ``issue``
    is a per-kind template carrying only a rounded score, so the span is the finding's
    only identity — omitting it silently collapses distinct lost sentences into one
    gap (and which span survives the collision is arbitrary iteration order). True
    duplicates (identical span) still collapse; genuinely different spans no longer
    collide. Non-span kinds keep the (kind, where, issue) key unchanged."""
    key = f"{kind}|{where}|{issue}"
    if kind in SPAN_IDENTITY_KINDS and quote:
        key += "|" + hashlib.sha1(quote.encode("utf-8")).hexdigest()[:12]
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
    return f"GAP-{h}"


# ---------------------------------------------------------------------------
# 1. COMPILE — findings + conceptric diagnostics -> typed gaps
# ---------------------------------------------------------------------------

def compile_gaps(findings: list[dict[str, Any]],
                 diagnostics: Optional[dict[str, Any]] = None,
                 *, spine_sections: Optional[list[str]] = None) -> list[Gap]:
    """Compile typed gaps from the finding stream + the conceptric diagnostics.

    ``findings`` — reader/panel finding dicts (``kind``/``where``/``issue`` at
    least; ``section``/``quote``/``severity`` optional). Only kinds in
    :data:`FINDING_KIND_TO_GAP` become gaps.

    ``diagnostics`` — the conceptric health read, optional. Two lanes consumed:
      * ``diagnostics["thin_beats"]``: ``[{beat, section, note}]`` — beats with an
        empty argues-in lane (``spine_drift`` computes these). -> ``thin``.
      * ``diagnostics["orphans"]``: ``[node_id, ...]`` or ``[{node, section}]`` —
        the def-orphans (connect or kill). -> ``orphaned``.

    ``spine_sections`` — the ordered spine section ids; a gap whose section is on
    the spine is ``spine_critical`` and takes its ``spine_rank`` (lower = earlier =
    more core). Dedupe is by (kind, where, issue) so a finding surfacing twice in
    one round is one gap."""
    spine_index = {s: i for i, s in enumerate(spine_sections or [])}
    seen: set[str] = set()
    gaps: list[Gap] = []

    def _emit(gap_class: str, where: str, section: str, kind: str, issue: str,
              quote: str, severity: float) -> None:
        gid = _gid(kind, where, issue, quote)
        if gid in seen:
            return
        seen.add(gid)
        crit = section in spine_index
        gaps.append(Gap(
            id=gid, gap_class=gap_class, where=where, section=section, kind=kind,
            issue=issue, quote=quote[:240], severity=severity,
            spine_critical=crit,
            spine_rank=spine_index.get(section, len(spine_index) + 1)))

    for f in findings or []:
        kind = f.get("kind", "")
        gap_class = FINDING_KIND_TO_GAP.get(kind)
        if gap_class is None:
            continue
        where = f.get("where") or f.get("node") or f.get("node_id") or "?"
        section = f.get("section") or _section_of_where(where)
        _emit(gap_class, where, section, kind,
              f.get("issue", ""), f.get("quote") or f.get("primary", ""),
              _severity_of(f))

    if diagnostics:
        for tb in diagnostics.get("thin_beats") or []:
            if isinstance(tb, str):
                tb = {"beat": tb, "section": tb}
            section = tb.get("section") or tb.get("beat") or "?"
            _emit("thin", tb.get("beat") or section, section,
                  "spine-drift-thin",
                  tb.get("note") or "beat has an empty argues-in lane", "", 0.6)
        for orph in diagnostics.get("orphans") or []:
            if isinstance(orph, str):
                orph = {"node": orph, "section": ""}
            node = orph.get("node") or orph.get("node_id") or "?"
            section = orph.get("section") or ""
            _emit("orphaned", node, section, "def-orphan",
                  "node connected to nothing — connect or kill", "", 0.55)

    return gaps


def _severity_of(f: dict[str, Any]) -> float:
    s = f.get("severity")
    if isinstance(s, (int, float)):
        return float(s)
    # a hard reader kind (referee/insufficient) reads more severe by default
    kind = f.get("kind", "")
    if kind.startswith("referee") or "insufficient" in kind:
        return 0.8
    if kind.startswith("promise"):
        return 0.7
    return 0.5


def _section_of_where(where: str) -> str:
    """Best-effort section from a ``where`` token: a bare ``N3`` / ``s5`` / a
    ``slug:node`` prefix. ``source-vs-projection`` and unresolved wheres return ""
    (off-spine by default)."""
    where = (where or "").strip()
    if where in ("?", "source-vs-projection", ""):
        return ""
    if ":" in where:
        return where.split(":", 1)[0]
    if "," in where:
        return where.split(",", 1)[0].strip()
    return where


# ---------------------------------------------------------------------------
# 2. SUBSTRATE-ABSENT BRANCH — cosine-floor detection -> research-intent typing
# ---------------------------------------------------------------------------

def probe_quarry(gaps: list[Gap], quarry_fn: Callable[[Gap], float]) -> None:
    """Score each gap's QUARRY — its best cosine retrieval against the un-mined
    source-corpus spans — in place. ``quarry_fn(gap) -> float`` is injected (the
    default wiring is :func:`default_quarry_fn` over ``stage_retrieval``); a probe
    that raises is treated as SUBSTRATE-ABSENT (score 0.0), never a silent pass —
    an unreachable quarry cannot certify mineable substrate.

    ``SystemExit`` is caught alongside ``Exception``: ``stage_retrieval``'s
    ``build_form_channel_and_record`` FAILS LOUD (``raise SystemExit``) for a
    dial-enabled-but-gate-refused or broken-index store, and ``SystemExit`` is a
    ``BaseException`` that a bare ``except Exception`` would let escape — crashing the
    whole ledger build instead of degrading the one gap to substrate-absent as the
    contract promises. ``KeyboardInterrupt`` is deliberately NOT caught (it still
    aborts the round)."""
    for g in gaps:
        try:
            g.quarry_score = float(quarry_fn(g))
        except (Exception, SystemExit):
            g.quarry_score = 0.0


def retype_substrate_absent(gaps: list[Gap],
                            *, cosine_floor: float = DEFAULT_COSINE_FLOOR) -> list[Gap]:
    """Re-type every gap whose quarry falls below the cosine floor as a RESEARCH
    INTENT, routing it to one of the three doors and stamping the epistemic
    provenance the substrate will carry (the arming's LAW: *epistemic provenance
    travels with substrate*). A gap not yet probed (``quarry_score is None``) is
    left a mineable growth target. Returns the same list (mutated in place)."""
    for g in gaps:
        if g.quarry_score is None:
            continue
        if g.quarry_score >= cosine_floor:
            g.substrate_absent = False
            continue
        g.substrate_absent = True
        g.research_class = _research_class_for(g)
        g.epistemic = {
            "literature": "cited",
            "computation": "computed",
            "novel": "conjectured",
            # source-recoverable: his OWN draft is the substrate — MINED (from source),
            # never conjectured. The gap is flagged substrate-absent only against the
            # conceptric store; the source-aware quarry keeps most of these mineable.
            "source-recoverable": "mined",
        }[g.research_class]
    return gaps


def _research_class_for(g: Gap) -> str:
    """The door a substrate-absent gap re-types to. Evidence-shaped -> computation
    (a missing figure/derivation is computed). A SOURCE-DELTA loss -> source-
    recoverable (the lost span lives verbatim in his draft — re-project from source,
    NEVER a novel derivation; the arming's source-delta leg). A citation/reference-
    grounding gap -> literature. Only what remains — an ungrounded/thin gap the
    quarry cannot ground and that is neither source-recoverable, a citation, nor a
    computation — is a genuinely NOVEL result (a dispatched derivation, CONJECTURE-
    tier)."""
    if g.gap_class == "evidence-shaped":
        return "computation"
    if g.kind in SOURCE_DELTA_KINDS:
        return "source-recoverable"
    if g.kind in ("promise-citation-absent", "referee-inherited-uncited",
                  "citation-naked-reliance", "unlinked-reliance"):
        return "literature"
    return "novel"


def default_quarry_fn(project: str, store: str = "conceptric",
                      k: int = 3) -> Callable[[Gap], float]:
    """A quarry probe over ``stage_retrieval``: embed the gap's issue+quote and
    return the top cosine against the store's non-defective rows. Returns a
    callable so the store/backend load once. If ``stage_retrieval`` is unavailable
    or the store is un-gated, the probe returns 0.0 (substrate-absent) — never a
    fabricated high score."""
    def _fn(gap: Gap) -> float:
        try:
            from laplace.pipeline import stage_retrieval as SR
            query = f"{gap.issue} {gap.quote}".strip()
            served = SR.build_form_channel_and_record(store, query, k=k)
            if served is None:                       # disabled/un-gated store
                return 0.0
            _env, record = served
            cosines = [float(e.get("cos", 0.0))
                       for e in (record.get("exemplars") or [])]
            return max(cosines) if cosines else 0.0
        except (Exception, SystemExit):
            # SystemExit is a BaseException, NOT Exception: stage_retrieval fails
            # loud (raise SystemExit) for a dial-enabled-but-gate-refused or broken
            # store. Degrade THAT store to substrate-absent (0.0) as the docstring
            # promises, never abort the whole round.
            return 0.0
    return _fn


def source_aware_quarry_fn(project: str, source: "str | Any",
                           store: str = "conceptric", k: int = 3,
                           source_is_text: bool = False) -> Callable[[Gap], float]:
    """The DEFAULT growth-leg quarry: routes each gap to the RIGHT corpus by its
    provenance.

    A SOURCE-DELTA gap (:data:`SOURCE_DELTA_KINDS`) is a span the projection LOST —
    its substrate lives VERBATIM in his source draft (``PAPER_FALQON_V1.md``), never
    in the conceptric (the span was lost precisely because it never became a node).
    Probing it against the conceptric store therefore scores ~0.0 and mistypes his
    own prose as a ``novel`` conjecture — the exact inversion the arming's source-
    delta leg forbids. So a source-delta gap probes against the SOURCE: the max
    content-word overlap of its verbatim ``quote`` against the source sentences —
    ~1.0 for a recoverable span, keeping it MINEABLE (re-project from his draft). A
    source-delta gap whose span truly does not recover (empty/garbled quote) falls
    below the floor and re-types to ``source-recoverable`` (still not ``novel``).

    Every OTHER gap class keeps the conceptric-store embedding probe
    (:func:`default_quarry_fn`) — a genuinely ungrounded claim with no source span
    scores low and correctly re-types to its door (literature/computation/novel).

    The source is read ONCE (its content-word sentence sets cached in the closure),
    so probing N gaps costs one source read. Deterministic and offline (content-word
    Jaccard, the same machinery :mod:`readers.source_delta` uses to DETECT the loss —
    no model call), so rerunning re-mints the same census."""
    from laplace.pipeline.readers import source_delta as SD
    from pathlib import Path

    if source_is_text:
        text = str(source)
    else:
        try:
            text = Path(source).read_text(encoding="utf-8", errors="replace")
        except OSError:
            # a missing/unreadable source draft: degrade to an empty corpus (every
            # source-delta gap then scores 0.0 -> source-recoverable, never novel),
            # never crash the quarry constructor.
            text = ""
    src_word_sets = [SD._content_words(s)
                     for s in SD._sentences(SD._strip_markup(text))]
    src_word_sets = [w for w in src_word_sets if w]
    conceptric = default_quarry_fn(project, store=store, k=k)

    def _fn(gap: Gap) -> float:
        if gap.kind in SOURCE_DELTA_KINDS:
            qw = SD._content_words(gap.quote or "")
            if not qw:
                return 0.0                       # no span to recover -> source-recoverable
            best = 0.0
            for sw in src_word_sets:
                inter = len(qw & sw)
                if inter == 0:
                    continue
                j = inter / len(qw | sw)
                if j > best:
                    best = j
            return best
        return conceptric(gap)
    return _fn


# ---------------------------------------------------------------------------
# 3. RANK + CAP
# ---------------------------------------------------------------------------

def rank_gaps(gaps: list[Gap],
              prior_rulings: Optional[dict[str, float]] = None) -> list[Gap]:
    """Rank: SPINE-CRITICALITY first (spine gaps ahead of off-spine, earlier spine
    beats ahead of later), then reader SEVERITY, then his PRIOR RULINGS (a boost
    keyed on the gap's kind or id), then a stable id tiebreak. Pure — returns a new
    sorted list.

    ``prior_rulings`` is the taste flywheel's return leg at the ranking: the durable
    caller builds it from his LIVE banked rulings
    (:func:`ruling_recall.rulings_boost` over ``proxy_verdicts.jsonl``), so a gap on a
    subject he has already ruled on outranks an equally-severe gap he has not. Omitting
    it is still lawful (the pure-function contract, and every test may rank without a
    repo) — but a PRODUCTION caller that omits it makes this docstring a lie, which is
    exactly what it was until the leg was wired. The boost sits below spine-criticality
    in the key, so it re-orders within a tier and can never invert the spine law."""
    rulings = prior_rulings or {}

    def _key(g: Gap) -> tuple:
        boost = rulings.get(g.id, rulings.get(g.kind, 0.0))
        return (
            0 if g.spine_critical else 1,     # spine gaps first
            g.spine_rank,                      # earlier spine beats first
            -(g.severity + boost),             # higher severity/boost first
            g.id,                              # stable
        )
    return sorted(gaps, key=_key)


def cap_per_round(gaps: list[Gap], cap: int = DEFAULT_ROUND_CAP) -> list[Gap]:
    """Take the top ``cap`` (assumes already ranked). Directed pressure."""
    return list(gaps[:max(0, cap)])


# ---------------------------------------------------------------------------
# 4. BANK — typed intents through the existing gate + the trajectory metric
# ---------------------------------------------------------------------------

def to_conceptric_intents(gaps: list[Gap], *, project: str = "",
                          round: int = 0, actor: str = "gap_ledger") -> list[dict]:
    """Emit each MINEABLE gap (substrate present) as a conceptric intent in the
    :func:`adjudicate.make_conceptric_intent` shape — ``status: "open"``, queued,
    executed by NOTHING (the draft-only conceptric law). The gap class maps onto a
    conceptric intent verb: ungrounded/thin -> ``content-missing`` (a claim needs an
    arguing node), orphaned -> ``edge-missing`` (connect or kill), evidence-shaped
    stays content-missing with an evidence note."""
    from laplace.pipeline import adjudicate as ADJ
    intent_for = {
        "ungrounded": "content-missing",
        "thin": "content-missing",
        "orphaned": "edge-missing",
        "evidence-shaped": "content-missing",
    }
    out: list[dict] = []
    for g in gaps:
        if g.substrate_absent:
            continue                      # research intents go through the other door
        rec = ADJ.make_conceptric_intent(
            g.where, intent_for.get(g.gap_class, "other"),
            note=f"[{g.gap_class}] {g.issue}",
            finding_id=g.id, kind=g.kind, section=g.section,
            actor=actor, round=round, project=project)
        rec["gap"] = g.as_dict()          # the typed-gap primary record rides along
        out.append(rec)
    return out


def to_research_intents(gaps: list[Gap], *, project: str = "",
                        round: int = 0, actor: str = "gap_ledger") -> list[dict]:
    """Emit each SUBSTRATE-ABSENT gap as a typed RESEARCH INTENT record — the
    engine's frontier, typed and ranked. Each carries its research class (the door),
    the epistemic provenance the eventual substrate will wear, and the gap as its
    primary record. These NEVER auto-apply: a literature intent awaits the
    citation-direction organ, a computation intent a banked WO, a novel intent a
    dispatched derivation whose truth-judgment is GENUINELY-HIS."""
    # the epistemic write FOLDS THROUGH THE ONE HOME (schema.canonical_status) at the
    # moment it leaves this module, so the surfaced status a set-status op consumes is
    # always a canonical enum member (cited -> imported, mined -> exploratory), never a
    # carrier that can drift from the enum (G3 leg 1c). The gap's own record
    # (``g.as_dict()`` below) keeps the raw carrier as provenance.
    from laplace.pipeline.schema import canonical_status
    out: list[dict] = []
    for g in gaps:
        if not g.substrate_absent:
            continue
        out.append({
            "id": f"RI-{g.id[4:]}",
            "record": "research-intent",
            "project": project,
            "research_class": g.research_class,      # literature | computation | novel
            "door": {
                "literature": "citation-direction",
                "computation": "evidence-organ",
                "novel": "derivation-attempt",
                # his OWN draft is the door — re-project the lost span from source,
                # never a dispatched derivation. The arming's source-delta leg.
                "source-recoverable": "re-project-from-source",
            }[g.research_class],
            "epistemic": canonical_status(g.epistemic) or g.epistemic,  # enum-canonical
            "node": g.where,
            "section": g.section,
            "gap_class": g.gap_class,
            "kind": g.kind,
            "quarry_score": g.quarry_score,
            "spine_critical": g.spine_critical,
            "issue": g.issue,
            "gap": g.as_dict(),                       # primary record
            "status": "open",
            "source": actor,
            "round": round,
            "text": f"research intent ({g.research_class}) for {g.gap_class} gap "
                    f"on {g.where!r}: {g.issue}",
        })
    return out


def build_ledger(findings: list[dict[str, Any]],
                 diagnostics: Optional[dict[str, Any]] = None,
                 *, spine_sections: Optional[list[str]] = None,
                 quarry_fn: Optional[Callable[[Gap], float]] = None,
                 cosine_floor: float = DEFAULT_COSINE_FLOOR,
                 cap: int = DEFAULT_ROUND_CAP,
                 prior_rulings: Optional[dict[str, float]] = None,
                 project: str = "", round: int = 0) -> dict[str, Any]:
    """The whole ledger in one call: compile -> probe quarry -> re-type substrate-
    absent -> rank -> cap -> emit both intent streams. ``quarry_fn`` optional; when
    absent, gaps are NOT probed (all stay mineable — the substrate-absent branch is
    a no-op, which is the declared default when no retrieval backend is wired).
    Returns the ranked+capped gaps and both intent streams plus the census a round
    banks to the trajectory (discovery counts by class; closure is a cross-round
    join the trajectory surface owns)."""
    gaps = compile_gaps(findings, diagnostics, spine_sections=spine_sections)
    if quarry_fn is not None:
        probe_quarry(gaps, quarry_fn)
        retype_substrate_absent(gaps, cosine_floor=cosine_floor)
    ranked = rank_gaps(gaps, prior_rulings)
    capped = cap_per_round(ranked, cap)
    concept = to_conceptric_intents(capped, project=project, round=round)
    research = to_research_intents(capped, project=project, round=round)
    return {
        "gaps": [g.as_dict() for g in capped],
        "all_gaps_n": len(gaps),
        "conceptric_intents": concept,
        "research_intents": research,
        "census": _census(gaps, capped, concept, research),
    }


def _census(all_gaps: list[Gap], capped: list[Gap],
            concept: list[dict], research: list[dict]) -> dict[str, Any]:
    by_class: dict[str, int] = {}
    by_research: dict[str, int] = {}
    spine_n = 0
    for g in all_gaps:
        by_class[g.gap_class] = by_class.get(g.gap_class, 0) + 1
        if g.spine_critical:
            spine_n += 1
        if g.substrate_absent and g.research_class:
            by_research[g.research_class] = by_research.get(g.research_class, 0) + 1
    return {
        "discovered": len(all_gaps),
        "capped": len(capped),
        "by_gap_class": by_class,
        "spine_critical": spine_n,
        "substrate_absent": sum(1 for g in all_gaps if g.substrate_absent),
        "by_research_class": by_research,
        "conceptric_intents": len(concept),
        "research_intents": len(research),
    }


def closure_metric(prev_gap_ids: list[str],
                   this_gap_ids: list[str]) -> dict[str, Any]:
    """THE METRIC (the growth channel of the trajectory): gap CLOSURE rate vs
    DISCOVERY rate across two rounds. A gap id present last round and absent this
    round CLOSED; present in both RECURRED (unclosed — names a grower failure or a
    missing organ); absent last round and present this round is fresh DISCOVERY."""
    prev, this = set(prev_gap_ids), set(this_gap_ids)
    closed = prev - this
    recurring = prev & this
    discovered = this - prev
    denom = len(prev) or 1
    return {
        "closed": sorted(closed),
        "recurring": sorted(recurring),
        "discovered": sorted(discovered),
        "closure_rate": round(len(closed) / denom, 3),
        "discovery_rate": round(len(discovered) / (len(this) or 1), 3),
        "recurring_n": len(recurring),
    }


def finding_kinds_manifest() -> list[dict[str, str]]:
    """The gap ledger introduces NO finding kinds of its own (it CONSUMES them) —
    this returns the empty manifest so ``register_component_kinds`` can fold it
    uniformly with the detectors that do."""
    return []
