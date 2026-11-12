"""The one schema — every record shape, op vocabulary, and marker convention in the
conceptric→storyboard→projection pipeline, stated once.

Before this module the schemas lived implicitly in four code sites
(``storyboard.py``, ``corpus_ingest.py``, ``scripts/build_section_briefs.py``,
``scripts/validate_projection_plan.py``) and were re-discovered by grep every
session (the 2026-07-08 infra mandate, thread 3). This is the leaf module of the
pipeline package: it imports NOTHING from laplace, so both ledger engines and
every script can consume it without cycles. The canon rendering of this module
(``scripts/render_pipeline_docs.py`` → ``canon://operations/*``) is generated FROM
it — the doc can not drift from the code.

The two ledgers (the split that kept being re-probed, pinned):

- **L1 — the substrate / corpus-friction ledger**, ``corpus_friction/<project>.jsonl``.
  Append-only rewire records over the conceptric (nodes, edges, essences, spine,
  projection slots). Writer: ``corpus_ingest.rewire_add``. Reducers:
  ``corpus_ingest.friction_current`` (live node state) and
  ``corpus_ingest.apply_overlay`` (fold into a build). Record fields:
  ``id, ts, kind, node, target, value, by, status`` (+ ``parent, node_kind,
  essence, ord, narrative`` where the kind carries them).
- **L2 — the storyboard / projection-plan ledger**, a three-file system beside the
  plan: ``projection_plan.base.json`` (immutable authored origin) +
  ``projection_plan.friction.jsonl`` (append-only board ops) → reduced to the
  committed ``projection_plan.json``. Writer: ``storyboard.plan_write``. Reducer:
  ``storyboard.reduce_plan`` (fold = ``storyboard._apply_op``).

The bridge (``storyboard._coemit`` / ``spine_write`` / ``reconcile_section_refs``)
mirrors plan placement into L1 ``section_ref`` slots; an evolution that writes one
ledger without the mirror is the drift class the atomic transaction
(``pipeline.ledger.transaction``) exists to prevent.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

# ---------------------------------------------------------------------------
# L1 — substrate rewire records
# ---------------------------------------------------------------------------

#: The kinds ``rewire_add`` admits (the write gate).
REWIRE_KINDS = frozenset({
    "confirm-edge", "add-edge", "remove-edge", "retype-edge", "reclassify", "edit-essence",  # edge + content
    "add-node", "delete-node", "move-node", "set-kind",                        # node CRUD
    "set-spine", "unset-spine",                                                # the apex chain
    "set-projection", "set-source",                                            # authored metadata
    "set-status",                                                              # epistemic status
})

#: The unified friction channel (2026-07-11 learning-loop design, §1b): an
#: engine ``friction`` or an author-``fork`` record rides the SAME L1 substrate
#: ledger as the rewire records — one spine, class told by ``kind``. The write
#: gate is :func:`corpus_ingest.friction_add`, never a raw append.
FRICTION_KINDS = ("friction", "fork")

#: Kinds OBSERVED in live ledgers beyond the write gate — deposited directly by
#: evolution scripts (figure ``data``/``schematic`` payload records) and by the
#: pipeline's own transaction journal. Reducers ignore unknown kinds by design,
#: so these are auditable pass-throughs, not state. ``friction``/``fork`` join
#: the pass-through: a friction record on a manuscript's ledger perturbs no
#: section and no reducer state (propagate._record_sections checks this set).
AUXILIARY_RECORD_KINDS = frozenset({"data", "schematic", "txn"}) | set(FRICTION_KINDS)

#: Every field a rewire record may carry (the base eight + kind-specific extras).
#: ``axis`` types an add-edge/confirm-edge against :data:`AXES` (the relation
#: family it lands on); ``supersedes`` on an add-node names an older node the new
#: one retires (the goal-versioning idiom, honoured only on add-node). The record
#: ``status`` field is the lifecycle status (open/resolved) — the EPISTEMIC status
#: a ``set-status`` op carries rides ``value`` and is threaded onto the built node
#: as its own ``status`` slot, distinct from this record-level lifecycle field.
REWIRE_FIELDS = (
    "id", "ts", "kind", "node", "target", "value", "by", "status",
    "parent", "node_kind", "essence", "ord", "narrative",
    "axis", "rel", "supersedes", "ref", "projection", "rationale",
)

# Human-facing semantic relation carried by current rewire records.  It is
# distinct from the storage axis: ``validated_by`` is evidence, ``analogy`` is
# lateral, and neither is silently promoted into a logical prerequisite.
EDGE_RELATIONS = frozenset({
    "prerequisite", "support", "counterevidence", "implementation", "analogy",
    "validated_by", "questions", "unknown",
})

#: The friction/fork record spine: the exact L1 base (the first nine
#: ``REWIRE_FIELDS``) plus the friction extras. ``owning_layer`` names the organ
#: that owns the fix (a path or protocol name — the engine's analogue of
#: ``owning_stage``); ``cost`` is what the friction cost, plainly; ``proposal``
#: is the reporter's suggested fix (advisory, never an instruction);
#: ``evidence`` is filled at consumption (commit hash / evolution dir /
#: OPEN_STACK row) — a resolution retiring a friction/fork WITHOUT evidence
#: leaves its target open (the drain's validator enforces this).
#: ``chain`` (2026-07-11) is the Chain of custody: an ordered list of goal
#: frames, coarse→fine, tracing the descent from global goal to the local
#: friction — the grain is session goal → phase/bite → dispatch goal → local
#: action (e.g. ["growth-session 2026-07-11: build the one thing out",
#: "phase 2B: voice wash of r6", "V2 wash run in worktree",
#: "compile_weld_dispatch(voice_on=True)"]). Each frame is a short string.
#: Recommended, not required (seed records predate it); the drain rolls up
#: records sharing a chain prefix and counts the chainless.
FRICTION_FIELDS = REWIRE_FIELDS[:9] + ("owning_layer", "cost", "proposal",
                                       "evidence", "chain")

#: ``set-projection`` value slots (dict-MERGED per record, never replaced):
#:   latex_label   — emitted as ``\label{...}`` by the projector
#:   section_ref   — the beat/section this node belongs to (also a virtual
#:                   connectivity edge in the connectivity gate)
#:   data_source   — for experiment figures: the CSV the render is checked against
#:   provenance    — figure provenance block (generator/engine/data/commit/seed)
#:   retired       — True retires the PROJECTION (the node and its history stay)
#:   term          — the glossary registry handle
#:   framing       — POSITIONING guidance for builders (meta, POLICY-channel only:
#:                   never rendered into prose; the essence stays object-only)
PROJECTION_SLOTS = (
    "latex_label", "section_ref", "data_source", "provenance", "retired",
    "term", "title", "framing", "result_bindings", "obligation", "mathematics",
)


def proj_of(node: dict) -> dict:
    """A node's projection slot, wherever the network put it. The one accessor —
    previously copied verbatim between the brief builder and the plan validator."""
    return node.get("projection") or (node.get("meta") or {}).get("projection") or {}


# ---------------------------------------------------------------------------
# Epistemic status — one home, one vocabulary
# ---------------------------------------------------------------------------

#: The epistemic status a node's claim wears, written by the ``set-status`` rewire
#: op and threaded onto the built node as its ``status`` slot. Before this the
#: status lived in three unlinked carriers and on no built-node record: the ingest
#: claim status/tier (``scripts/ingest_synthetic.py``, lost past the pour), the
#: plan-meta postures at node-KIND grain, and ``gap_ledger``'s per-record
#: ``epistemic`` field. This is the reconciled vocabulary; :data:`STATUS_ALIASES`
#: folds the carriers into it so there is one enum, not a fourth.
EPISTEMIC_STATUSES = ("proven", "computed", "conjectured", "imported", "exploratory")

#: The fold from a legacy carrier token into :data:`EPISTEMIC_STATUSES` — the
#: reconciliation the growth-stage arming named (a fourth vocabulary was the
#: campaign judge's must-fix). Two carriers merge here:
#:   * gap_ledger's ``epistemic`` (mined | cited | computed | conjectured):
#:     ``cited`` is admitted literature -> ``imported``; ``mined`` is a
#:     machine-proposed gap -> ``exploratory`` (the machine-proposal marker);
#:     ``computed``/``conjectured`` already match the enum (no alias needed).
#:   * the ingest claim-status strings (the ``_TIER`` keys): mapped by their
#:     epistemic character. The genuinely foundational givens (a definition, a
#:     resolved boundary) read as ``proven`` for want of an axiom slot in the
#:     five-value enum — a judgement fold, tunable here in the one place.
#: An unknown token resolves to ``None`` (refused at the write gate), so a typo
#: cannot silently mint a fictional status.
STATUS_ALIASES = {
    # gap_ledger.py epistemic carrier (the load-bearing reconciliation)
    "mined": "exploratory",
    "cited": "imported",
    # ingest_synthetic.py claim-status carrier (the _TIER keys), by tier character
    "motivation": "exploratory",
    "definition": "proven",
    "definition_with_explicit_two_mode_obstruction": "proven",
    "assumption": "conjectured",
    "proposition": "proven",
    "derivation_and_numerical_check": "computed",
    "finite_local_form_derived": "proven",
    "finite_stage_supported": "computed",
    "finite_rg_recursion_added": "computed",
    "proved_finite_dimensional": "proven",
    "toy_verified": "computed",
    "numerical_check": "computed",
    "literature_supported": "imported",
    "geometry_supported": "computed",
    "boundary_resolved": "proven",
    "interpretation_boundary": "exploratory",
    "philosophical_after_technical_work": "exploratory",
    "finite_obstruction_memory_example": "computed",
}


def canonical_status(value: Any) -> str | None:
    """Resolve a status token to its :data:`EPISTEMIC_STATUSES` member — the enum
    itself passes through; a :data:`STATUS_ALIASES` carrier folds; anything else is
    ``None`` (the write gate refuses it, the reducer skips it). Case- and
    whitespace-forgiving so a hand-written deposit is not rejected on casing."""
    if not isinstance(value, str):
        return None
    v = value.strip().lower()
    if v in EPISTEMIC_STATUSES:
        return v
    return STATUS_ALIASES.get(v)


# ---------------------------------------------------------------------------
# The axis registry — relation families typed, one minter, one parser
# ---------------------------------------------------------------------------

#: Every edge in a conceptric's ``edge_index`` belongs to a relation FAMILY — an
#: axis of projection of the one high-dimensional graph. Before this registry the
#: family was smuggled as an ad-hoc string prefix (``sem::``, ``confirmed::``,
#: ``conn::A<->B::atoms::kind``, ``inpaper::``) re-parsed by convention at every
#: consumer. Each row names its axis, what it bears, the edge-token grammar (so
#: the wire form has one definition), and a coverage-law one-liner (the floor a
#: completeness gauge reads per axis). The trained metric M and the semantic caches
#: are keyed on the CURRENT symbolic wire, so the token STRINGS are held stable: a
#: consumer that mints through :func:`token_for` writes exactly what it wrote
#: before, and new code never hand-writes a prefix. The edge_index data SHAPE (a
#: list of referent strings) does not change — the metric/embed retrain is a banked
#: later order, not this wave's.
AXES = (
    {"axis": "derives", "bears": "a result derives from its antecedents",
     "prefix": None, "modes": ("confirmed", "sem", "tentative"), "pair": False,
     "grammar": "<mode>::<target>  (mode in confirmed|sem|tentative)",
     "coverage_law": "every derivation-DAG node reaches its stated antecedents "
                     "(no result orphaned from its provenance)"},
    {"axis": "supports", "bears": "literature bears a claim",
     "prefix": "supports", "modes": (), "pair": False,
     "grammar": "supports::<claim-node> (borne target; the token lives ON the literature node that bears it)",
     "coverage_law": "every load-bearing claim carries at least one supports edge "
                     "to a literature node"},
    {"axis": "validates", "bears": "evidence bears a result",
     "prefix": "validates", "modes": (), "pair": False,
     "grammar": "validates::<evidence-node>",
     "coverage_law": "every result carries at least one validates edge to a "
                     "resolvable reading / evidence node"},
    {"axis": "implements", "bears": "an implementation realises a logical object",
     "prefix": "implements", "modes": (), "pair": False,
     "grammar": "implements::<implementation-node>",
     "coverage_law": "implementation links remain inspectable but do not establish a logical premise"},
    {"axis": "demonstrates", "bears": "a figure bears a result",
     "prefix": "demonstrates", "modes": (), "pair": False,
     "grammar": "demonstrates::<result-node> (borne target; the token lives ON the figure node that bears it)",
     "coverage_law": "every headline result is demonstrated by at least one figure"},
    {"axis": "contains", "bears": "a parent contains its members (structural)",
     "prefix": "inpaper", "modes": (), "pair": False,
     "grammar": "inpaper::<paper-node>",
     "coverage_law": "every substrate atom is contained by exactly one structural "
                     "parent"},
    {"axis": "connects", "bears": "two concepts couple laterally within a theme",
     "prefix": "conn", "modes": (), "pair": True, "joiner": "<->",
     "grammar": "conn::<lo><->hi>::<atoms>::<kind>[::<strength>]",
     "coverage_law": "lateral concept coupling — an exploration channel, no "
                     "manuscript coverage floor"},
)

#: Registered axis names, and the pair-family subset (lateral couplings carrying an
#: unordered endpoint pair, not a single target referent).
AXIS_NAMES = tuple(row["axis"] for row in AXES)
PAIR_AXES = frozenset(row["axis"] for row in AXES if row.get("pair"))
#: The target-bearing axes an add-edge/confirm-edge can be typed against.
TARGET_AXES = tuple(row["axis"] for row in AXES if not row.get("pair"))

_AXIS_ROW = {row["axis"]: row for row in AXES}

# The authored relation label is the human/machine planning contract.  The axis is
# its storage family; direction says how the public ``source``/``target`` pair is
# read.  Only ``prerequisite`` is an inferential dependency.  In particular,
# evidence, implementation and analogy remain graph connections without becoming
# premises merely because the legacy edge index also carries a bare target.
RELATION_SEMANTICS = {
    "prerequisite": {"axis": "derives", "direction": "source-requires-target",
                     "inferential": True},
    "support": {"axis": "supports", "direction": "source-supported-by-target",
                "inferential": False},
    "counterevidence": {"axis": None, "direction": "source-counterevidenced-by-target",
                        "inferential": False},
    "validated_by": {"axis": "validates", "direction": "source-validated-by-target",
                     "inferential": False},
    "implementation": {"axis": "implements", "direction": "source-implemented-by-target",
                       "inferential": False},
    "analogy": {"axis": "connects", "direction": "lateral", "inferential": False},
    "questions": {"axis": None, "direction": "source-questions-target",
                  "inferential": False},
    "unknown": {"axis": None, "direction": "unresolved", "inferential": False},
}

_RELATION_BY_AXIS = {
    "derives": "prerequisite",
    "supports": "support",
    "validates": "validated_by",
    "implements": "implementation",
    "connects": "analogy",
}


def relation_semantics(rel: Any) -> dict | None:
    """Return a copy of the canonical semantics for an authored relation label."""
    row = RELATION_SEMANTICS.get(str(rel or "").strip())
    return dict(row) if row is not None else None


def relation_for_axis(axis: Any) -> str | None:
    """The authored relation represented by an axis, where that mapping is exact."""
    return _RELATION_BY_AXIS.get(str(axis or "").strip())


def relation_axis_error(rel: Any, axis: Any) -> str | None:
    """Explain a rel/axis contradiction; an omitted axis takes the relation default."""
    rel_s, axis_s = str(rel or "").strip(), str(axis or "").strip()
    if not rel_s or not axis_s:
        return None
    semantics = RELATION_SEMANTICS.get(rel_s)
    if semantics is None:
        return f"unknown relation {rel_s!r}"
    expected = semantics["axis"]
    if expected != axis_s:
        return f"relation {rel_s!r} uses axis {expected!r}, not {axis_s!r}"
    return None


def _axis_by_prefix() -> dict:
    """token prefix -> (axis, mode). For ``derives`` the prefix IS the mode."""
    idx: dict[str, tuple[str, str | None]] = {}
    for row in AXES:
        if row.get("modes"):
            for m in row["modes"]:
                idx[m] = (row["axis"], m)
        else:
            idx[row["prefix"]] = (row["axis"], None)
    return idx


_AXIS_BY_PREFIX = _axis_by_prefix()


def token_for(axis: str, target: str | None = None, *, mode: str = "confirmed",
              kind: str | None = None, strength: str | None = None,
              lo: str | None = None, hi: str | None = None,
              atoms: str | None = None) -> str:
    """Mint the audit-marker edge token for a relation family — the single place a
    prefix grammar is written, the inverse of :func:`parse_edge_token`. The
    target-bearing axes take a ``target`` (``derives`` also a ``mode``); the pair
    families (``connects``) take ``lo``/``hi``/``atoms``/``kind`` and an optional
    ``strength``. Raises on an unknown axis or a missing field, so a caller can not
    quietly mint a malformed token."""
    row = _AXIS_ROW.get(axis)
    if row is None:
        raise ValueError(f"unknown axis {axis!r}; registered: {AXIS_NAMES}")
    if row.get("pair"):
        if lo is None or hi is None or atoms is None or kind is None:
            raise ValueError(f"axis {axis!r} needs lo, hi, atoms, kind")
        # the fence the docstring promises (the G1 judge's catch): the pair grammar
        # splits its inner fields on '::' and lo<->hi on the joiner, so a field
        # carrying either separator would mint a token the parser misreads - refuse it
        # here rather than emit an ambiguous edge.
        for label, field in (("lo", lo), ("hi", hi), ("atoms", atoms),
                             ("kind", kind), ("strength", strength)):
            if field and "::" in str(field):
                raise ValueError(f"axis {axis!r} field {label} may not contain '::'")
        if row["joiner"] in str(lo) or row["joiner"] in str(hi):
            raise ValueError(f"axis {axis!r} lo/hi may not contain {row['joiner']!r}")
        tok = f"{row['prefix']}::{lo}{row['joiner']}{hi}::{atoms}::{kind}"
        if strength:                       # carried where parsed; absent -> the prior 4-field form
            tok += f"::{strength}"
        return tok
    if not target:
        raise ValueError(f"axis {axis!r} needs a target")
    if row.get("modes"):                   # derives — the mode is the prefix
        if mode not in row["modes"]:
            raise ValueError(f"axis {axis!r} mode must be one of {row['modes']}")
        return f"{mode}::{target}"
    return f"{row['prefix']}::{target}"


def parse_edge_token(token: Any) -> dict | None:
    """Parse an edge token back to its relation family, or ``None`` for a bare
    referent (a plain node id / bib key carries no axis marker). Inverse of
    :func:`token_for` for every registered row: a target-bearing token yields
    ``{axis, target[, mode]}``; a pair token yields
    ``{axis, lo, hi, atoms, kind, strength}``. Split is on the FIRST ``::`` for
    target tokens (a target may itself be an ``atom::name`` id), on every ``::``
    for pair tokens (their inner fields never carry one)."""
    if not isinstance(token, str) or "::" not in token:
        return None
    prefix, rest = token.split("::", 1)
    hit = _AXIS_BY_PREFIX.get(prefix)
    if hit is None:
        return None
    axis, mode = hit
    row = _AXIS_ROW[axis]
    if row.get("pair"):
        parts = rest.split("::")
        if len(parts) < 3 or row["joiner"] not in parts[0]:
            return None
        lo, hi = parts[0].split(row["joiner"], 1)
        return {"axis": axis, "lo": lo, "hi": hi, "atoms": parts[1],
                "kind": parts[2], "strength": parts[3] if len(parts) > 3 else ""}
    if not rest:
        return None    # a bare mode-prefix ('sem::') is a nonsense token, not an edge
    out: dict[str, str] = {"axis": axis, "target": rest}
    if mode is not None:
        out["mode"] = mode
    return out


# ---------------------------------------------------------------------------
# L2 — storyboard plan ops
# ---------------------------------------------------------------------------

#: CHEAP ops leave every section's node SET unchanged: prose stays valid, only
#: the \input order or a title string moves. Zero-token recompile.
CHEAP_OPS = frozenset({"reorder-sections", "reorder-appendices", "retitle", "reorder-nodes", "set-outline", "bind-source"})

#: EXPENSIVE ops change a section's substrate: its builder must re-run.
#: ``set-meta`` merges into ``plan.meta`` (typed fields — workflow modes,
#: postures, gate refs) exactly as set-projection merges node slots; it is
#: classed expensive because policy changes want a re-dispatch even though the
#: %NODES diff cannot see them.
EXPENSIVE_OPS = frozenset({
    "add-section", "remove-section", "restore-section",
    "edit-job", "edit-notes", "set-refs",
    "move-node", "add-node", "remove-node", "toggle-beat",
    "set-nodes",   # replace a section's whole pool (the derive path)
    "set-meta",
    "set-serves",  # C3.1 section ownership: pin the contribution(s) a section earns
                   # (resolved against meta.contribution_rank by check_serves).
                   # Mirrors set-refs — a declaration edit the %NODES diff can't see,
                   # so it re-dispatches rather than passing silently.
})

PLAN_OP_KINDS = CHEAP_OPS | EXPENSIVE_OPS

#: Plan JSON shape: ``meta`` + ``sections[]`` + ``appendices[]``.
SECTION_FIELDS = ("id", "title", "job", "notes", "refs", "beats",
                  "nodes_in_order", "figures", "spec")


def section_nodes(section: dict) -> list[str]:
    """A section/appendix's pinned node list — ``nodes_in_order`` with the legacy
    ``nodes`` fallback. The one accessor (previously re-derived at four sites)."""
    return list(section.get("nodes_in_order") or section.get("nodes") or [])


def plan_sections(plan: dict, appendices: bool = True):
    """Iterate the plan's sections (and appendices), in document order."""
    from laplace.manuscript.book_outline import outline
    yield from outline(plan.get("sections") or [])
    if appendices:
        yield from outline(plan.get("appendices") or [])


# ---------------------------------------------------------------------------
# The %-marker convention (the dirty-detection join key)
# ---------------------------------------------------------------------------

#: A compiled fragment carries ``% PLAN:<section-id>`` once and ``% NODES: <id> …``
#: per discharged span. A section is dirty iff its plan node-set differs from the
#: set its fragment's markers discharge. Figures ride ``\ref`` (tracked in
#: ``figures[]``), citations ride ``\cite`` — neither reads as a node change.
PLAN_MARKER_RE = re.compile(r"^%\s*PLAN:\s*(\S+)\s*$", re.MULTILINE)
NODES_MARKER_RE = re.compile(r"^%\s*NODES:\s*(.+)$", re.MULTILINE)

#: The realiser and the weld also emit ``% <section-id>-p<N>`` before every
#: rendered paragraph — ``spec_id`` == the narrative / prose-provenance
#: ``paragraph_id``. It carries no node set (the per-paragraph nodes live in the
#: provenance sidecar); it is the JOIN KEY that lets a rendered span resolve to
#: ITS paragraph — and its realiser/weld decisions — rather than the whole
#: section. Distinct from PLAN/NODES by construction: the whole comment body is a
#: single token ending ``-p<digits>`` (``PLAN:x``/``NODES: …`` never do).
PARA_MARKER_RE = re.compile(r"^%\s*(\S+-p\d+)\s*$", re.MULTILINE)

#: A KIND-PREFIXED node id, space-free (``goal:x``, ``def:y``, ``res:z``). This is
#: the IDENTITY guard, not the pool grammar: two callers (``citation_direction``'s
#: claim-node resolution, ``review_surface``'s feedback anchoring) use it to decide
#: whether a free-text reference names a conceptric node at all, and the strings
#: they must reject — section stems (``introduction``, ``limits_and_discussion``),
#: bib keys (``chan2025shadow``), the ``source-vs-projection`` sentinel — are bare.
#: Widening THIS pattern would fabricate anchors, so the pool grammar is separate.
NODE_ID_RE = re.compile(r"^[a-z][\w-]*:[^\s]+$")

#: The node-POOL grammar: kind-prefixed OR bare. Conceptric pools mint both —
#: ``RQ-CLM-043`` (uppercase, dashed), ``fal_clm_001`` / ``d_context_window`` /
#: ``readout_dimension_K`` (snake_case, uppercase tails), ``nmse`` (one word).
#: Before 2026-08-07 the dirty diff filtered on ``NODE_ID_RE``, so every bare id
#: dropped out of BOTH sides of the set difference and a changed node pool read
#: CLEAN (roland totally, falqon/eigenengine partially — IDEMPOTENCE row 7).
#: The bare arm's charset is ``[A-Za-z]`` then word-chars/dot/hyphen (``\w`` is
#: Unicode-aware for str patterns, so accented ids like ``café`` also pass — the
#: gate is against punctuation and whitespace, not against non-ASCII letters). That
#: is what keeps a blind builder's trailing prose (``(evidence)``, ``back:``,
#: ``\section{…}``) out of the id sets.
POOL_ID_RE = re.compile(r"^(?:[a-z][\w-]*:[^\s]+|[A-Za-z][\w.-]*)$")

#: ``<section>-p<N>`` is the paragraph marker's spec id (:data:`PARA_MARKER_RE`),
#: which shares the bare-id charset. It is prose provenance, never a node.
SPEC_ID_TAIL_RE = re.compile(r"-p\d+$")

#: Namespaces that are SUPPORT, not content, for the dirty diff.
NON_CONTENT_PREFIXES = ("fig:", "ref:")


def is_pool_id(x: str) -> bool:
    """Whether ``x`` is a content node id the dirty diff should compare: pool
    grammar, not a ``fig:``/``ref:`` support namespace, not a paragraph spec id."""
    return bool(POOL_ID_RE.match(x)) and not SPEC_ID_TAIL_RE.search(x) \
        and not x.startswith(NON_CONTENT_PREFIXES)


def clean_ids(ids) -> set[str]:
    """Real content-node ids only — the set the dirty diff compares."""
    return {x for x in ids if is_pool_id(x)}


# ---------------------------------------------------------------------------
# Literature (the global store, coupled by ref: edges)
# ---------------------------------------------------------------------------

BIB_KEY_RE = re.compile(r"@\w+\{([^,\s]+),")


def bib_keys(bib_text: str) -> set[str]:
    return set(BIB_KEY_RE.findall(bib_text))


def bib_entries(bib_text: str) -> dict[str, str]:
    """key → full balanced-brace entry (previously private to the brief builder)."""
    out: dict[str, str] = {}
    for m in BIB_KEY_RE.finditer(bib_text):
        start = m.start()
        depth, i = 0, start
        while i < len(bib_text):
            if bib_text[i] == "{":
                depth += 1
            elif bib_text[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        out[m.group(1)] = bib_text[start:i + 1]
    return out


# ---------------------------------------------------------------------------
# The intake door — one typed record for every perturbation
# ---------------------------------------------------------------------------

#: Where an instruction LANDS is decided by its scope the moment it arrives —
#: the structural end of single-instance rules that pretend to be general.
#:   global  → canon-standards review queue (folded at sew-up, author-gated)
#:   project → plan meta / term registry / dated evolution sources
#:   section → plan section fields (job, notes, refs)
#:   node    → essence (object) or projection.framing (policy)
INSTRUCTION_SCOPES = ("global", "project", "section", "node")

#: Feedback/intake record fields (the review surface already emits most of these;
#: judge panels join the same door in P4). ``supersedes`` is the correction
#: mechanism: a later record naming an earlier record's id RETIRES it (wrong
#: kind, wrong routing, withdrawn) — the door stays append-only and the
#: correction propagates, because propagate skips superseded records.
FEEDBACK_FIELDS = ("id", "project", "ts", "scope", "kind", "node_id", "section",
                   "text", "source", "anchor", "supersedes")

#: The ALTITUDE vocabulary a feedback row's ``scope`` takes — the six already typed
#: in the author's own ledger rows (``FB-20260808-gm-001``…``gm-009`` carry
#: artefact / structure / voice / sentence / meta / delivery). One producer: the
#: redline composer's scope keys, the comment door's validation, and any consumer
#: that groups by altitude read THIS tuple; no competing taxonomy is minted.
#: Order is the composer's stable key order (1..6), not alphabetical.
#: ``scope`` is OPTIONAL on a row: absent means UNSCOPED, a first-class state
#: (scope is required downstream, optional at capture).
FEEDBACK_SCOPES = ("sentence", "structure", "voice", "artefact", "meta", "delivery")

#: How a row's ``scope`` was set: the author chose it, a frozen text rule inferred
#: it, or the DOOR applied its own default because the gesture named none. Banked
#: beside ``suggested_scope`` (what the rule leaned toward) so a rule's override
#: rate is derivable from the ledger mechanically.
#:
#: ``default`` exists because ``chosen`` and a machine-applied altitude were
#: BYTE-IDENTICAL on the rewrite door: it sets ``scope="sentence"`` when the
#: composer named none, wrote no ``scope_source``, and the row then read back
#: exactly like one he had picked with a digit. An override rate that cannot
#: separate his hand from the door's default is not derivable, so the door now
#: says which it was and the walk states the same sentence before Enter.
SCOPE_SOURCES = ("inferred", "chosen", "default")

#: Voice comments take one of three fates — NEVER "append to the contract", and
#: (2026-07-09 rebuild mandate) never a new instruction in any generation path:
#:   mechanical    → a structural failure pattern joins the DETECTOR data
#:                   (``VOICE_FAILURE_PATTERNS`` below — a boundary gate runs it)
#:   exemplar      → the accepted wording is banked in the sealed exemplar store;
#:                   it feeds voice-profile calibration, never a prompt
#:   consolidation → queued for the author-gated revision of the versioned voice
#:                   profile (``profiles/voice/``), the one voice artifact
VOICE_FATES = ("mechanical", "exemplar", "consolidation")

#: The 5-way decomposition of builder-contract material (each kind has a HOME;
#: none of them is "prose poured into every brief"):
#:   gate        → already enforced by verify; briefs carry the gate HANDLE
#:   voice       → the versioned voice profile (profiles/voice/), supplied ONLY
#:                 to the final prose realiser and the weld — never upstream
#:   workflow    → POLICY channel (modes: minimal-diff, body-first, …)
#:   node_data   → typed per-node/plan data (epistemic postures, framing)
#:   terminology → the term registry / glossary (project history lives here)
CONTRACT_HOMES = ("gate", "voice", "workflow", "node_data", "terminology")

#: The decision sidecar — a generating stage records a FORK it took against a
#: paragraph, so the review surface can surface WHERE the pipeline chose or
#: hesitated (his ask: "surface all those forks and decisions"). Keyed by
#: ``spec_id`` (== paragraph_id), the same join the provenance sidecar uses. The
#: realiser already emits its forks as prose-provenance ``qualifications``; the
#: weld emits none today — this is its target. A decision is a RECORD, never an
#: edit to substance: a cross-link-opportunity is SURFACED and routed, not
#: silently written (the weld's substance freeze holds). ``before`` is optional
#: (a doubt or opportunity has no prior form).
#: ``paragraph-restructure`` is his model (this session): the weld keeps its
#: freedom to MERGE plan paragraphs (their spec_ids join on one paragraph) or
#: SPLIT one (its spec_id repeats across parts) — a paragraph is a unit, some
#: content needs more than one — but it must BACKPROPAGATE that as a decision, so
#: the many-to-many provenance stays exact and narrative learns the new unit.
DECISION_KINDS = ("ambiguity-resolved", "substance-doubt",
                  "cross-link-opportunity", "voice-choice", "paragraph-restructure")
DECISION_RECORD_FIELDS = ("spec_id", "section", "stage", "kind",
                          "before", "after", "rationale")


# ---------------------------------------------------------------------------
# The typed worklist — new substance, routed not confabulated
# ---------------------------------------------------------------------------

#: When the loop demands what does not exist, propagate emits a WORK ITEM, not a
#: dirty section. Each kind carries its worker, landing zone, gate, and
#: dirty-consequence; ordering falls out of the substrate edges.
WORK_KINDS = ("derive", "simulate", "figure", "mint", "prose",
              "structure", "narrative", "render")

#: The dispatch-model law (his, 2026-07-11): Eigen orchestrates; dispatched agents are
#: Opus-level or less. The orchestrator is the ceiling - never dispatch a model above
#: the one you are. Banked mechanically, not remembered: ``compile_dispatch`` stamps
#: every compiled dispatch with a (model, effort) drawn from this map and clamped to
#: ``MAX_MODEL``; ``scripts/audit_dispatch_models.py`` enforces the same ceiling over
#: the hand-written ``model:`` literals in the .mjs/.js workflows (the dispatch sites
#: the compiler cannot reach).
MODEL_RANK = ("haiku", "sonnet", "opus")
MAX_MODEL = "opus"
#: The ONE tier table (his 2026-09-21 model law, STANDING_LAW.md:46): a dispatch names a
#: provider-NEUTRAL intelligence tier and an effort, and each provider resolves the tier to
#: its own model. Before this table the same fact lived in three places - this module in
#: Claude names only, a ``MODEL`` literal in ``.claude/workflows/atlas-wave.js``, and the
#: model Codex root typed into each ``collaboration.spawn_agent`` call - so a tier could be
#: changed in one and stay stale in the others. The Codex defaults were upgraded at the
#: author's request on 2026-10-06, verified in the 0.160.1 client's model/list catalogue.
#: ``/authoring/providers`` serves that catalogue; Claude resolves MODEL_RANK as tiers.
TIERS = {
    "deep": {"claude": "opus", "codex": "gpt-6.1-sol"},
    "standard": {"claude": "sonnet", "codex": "gpt-5.6-terra"},
    "light": {"claude": "haiku", "codex": "gpt-6-luna"},
}
#: worker kind -> (tier, effort) default. Adjudication-grade derivation earns the apex;
#: mechanical minting/rendering rides the floor; the middle is standard. This is the row
#: source: ``WORKER_MODEL`` below is its Claude projection, not a second table.
WORKER_TIER = {
    "derive": ("deep", "high"),
    "simulate": ("standard", "medium"),
    "figure": ("standard", "medium"),
    "mint": ("light", "low"),
    "prose": ("standard", "medium"),
    "structure": ("standard", "medium"),
    "narrative": ("standard", "medium"),
    "render": ("light", "low"),
}


def tier_model(tier: str, provider: str = "claude") -> str:
    """The model a provider resolves an intelligence tier to. The only place a tier becomes
    a model name: a launcher asks here instead of carrying a literal of its own.

    An unknown tier or provider RAISES. The conjugate choice - falling back to the ceiling -
    would let a mistyped tier run silently at the apex and be discovered in the run ledger
    afterwards, which is the failure ``pin_model`` already refuses for a mistyped pin."""
    if tier not in TIERS:
        raise ValueError(f"unknown tier {tier!r}; one of {tuple(TIERS)}")
    column = TIERS[tier]
    if provider not in column:
        raise ValueError(f"unknown provider {provider!r}; one of {tuple(column)}")
    return column[provider]


#: worker kind -> (model, effort) default, DERIVED from ``WORKER_TIER`` through the Claude
#: column of ``TIERS``. Byte-identical to the literal dict it replaces (asserted by
#: ``tests/test_dispatch_grammar.py::test_worker_model_is_the_derived_literal``), so its
#: consumers - ``pipeline/dispatch.py:1217``, ``pipeline_surface.py:1774`` - and the
#: ``monkeypatch.setitem`` in ``tests/test_dispatch_model_ceiling.py`` are untouched: it is
#: still a plain mutable dict of ``(model, effort)`` in the same key order.
WORKER_MODEL = {kind: (tier_model(tier), effort)
                for kind, (tier, effort) in WORKER_TIER.items()}


def tier_effort(tier: str) -> str:
    """The ONE effort ``WORKER_TIER`` pairs with this tier.

    Not a second table: every row of ``WORKER_TIER`` that names a tier names the same
    effort beside it, so the pairing is a fact OF that table and reading it back is a
    derivation (``tests/test_writing_provider_tiers.py::test_each_tier_pairs_with_one_effort``
    fails the moment a row disagrees).  A role default therefore names a TIER only --
    before this, a role's effort would have been a second literal free to disagree with the
    worker row at the same tier, which is the two-tables defect this module ended once."""
    if tier not in TIERS:
        raise ValueError(f"unknown tier {tier!r}; one of {tuple(TIERS)}")
    efforts = sorted({effort for kind_tier, effort in WORKER_TIER.values() if kind_tier == tier})
    if len(efforts) != 1:
        raise ValueError(f"WORKER_TIER pairs tier {tier!r} with {efforts}; a role default "
                         "cannot read one effort out of that")
    return efforts[0]


def _tier_rank(tier: str) -> int:
    """A tier's height, read off ``MODEL_RANK`` through its own Claude column, so "the
    highest tier" is a derivation and not a fourth spelling of ``opus``."""
    return MODEL_RANK.index(TIERS[tier]["claude"])


def _dispatched_tier() -> str:
    """The tier a dispatched worker or judge defaults to: the one most of ``WORKER_TIER``'s
    rows already name (ties to the lower tier).  The per-KIND default stays ``WORKER_TIER``'s
    own row and a wave's per-packet tier stays in its plan; this is only the answer for a
    dispatch that names no kind, and it is read out of that table rather than typed again."""
    tiers = [tier for tier, _ in WORKER_TIER.values()]
    most = max(tiers.count(tier) for tier in tiers)
    return min((tier for tier in TIERS if tiers.count(tier) == most), key=_tier_rank)


#: ROLE -> tier.  The author's dispatch-model law (``STANDING_LAW.md`` model law, his
#: 2026-09-21): the interfacing session runs at the highest tier and a dispatched worker
#: never inherits it; plus his 2026-10-03 economy rule for anything that drives a real
#: provider in a test (cheapest model per provider, effort low).  Every VALUE is derived --
#: the apex and the floor from ``_tier_rank``, the dispatched tier from ``WORKER_TIER`` --
#: so this dict names the roles the system has and nothing else.  The app's session default
#: is resolved through here and ``tier_model``; before it, the app never asked, and its
#: default model was whichever catalogue row the vendor flagged ``default``
#: (``src/laplace/writing_provider.py:569`` copies the Claude SDK's own ``default`` entry
#: onto the row and ``src/laplace/web/static_shared/workspace-session.mjs:215`` preselected it;
#: both lines were resolved by `grep -n` for the identifier beside them at THIS commit, not
#: carried over from the brief's base-tree numbering).
ROLE_TIER = {
    "session": max(TIERS, key=_tier_rank),
    "worker": _dispatched_tier(),
    "judge": _dispatched_tier(),
    "test": min(TIERS, key=_tier_rank),
}
#: What a session row's ``model_source`` can say: the role's tier default, the project's
#: saved preference, or a model named on the turn.  Declared beside the table that produces
#: the first of them, so the door, the row and the tests read one enum.
MODEL_SOURCES = ("tier-default", "project-preference", "named")


def role_tier(role: str) -> str:
    if role not in ROLE_TIER:
        raise ValueError(f"unknown role {role!r}; one of {tuple(ROLE_TIER)}")
    return ROLE_TIER[role]


def role_model(role: str, provider: str = "claude") -> dict:
    """The tier, model and effort a role defaults to for one provider.  The only place the
    app's default model comes from: ``project_work`` asks here and validates the answer
    against the live catalogue."""
    tier = role_tier(role)
    return {"role": role, "tier": tier, "model": tier_model(tier, provider),
            "effort": tier_effort(tier)}


def model_spellings(model: str, resolved_model: str | None = None) -> set:
    """Every spelling one catalogue row answers to, by MECHANISM and not by list: the id
    itself, the id with an alias suffix removed (``opus[1m]`` -> ``opus``), and the
    hyphen-delimited parts of both ids (``claude-sonnet-5`` -> ``sonnet``).

    One mechanism, both directions: :func:`model_tier` reads a row's tier out of it and
    ``writing_provider.advertised_model`` (:func:`~laplace.writing.provider.advertised_model`)
    finds the advertised row a tier's model names.  A list of
    aliases here would be a second model table with a vendor's release schedule attached."""
    tokens = set()
    for text in (str(model or ""), str(resolved_model or "")):
        if not text:
            continue
        tokens.add(text)
        base = text.split("[")[0]
        tokens.add(base)
        tokens.update(part for part in base.replace("/", "-").split("-") if part)
    return {token for token in tokens if token}


def model_tier(model: str, provider: str = "claude",
               resolved_model: str | None = None) -> str | None:
    """The tier a model belongs to, read back out of ``TIERS`` -- ``None`` for a model the
    table does not name.  The reverse of :func:`tier_model`, so a session row can carry the
    tier of a model its author typed by hand with no second table to look it up in."""
    spellings = model_spellings(model, resolved_model)
    for tier, column in TIERS.items():
        if column.get(provider) in spellings:
            return tier
    return None


def model_choice_declaration(providers: tuple = ("claude", "codex")) -> dict:
    """The whole of model choice, generated from this module at read time.

    One declaration, three readers: the provider catalogue annotates its rows with it
    (``src/laplace/writing/provider.py``), the tool door's ``help`` for the providers route
    renders it (``src/laplace/web/writing_declared_http.py`` names this function as its
    producer), and the composer's pane reads the catalogue.  Nothing stores it -- a copy on
    disk or in a UI dict is exactly the drift ``TIERS`` was introduced to end."""
    return {
        "schema_version": "laplace.model-choice/1",
        "law": ("a dispatch names a provider-neutral intelligence tier and an effort, and "
                "each provider resolves the tier to its own model; the interfacing session "
                "runs at the highest tier and a dispatched worker never inherits it"),
        "row_source": "src/laplace/pipeline/schema.py TIERS / WORKER_TIER",
        "tiers": {tier: {provider: tier_model(tier, provider) for provider in providers}
                  for tier in sorted(TIERS, key=_tier_rank, reverse=True)},
        "role_defaults": {role: {"tier": role_tier(role),
                                 "effort": tier_effort(role_tier(role)),
                                 "models": {provider: tier_model(role_tier(role), provider)
                                            for provider in providers}}
                          for role in ROLE_TIER},
        "model_sources": list(MODEL_SOURCES),
        "effort_truth": ("a model that supports no effort is recorded with effort null -- "
                         "what the adapter sends -- and a pane may still display Automatic"),
    }


def clamp_model(model: str) -> str:
    """Clamp a model name to the dispatch ceiling. Unknown names land AT the ceiling
    (never silently above it); known names above ``MAX_MODEL`` are pulled down."""
    rank = {m: i for i, m in enumerate(MODEL_RANK)}
    if model not in rank:
        return MAX_MODEL
    return model if rank[model] <= rank[MAX_MODEL] else MAX_MODEL


def pin_model(model: str, pin: str | None) -> str:
    """Raise ``model`` to a pinned FLOOR tier. The conjugate of :func:`clamp_model`,
    and the half the tree lacked: with ``opus`` atop ``MODEL_RANK`` the clamp is the
    identity on every known token, so it can pull a stage DOWN but never pin one UP.

    Pin-then-clamp is the composition order, and it is load-bearing: the caller
    applies this first and ``clamp_model`` after, so a pin can never lift a stage
    above ``MAX_MODEL`` and the 2026-07-11 ceiling law still binds. ``pin=None`` is
    inert (the per-worker ``WORKER_MODEL`` default stands, byte-identical to
    pre-pin). A pin BELOW ``model`` never demotes — a floor only raises.

    An unknown pin raises: a mistyped arm policy must fail loudly, never run
    silently at the default tier and be discovered in the run ledger afterwards."""
    if not pin:
        return model
    rank = {m: i for i, m in enumerate(MODEL_RANK)}
    if pin not in rank:
        raise ValueError(f"unknown model pin {pin!r}; one of {MODEL_RANK}")
    if model not in rank:
        return pin
    return pin if rank[pin] > rank[model] else model


#: feedback kind → work kind (None = comment only; no generation demanded).
#: Judge-panel keys land through the same door as his review comments
#: (voice/closure/caption/claims/calc → voice/imprecise/caption/naked-claim/
#: calc-detail), so a panel round and a human pass propagate identically.
KIND_TO_WORK = {
    # Adjudication-tier intents ride the one ledger but are VERDICT records,
    # not generation work: known kinds, no item (the None idiom). The first
    # live auto-minted calibration-intent (2026-07-10) proved they reach the
    # intake door on real corpora.
    "calibration-intent": None,
    "conceptric-intent": None,
    # projection-intent (2026-07-13): the PLAN-altitude sibling of
    # conceptric-intent — a whole-artefact/plan finding types into it (adjudicate.
    # make_projection_intent) and it draws a DRAFT plan proposal, never an auto-
    # apply. A verdict record like its conceptric sibling: known, no work item.
    "projection-intent": None,
    # The six banked desk-review finding kinds (whole-artefact author read):
    # VERDICT-only at the intake door — each is a plan-altitude signal an author
    # routes to a projection-intent, never a per-node generation demand. Without
    # these the live subset-sum-itqde ledger raises at propagate.intake_items
    # (the door refuses an unrouted kind); the None idiom lets them through as
    # routed comments while the plan-altitude correction rides route-plan.
    "author-desk-review": None,
    "quadrature-conflation": None,
    "novelty-overbroad": None,
    "access-model-unstated": None,
    "symbol-collision-M": None,
    "contribution-rank-absent": None,
    # author-read (2026-07-22): HIS read observations, banked verbatim (a reaction to
    # reading the compiled paper). A read is a signal for the author, not a per-node
    # generation demand — so it routes as a comment (the None idiom): counted in
    # comments_routed, excluded from the worklist. Without this the live paper_falqon
    # ledger raised at the propagate intake door and 400'd the whole dry-run preview.
    "author-read": None,
    # ratification-grant (2026-07-22): HIS ratification of open projection-intents — an
    # author verdict authorising work already named, not a fresh generation demand. Same
    # comment routing as author-read; it rides beside author-read in the live ledger.
    "ratification-grant": None,
    "missing-derivation": "derive",
    "missing-simulation": "simulate",
    "figure-standard": "figure",
    "figure-regenerate": "figure",
    "missing-node": "mint",
    "imprecise": "prose",
    "voice": "prose",
    "naked-claim": "prose",
    "calc-detail": "prose",
    "caption": "prose",
    "meta-leak": "prose",
    # 2026-07-09 staged rebuild: feedback routes to the OWNING LAYER (mandate
    # §12) — a downstream stage never compensates for an upstream defect.
    "missing-content": "mint",          # → manuscript projection
    "unsupported-claim": "mint",        # → projection / research state
    "section-order": "structure",       # → structural resolution
    "repetition": "structure",          # cross-section repeats = structural
    "sequence": "narrative",            # explanatory order = narrative spec
    "equation-placement": "structure",
    "equation-break": "render",         # → document/LaTeX backend
    "figure-purpose": "mint",           # figure SPEC defect = projection layer
    "tex-layout": "render",             # → typography profile / backend
    "prose-fidelity": "prose",          # re-render from the SAME narrative spec
    "note": None,
    "comment": None,                    # review-surface comment verb (B-4): a
                                        # ruling-surface kind, no auto work item
                                        # (same None idiom as 'note') - so a live
                                        # comment record never halts the intake door.
}

#: work kind → the pipeline stage that owns its resolution (reporting +
#: dispatch routing for the staged path; mandate §12's table, mechanised).
WORK_TO_LAYER = {
    "derive": "research-state", "simulate": "research-state",
    "mint": "projection", "figure": "figures",
    "structure": "structural", "narrative": "narrative",
    "prose": "prose", "render": "document",
}

#: A work item (the dispatch manifest generalised): what propagate emits and
#: compile_dispatch consumes.
WORK_ITEM_FIELDS = ("id", "kind", "owning_stage", "scope", "local", "project",
                    "target", "section", "goal", "blocked_by", "source_feedback",
                    "worker")


# ---------------------------------------------------------------------------
# Brief channels — object_not_artefact, mechanised
# ---------------------------------------------------------------------------

#: A brief is TWO fenced channels. OBJECT is the only renderable content; POLICY
#: configures the generator and is never echoed. A policy sentence surfacing in
#: prose is the leak, and the meta_leak gate scans for exactly that.
BRIEF_CHANNEL_POLICY = "POLICY"
BRIEF_CHANNEL_OBJECT = "OBJECT"

#: The canon standards a NODE builder rides — HANDLES, resolved by the reader
#: on demand; a change to the standard propagates to every future dispatch
#: because nothing is copied. (Voice is deliberately absent: the profile
#: reaches only the prose realiser and the weld — 2026-07-09.)
POLICY_HANDLES = (
    "canon://skills/figure_standard",
    "canon://skills/latex_forge",
    "canon://workflow/object_not_artefact",
)

#: The verify checks that will run on a built output.
DEFAULT_GATE_REFS = ("glossary", "citations", "figures", "connectivity", "meta_leak")

#: The one builder contract — the 17-item wall, replaced. Everything else the
#: wall carried has a typed home (CONTRACT_HOMES below).
BUILDER_CONTRACT_LINE = (
    "Render the OBJECT channel only. POLICY configures you — obey it and never "
    "let its text, vocabulary, or self-description surface in the prose (a "
    "policy sentence in the output is the defect the meta_leak gate rejects). "
    "An unmet demand is a typed friction to report, never a confabulation.")

#: ``plan.meta`` typed fields the POLICY channel renders from (set via the
#: ``set-meta`` op; the legacy free-text ``builder_contract`` list folds into
#: POLICY verbatim until migrated):
#:   workflow_modes — list of mode lines (minimal-diff prior, evolutionary
#:                    reprojection, marker preservation, …)
#:   postures       — node-kind → epistemic posture (exact algebra, measured
#:                    validation, perturbative model, statistical certification)
#:   gate_refs      — the verify checks that will run on the output
#: (``voice_refs`` retired 2026-07-09: voice rides only the versioned profile
#: at the final leg, never plan meta.)
PLAN_META_TYPED = ("workflow_modes", "postures", "gate_refs")
_FENCE_OPEN = "<!-- {channel} -->"
_FENCE_CLOSE = "<!-- /{channel} -->"


def fence(channel: str, body: str) -> str:
    """Wrap a channel body in its fences."""
    return f"{_FENCE_OPEN.format(channel=channel)}\n{body}\n{_FENCE_CLOSE.format(channel=channel)}"


_FENCE_RE = re.compile(
    r"<!--\s*(POLICY|OBJECT)\s*-->\n(.*?)\n<!--\s*/\1\s*-->", re.DOTALL)


def parse_channels(text: str) -> dict[str, str]:
    """channel → body for a fenced brief; {} for a legacy unfenced brief (the
    transition reader in project-fixedpoint falls back on the whole text)."""
    return {m.group(1): m.group(2) for m in _FENCE_RE.finditer(text)}


# ---------------------------------------------------------------------------
# plan.meta.contribution_rank — the one authored judgement, two framings
# ---------------------------------------------------------------------------

#: ``plan.meta.contribution_rank`` accepts either a plain ordered list of claim
#: strings or a list of ``{rank, claim, role}`` dicts; a ``role`` reading as
#: excluded/exploratory demotes the claim to the EXCLUDED line. This parse is
#: the one authored judgement's ONE decode - shared by every consumer so the
#: primary/excluded split is never duplicated. Consumers differ only in the
#: SURROUNDING FRAME: dispatch.py's kernel wraps it as policy voice (node
#: builders, §13 kernel-bearing workers); narrative.py's packet wraps it as
#: authored-content voice (the prose realiser, §13 context-isolated - no
#: 'policy'/'contract' framing may reach it).
def contribution_rank_id(claim: str) -> str:
    """A contribution's STABLE id, derived from its claim text — the
    ``meaning_upfold._cluster_id`` precedent (content-derived, byte-identical
    across re-authoring), NOT an enumerate ordinal re-minted every re-rank. A
    sha1 over the stripped claim text: the SAME claim yields the SAME id whether
    authored as a plain string or a ``{rank, claim, role}`` dict, and whether it
    sits at rank 1 or rank 4 — so a section's ``serves`` reference survives a
    re-ranking that leaves the claim text untouched. The rank number is a POSITION
    (it moves); the id is IDENTITY (it does not). ``""`` for an empty claim (a
    malformed entry the caller already drops). Ids are opaque: nothing parses the
    hex, so the derivation is a drop-in and re-hashable at will."""
    text = (claim or "").strip()
    if not text:
        return ""
    return "c" + hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:8]


def unwrap_contribution_rank(rank: Any) -> Any:
    """Read the bare ``contribution_rank`` list through the 2026-07-22 respine
    envelope. The RESPINE (ratified, intent PI-20260721-142526-161107) banked the
    rank as ``{"value": [thesis, D1..Dn], "projection_ruling": {...}}`` — the
    wrapper carrying the ruling's provenance. Every reader wants the ``value``
    list; NONE may rewrite the store to a bare list, because that would strip the
    ratified ``projection_ruling``. This is the one place that knows the envelope:
    a ``{value: ...}`` dict yields its ``.value``; a bare list / ``None`` / any
    other shape passes through untouched (callers already tolerate non-lists).
    The peel repeats to its FIXED POINT, so a double-wrapped
    ``{value: {value: [...]}}`` (an envelope applied twice — seen live where one
    respine re-wrapped an already-wrapped rank) still reaches the inner list; a
    bounded loop guards against a pathological cycle. Non-lossy by construction —
    it reads, it never writes back to the store."""
    for _ in range(16):
        if isinstance(rank, dict) and "value" in rank:
            rank = rank.get("value")
        else:
            break
    return rank


def contribution_rank_lines(rank: Any) -> tuple[list[str], list[str]]:
    """Parse ``rank`` into ``(primary, excluded)`` line lists. Each primary line
    reads ``"N. claim [role] {#id}"``; each excluded entry reads
    ``"claim (role) {#id}"``. The trailing ``{#id}`` is the STABLE content-id
    (``contribution_rank_id``) — byte-identical across two renders of the same
    meta and across list-vs-dict authoring of the same claims, because it derives
    from the claim text alone. ``([], [])`` for anything empty/malformed - callers
    read that as "no block" (the additive floor: an absent/malformed rank changes
    nothing downstream). The respine ``{value, projection_ruling}`` envelope is
    unwrapped here (``unwrap_contribution_rank``), so EVERY consumer of this one
    decode — the kernel block (dispatch), the prose hierarchy (narrative), the
    board strip (shared_ui/storyboard), the mass audit's sibling — reads the
    ratified class thesis without a second copy of the shape logic."""
    rank = unwrap_contribution_rank(rank)
    if not rank or not isinstance(rank, (list, tuple)):
        return [], []
    primary: list[str] = []
    excluded: list[str] = []
    for i, item in enumerate(rank, 1):
        if isinstance(item, dict):
            claim = str(item.get("claim") or "").strip()
            role = str(item.get("role") or "").strip()
            n = item.get("rank", i)
        else:
            claim, role, n = str(item).strip(), "", i
        if not claim:
            continue
        cid = contribution_rank_id(claim)
        tag = f" {{#{cid}}}"
        role_l = role.lower()
        if role and ("excluded" in role_l or "exploratory" in role_l):
            excluded.append((claim if not role else f"{claim} ({role})") + tag)
        else:
            primary.append(f"{n}. {claim}" + (f" [{role}]" if role else "") + tag)
    return primary, excluded


# ---------------------------------------------------------------------------
# Evolution contracts (both banked shapes)
# ---------------------------------------------------------------------------

#: ``evolution_plan.json`` meta, required for any direction:
EVOLUTION_META_REQUIRED = ("project", "from_version", "to_version", "contract")

#: Substrate-led shape (v2→v3 spectral surfacing): enumerated mutations.
#: ``removals`` is a true DELETE (delete-node) for correcting a mis-mint — distinct
#: from ``deprecations`` (which retire a projection but keep the node record).
EVOLUTION_SUBSTRATE_SECTIONS = ("mints", "reshapes", "deprecations", "edges", "removals")

#: Storyboard-led shape (general-first restructure): the plan leads, the
#: substrate follows (spine reorder + placement reshapes).
EVOLUTION_STORYBOARD_SECTIONS = ("target_arc", "rulings", "reshapes_placement")

#: The laws (canon://skills/conceptric_evolution — enforced by pipeline.evolve):
#: fold by ledger never replay · deprecate projections keep nodes · the plan is
#: downstream · supersessions are new dated files · round-trip exact or stop.


# ---------------------------------------------------------------------------
# The meta-leak lexicon (object_not_artefact, made scannable)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Claims → gates: the operation contracts
# ---------------------------------------------------------------------------

#: Every operational surface ships with its canon contract node, an
#: orient-reachability probe, and an EXECUTABLE verify (module:callable, run by
#: the ``contracts`` check). A surface without a green row here does not pass —
#: the up-guarantee, and the engine backing its own claims.
#: ``verify`` callables live in ``laplace.pipeline.contracts_verify``.
OPERATION_CONTRACTS = (
    {"surface": "the two-ledger system (L1 substrate / L2 plan)",
     "canon": "canon://operations/two_ledger_system",
     "probe": "what are the two ledgers and how do they stay in sync",
     "verify": "laplace.pipeline.contracts_verify:ledger_engine"},
    {"surface": "projection plan schema + storyboard op vocabulary",
     "canon": "canon://operations/projection_plan_schema",
     "probe": "projection plan schema storyboard op vocabulary set-spine markers",
     "verify": "laplace.pipeline.contracts_verify:rendered_docs_fresh"},
    {"surface": "the gate registry (verify checks)",
     "canon": "canon://operations/gate_registry",
     "probe": "what are the seven gates the projection must pass",
     "verify": "laplace.pipeline.contracts_verify:rendered_docs_fresh"},
    {"surface": "pipeline operators (evolve / restructure / propagate)",
     "canon": "canon://operations/pipeline_operators",
     "probe": "run an evolution restructure a project propagate changes",
     "verify": "laplace.pipeline.contracts_verify:operators_importable"},
    {"surface": "typed dispatch compiler (narrative packets + node frames)",
     "canon": "canon://operations/briefs_and_dispatch",
     "probe": "compile a dispatch for a builder agent from the narrative spec",
     "verify": "laplace.pipeline.contracts_verify:dispatch_compiles"},
    {"surface": "the staged manuscript pipeline (spec→structure→narrative→prose→document)",
     "canon": "canon://operations/staged_generation",
     "probe": "the staged compile-before-render manuscript pipeline and its gates",
     "verify": "laplace.pipeline.contracts_verify:staged_stages_ready"},
    {"surface": "the project registry",
     "canon": "canon://operations/two_ledger_system",
     "probe": "resolve a registered project paths ledger plan briefs",
     "verify": "laplace.pipeline.contracts_verify:registry_resolves"},
    {"surface": "the standing sew-up operator",
     "canon": "canon://operations/pipeline_operators",
     "probe": "sew up fold the machinery back embed the close operators",
     "verify": "laplace.pipeline.contracts_verify:sewup_ready"},
    {"surface": "laplace.core.records.journal.bank_row signature, relations and intent-before-execute",
     "canon": "canon://operations/journal_bank_row",
     "probe": "journal bank_row signature edges relations intent execute",
     "verify": "laplace.pipeline.contracts_verify:journal_bank_row_contract"},
    {"surface": "laplace.engine.bequest.parse_parcel syntax and rotation cap",
     "canon": "canon://operations/bequest_parcel",
     "probe": "bequest parcel syntax descend probe 900 character cap refusal",
     "verify": "laplace.pipeline.contracts_verify:bequest_parcel_contract"},
    {"surface": "scripts/reembed.py argv, device dials and deposit outputs",
     "canon": "canon://operations/reembed_contract",
     "probe": "reembed argv full spectral gpu deposit writes",
     "verify": "laplace.pipeline.contracts_verify:reembed_contract"},
    {"surface": "campaign gates atlas_s1g2_gate.py, atlas_s1_gate.py, atlas_s0_gate.py exit codes",
     "canon": "canon://operations/campaign_gate_contract",
     "probe": "campaign gates S1 generation 2 S1 S0 exit codes verdict",
     "verify": "laplace.pipeline.contracts_verify:campaign_gate_contract"},
    {"surface": "scripts/dispatch_codex.py argv, sandbox and dispatch row",
     "canon": "canon://operations/dispatch_codex_contract",
     "probe": "dispatch codex argv sandbox worker compile row output schema",
     "verify": "laplace.pipeline.contracts_verify:dispatch_codex_contract"},
)


#: A meta-instruction surfacing in rendered prose is the leak, and the leak is
#: the defect (canon://workflow/object_not_artefact). These classes are the
#: mechanical floor the ``meta_leak`` verify check runs over compiled .tex
#: (comment lines excluded — the %NODES markers themselves are structural).
#: The lexicon is DATA: tune it here, never in the gate's code. All three
#: classes fail the gate; the welder remains the global backstop for the
#: narrative leaks no lexicon can name.
META_LEAK_PATTERNS: dict[str, tuple[str, ...]] = {
    # the machine's own vocabulary appearing in the paper
    "machine-vocab": (
        r"\bbuilder contract\b", r"\bstoryboard\b", r"\bconceptric\b",
        r"\bnode essence\b", r"\bfriction ledger\b", r"\bdispatch manifest\b",
        r"\bprojection plan\b", r"\bglossary gate\b", r"\bretired node\b",
    ),
    # plan/fork routing language addressed to the pipeline, not the reader
    "routing": (
        r"the author'?s call", r"\bhis call\b", r"pending the author",
        r"\bTODO\b", r"\bFIXME\b", r"\[FIGURE TODO\]",
    ),
    # performative posture: announcing a property instead of exhibiting it
    "performative": (
        r"stated plainly and modestly", r"it is worth being (exact|precise|truthful)",
        r"\bhonesty clauses?\b", r"states rather than settles",
        r"\bdemoted to\b", r"not the organising (object|principle)",
    ),
    # self-certifying: the sentence's function is to declare the work truthful,
    # modest, safe, or defensible (his ratification 2026-07-08 - the quality
    # lives in the proposition, never in an announcement)
    "self-certifying": (
        r"\bthe truthful (boundar|claim|sentence)", r"state[sd]? (its|the) status plainly",
        r"\bthe safe claim\b", r"\bdeliberately modest\b", r"and a defensible one\b",
        r"in the only way that counts",
    ),
    # commercial metaphor as governing language (ratified 2026-07-08)
    "commercial": (
        r"\bspends? (that|the|its) record", r"measurements? buys?\b",
        r"\bthe device is spent\b", r"bought with classical arithmetic",
        r"at lattice price\b", r"\bspent once\b",
    ),
    # the resonant closer / verdict register (ratified 2026-07-08)
    "resonant-closer": (
        r"\bthe (hardness )?verdict\b", r"is what the instrument is for\b",
        r"the ruler does not care", r"cost the instrument nothing",
        r"\bnow knows how to\b",
    ),
    # engine node-ids surfacing in reader-facing prose (the outside judgement,
    # banked 2026-07-09: "def:classical-dial, res:..., thm:... directly in
    # ordinary prose and captions"). Machine addresses live inside \label/\ref
    # braces or the metadata layer, never in a sentence; the lookbehind spares
    # the legitimate {/[ contexts and multi-ref commas.
    "node-id": (
        r"(?<![{\[,])\b(?:def|res|irf|thm|goal):[a-z][a-z0-9-]{2,}",
    ),
}


# ---------------------------------------------------------------------------
# The staged manuscript pipeline (the 2026-07-09 rebuild mandate)
# ---------------------------------------------------------------------------

#: Stage artifacts, per project (paths relative to ``manuscript_dir`` unless the
#: registry overrides). Each stage produces ONE inspectable artifact with a
#: schema below; each stage adds one kind of information; no stage silently
#: redoes an earlier stage's work (mandate §3).
STAGE_ARTIFACTS = {
    "spec": "manuscript_spec.json",            # B  projection specification
    "contracts": "section_contracts.json",     # C  structural resolution
    "reader_state": "reader_state.json",       # C  derived reader-state graph
    "narrative": "narrative",                  # D  narrative/<sid>.json dir
    "dispatches": "dispatches",                # E  compiled <sid>_dispatch.md dir
    "provenance": "prose_provenance",          # E  prose_provenance/<sid>.json dir
    "decisions": "decisions",                  # E/weld  decisions/<sid>.json dir
    "document_model": "document_model.json",   # F  derived document model
}

#: §5.1 — the global manuscript record (fixes the paper's contract once).
MANUSCRIPT_RECORD_FIELDS = (
    "manuscript_id", "working_title", "purpose", "research_question",
    "primary_contribution", "scope", "non_claims", "target_reader",
    "general_method", "embodiments", "evidence_classes", "notation",
    "terminology", "main_text_budget", "appendix_policy", "document_profile",
    "genre",
)

#: §5.3 — equation-ledger entry (derived from conceptric nodes carrying
#: ``projection.latex_label``; ``role`` distinguishes definition / exact
#: identity / approximation / asymptotic / estimator / fitted / observation —
#: STRUCTURAL metadata, never a rhetorical performance in prose).
EQUATION_LEDGER_FIELDS = (
    "label", "node", "role", "symbols", "assumptions", "validity",
    "established_by", "used_by", "section", "display", "numbered",
)

#: §5.5 / §5.6 — figure and table specifications: semantic objects settled at
#: the projection stage. The CAPTION is spec content (the four-question caption
#: law), settled before any prose exists — a renderer never invents what a
#: figure is trying to say.
FIGURE_SPEC_FIELDS = (
    "figure_id", "node", "question_answered", "function", "inputs", "panels",
    "data_sources", "epistemic_labels", "caption", "placement", "width",
    "generator", "status",                       # status: banked | deferred
)
TABLE_SPEC_FIELDS = (
    "table_id", "question_answered", "row_semantics", "column_semantics",
    "inputs", "ordering", "units", "caption", "placement", "width", "home",
)

#: §6.1 — the section contract. ``entry_state``/``exit_state`` are the reader
#: model: what may be assumed on entry, what must be established by exit.
SECTION_CONTRACT_FIELDS = (
    "section_id", "title", "function", "question_answered",
    "entry_state", "exit_state", "nodes_in_order", "equations", "figures",
    "tables", "depends_on", "forward_uses", "permitted_recap", "citations",
)

#: §7.1 — one paragraph plan (the narrative specification's unit). The prose
#: realiser receives these CLOSED: nothing substantive is left to decide.
PARAGRAPH_FIELDS = (
    "paragraph_id", "section_id", "function", "input_nodes", "proposition",
    "explanation", "derivation_detail", "equation_anchor", "figure_anchor",
    "qualification", "from_previous", "to_next", "detail_level",
    "length_range", "citations",
)

#: §8.2 — machine-readable prose provenance, one record per generated paragraph.
PROSE_PROVENANCE_FIELDS = (
    "paragraph_id", "spec_id", "spec_ids", "nodes_realised", "equations", "qualifications",
    "citations",
)

#: The prose stage's clean preamble (mandate §13: the realiser receives ONLY the
#: closed narrative packet + registries + the voice profile — never the engine's
#: graded-node kernel, whose internal framing is exactly the §1.8 scaffolding
#: class the meta_leak gate polices).
PROSE_STAGE_PREAMBLE = (
    "You are the prose realiser for one manuscript section. You receive a closed "
    "narrative specification (paragraph plans), the section contract (reader "
    "entry and exit states), the semantic content of the objects each paragraph "
    "realises, the notation and terminology registries, and a voice profile.\n"
    "The plans fix scientific and evidential obligations, not the shape of the "
    "finished exposition. You own the section's argument and may reorder, merge "
    "or split plan material when that produces a more connected explanation. "
    "Carry every plan id into the rendered paragraph markers and provenance so "
    "the claims, assumptions, evidence and equations remain checkable. You decide "
    "sentence boundaries, syntax, paragraph rhythm, connective language and "
    "explanatory compression. No paragraph pattern, sentence pattern or numerical "
    "style quota is an acceptance rule. You do NOT decide scientific "
    "content, claims, assumptions, qualifications, evidence status, novelty, "
    "hierarchy, section purpose, equation content and anchors, figure purpose, or "
    "citation necessity - those are settled in the specification you received.\n"
    "When you meet an unresolved substantive question, return it as a typed "
    "issue against the owning stage; never repair it rhetorically. Realise every "
    "plan, but let the reasoning determine paragraph boundaries and order."
)

#: §11.5 — the voice failure-pattern DETECTOR lexicon: the catalogued failure
#: modes of the condemned generator, scanned post-render at the validation
#: boundary. DATA, like META_LEAK_PATTERNS - tune here, never in gate code.
#: This detector is a safeguard; the positive voice profile remains the only
#: generative voice input. (The retired slop-vocabulary blacklist is
#: deliberately NOT here: a blacklist breeds synonyms, mandate §1.10 - these
#: classes are structural.)
VOICE_FAILURE_PATTERNS: dict[str, tuple[str, ...]] = {
    # §1.1 the prose adjudicates itself
    "self-adjudication": (
        r"\bproperly (graded|bounded|scoped)\b", r"\bresponsibly (bounded|stated)\b",
        r"\bappropriately demoted\b", r"\bhas earned\b", r"\bthe status it deserves\b",
        r"\bwe state (this )?plainly\b", r"\bepistemic posture\b",
    ),
    # §1.2 the narrator stands between reader and science
    "narrator-visible": (
        r"\bthe paper (now )?turns\b", r"\bwhat matters here\b",
        r"\bwe keep (this|it) secondary\b", r"\bthe claim the paper hangs on\b",
        r"\bthe remainder follows this grading\b", r"\bthe truthful shape\b",
        r"\bthis section (explores|discusses|examines)\b",
        r"\bhaving established the above\b", r"\bwith this in hand\b",
    ),
    # §1.7 polished opposition replacing mechanism
    "opposition-flourish": (
        r"\balgebraically free but statistically\b", r"\ba signal rather than an answer\b",
        r"\bone object, many readings\b", r"\bmethod before embodiment\b",
        r"\bfree but priced\b", r"\bnot .{1,30}, but rather\b",
    ),
    # §1.8 internal apparatus exposed as narrative
    "apparatus-exposed": (
        r"\binvention disclosure\b", r"\bclaim ledger\b", r"\bvalidation matrix\b",
        r"\bexactness taxonomy\b", r"\bterminology registry\b", r"\breader-state\b",
        r"\bnarrative specification\b", r"\bparagraph plan\b",
    ),
    # profile surface invariants (his rulings, verified post-render - the
    # punctuation half of the retired Vonnegut rule is his stated preference)
    "surface-invariant": (
        r"(?<!\\);", r"---", r"(?<!\-)--(?!\-)", "—", "–",
    ),
    # 2026-07-09, his read of the first staged fragments: the PATTERN survives
    # lexicon substitution (§1.10 live) - the narrator re-emerges with fresh
    # words. These classes generalise the observed instances. They are the
    # weld's kill-list and the boundary detector's floor, tuned to spare
    # literal resource-cost language (this paper's legitimate subject).
    "document-deixis": (
        r"\b(at|by|toward|near) the end of (this|the) section\b",
        r"\b(earlier|later|elsewhere) in (this|the) (section|paper)\b",
        r"\bwaits? for\b", r"\btreated below\b", r"\bderived below\b",
        r"\bcarried (from|forward to) the (previous|next) section\b",
        r"\breturned to (below|later)\b", r"\bas promised\b",
    ),
    "meta-orientation": (
        r"^[^.]{0,80}\bthis section\b[^.]{0,80}\bso we (begin|start|turn|name)\b",
        r"\bwe (begin|start) (at|with|from)\b", r"\bwe name (them|it|these) before\b",
        r"\bbefore deriving\b", r"\bwe now (turn|return|proceed)\b",
        r"\bwe (defer|postpone)\b",
    ),
    "performative-honesty": (
        r"\brather than [^,.]{0,40}(silently|quietly|in passing)\b",
        r"\bnot (hidden|swept|glossed)\b", r"\bstated (plainly|plainly|literally|explicitly)\b",
        r"\bthe claim (that|we|this)\b", r"\bno [^,.]{0,30}claim (made|is made|extends)\b",
        r"\bwe (do not|never) (claim|assert|pretend)\b",
        r"\bhonest(ly)?\b",
    ),
    "opposition-closer": (
        r", (never|not) (a|an|the) [^,.;]{1,45}[.]\s*$",
        r"\ba [^,.;]{1,30} to (read|keep|watch), not (a|an) [^,.;]{1,30}[.]",
        r"- [^,.;]{1,40}, (never|not) [^,.;]{1,40}[.]\s*$",
    ),
    "price-metaphor": (
        r"\bprice[sd]? (by|what|into|out)\b", r"\bpays? (in|for|out)\b",
        r"\bis priced\b", r"\bbuys?\b", r"\bspend[st]?\b(?! budget)",
        r"\bpurchas\w+\b", r"\bat [^,.;]{0,20} price\b",
    ),
}


# ---------------------------------------------------------------------------
# Phase F-wire — fold every component finding-kinds manifest into KIND_TO_WORK
# ---------------------------------------------------------------------------
#
# The Phase-B..I check modules each EXPORT a finding-kinds manifest that is the
# source of truth for its kinds. This section READS them (never re-enumerates the
# ~60 kinds) and routes each to its work kind, so no kind can reach
# ``propagate.intake_items`` unrouted — the door raises on an unrouted kind, so
# completeness here is mandatory. The imports are function-local: this leaf module
# keeps NO top-level ``laplace`` dependency, and no manifest module imports
# ``schema`` (verified: graph/canon and the other manifests never import it back),
# so the registration below runs at import with no cycle.

#: The inverse of ``WORK_TO_LAYER``: an owning STAGE -> the work kind that resolves
#: to it. ``research-state`` has two work kinds (derive|simulate); a finding routed
#: by its owning stage means "new substance from the research state", so the inverse
#: picks ``derive`` (the simulate path stays reachable via the explicit
#: ``missing-simulation`` kind).
LAYER_TO_WORK = {
    "structural": "structure",
    "prose": "prose",
    "projection": "mint",
    "figures": "figure",
    "document": "render",
    "narrative": "narrative",
    "research-state": "derive",
}


def _work_for_stage(route: str | None) -> str | None:
    """A component manifest's route -> a work kind. Accepts either an owning STAGE
    (inverted via ``LAYER_TO_WORK``: B/C route by stage) or a work kind directly
    (D2/E/I1 route by work kind — ``render``/``prose``/…). ``None`` stays ``None``,
    the report-only sentinel. An unknown stage raises ``KeyError`` — loud by design.
    ``prose``/``narrative`` are fixed points (stage name == work-kind name), so the
    work-kind short-circuit is correct for them."""
    if route is None:
        return None
    if route in WORK_KINDS:          # already a work kind (house_style / reader routes)
        return route
    return LAYER_TO_WORK[route]      # an owning stage -> its work kind


def register_component_kinds() -> dict[str, "str | None"]:
    """Fold the Phase-B..I component finding-kinds manifests into ``KIND_TO_WORK``
    (idempotent). Returns the kinds it wired (kind -> work kind). Dedupe is by NAME:
    a kind shared across manifests (``citation-cluster``, ``figure-debris``,
    ``orthography-fork``) must carry the SAME route in each, or this raises — the
    mechanical guard against one kind routing two ways."""
    from laplace.pipeline import (
        apparatus_common,
        house_style,
        scaffold_wipe,
        visual_gate,
    )
    # the readers package __init__ re-exports a `roster` FUNCTION, which shadows the
    # submodule of the same name — so pull the manifest accessor by name, not the module.
    from laplace.pipeline.readers import finding_kinds_manifest as reader_finding_kinds

    wired: dict[str, "str | None"] = {}

    def put(kind: str, work: "str | None") -> None:
        if kind in KIND_TO_WORK and KIND_TO_WORK[kind] != work:
            raise ValueError(
                f"finding kind {kind!r} routed two ways: "
                f"{KIND_TO_WORK[kind]!r} vs {work!r} — a shared kind must route "
                "the same in every manifest")
        KIND_TO_WORK[kind] = work
        wired[kind] = work

    # B — scaffold-wipe (owning stage under 'primary')
    for kind, entry in scaffold_wipe.FINDING_KIND_STAGE.items():
        put(kind, _work_for_stage(entry["primary"]))
    # C — apparatus / coherence (stage direct; None = the report-only orthography fork)
    for kind, stage in apparatus_common.FINDING_KIND_STAGE.items():
        put(kind, _work_for_stage(stage))
    # D2 — visual gate (every kind -> document via the 'render' work kind)
    for row in visual_gate.routing_manifest():
        put(row["kind"], _work_for_stage(row["work_kind"]))
    # I1 — house style (KIND_ROUTES values are work kinds; None = the report-only fork)
    for kind, work in house_style.KIND_ROUTES.items():
        put(kind, _work_for_stage(work))
    # E — reader suite (each reader-owned kind carries its work kind)
    for row in reader_finding_kinds():
        put(row["kind"], _work_for_stage(row["work_kind"]))
    # DETECTOR-ORGANS (ARMING_2026-07-16) — the promised-but-absent detector, the
    # source-delta reader, and the meta-leak source-tier scrub each EXPORT a
    # {kind, stage} manifest; fold them the same way (route by owning stage). The
    # gap ledger CONSUMES kinds (empty manifest), so its fold is a no-op. Imported
    # function-locally, and none imports schema, so no cycle.
    from laplace.pipeline import promise_audit as _promise
    from laplace.pipeline import meta_leak_scrub as _mls
    from laplace.pipeline.readers import source_delta as _srcdelta
    for _mod in (_promise, _srcdelta, _mls):
        for row in _mod.finding_kinds_manifest():
            put(row["kind"], _work_for_stage(row["stage"]))
    return wired


def _extend_meta_leak_lexicon() -> None:
    """Fold Phase-B's internal-planning-object + narrator-self-narration pattern
    classes into ``META_LEAK_PATTERNS`` (core extension B flagged). The patterns are
    DATA owned by ``scaffold_wipe._PLANNING_OBJECT_PATTERNS`` — IMPORTED, never
    re-typed, so the one lexicon has one source. ``check_meta_leak`` scans the dict
    generically, so this widens the core gate across the planning-object surface
    with no gate-code change. Idempotent (assignment, not append)."""
    from laplace.pipeline.scaffold_wipe import _PLANNING_OBJECT_PATTERNS

    META_LEAK_PATTERNS["self-narration"] = tuple(
        _PLANNING_OBJECT_PATTERNS.get("self-narration", ()))
    META_LEAK_PATTERNS["planning-object"] = tuple(
        pat for cls, pats in _PLANNING_OBJECT_PATTERNS.items()
        if cls != "self-narration" for pat in pats)


register_component_kinds()
_extend_meta_leak_lexicon()


# ---------------------------------------------------------------------------
# G4 growth-stage refusal-router kinds (ARMING_2026-07-22, wave G4) — ADDITIVE
# ---------------------------------------------------------------------------
#
# The refusal router (``pipeline.demand.route_refusal``) mints typed feedback records
# from a REFUTED verdict and routes them through the one intake door
# (``propagate.intake_items``, which RAISES on an unrouted kind). The three friction
# classes of the manuscript FORM object route to the three growth stages:
#   CONTENT  → growth mining        → work kind ``mint`` (→ projection, already in
#                                     WORK_TO_LAYER; no new work-kind, so propagate.WORKERS
#                                     resolves and nothing existing is touched)
#   FORM     → the demand registry  → None (a registry edit is an author-gated comment,
#                                     the None idiom the desk-review kinds already use)
#   TENSION  → the goal-tension queue → None (a REGOAL/HOLD/REJECT ruling is his
#                                     jurisdiction, machine-proposed — not builder work)
# Registered with ``setdefault`` so an existing routing is never clobbered (touch nothing
# existing). No WORK_TO_LAYER row is added: ``mint`` is already mapped and the None kinds
# carry no work stage.
_GROWTH_REFUSAL_KINDS: dict[str, "str | None"] = {
    "growth-content": "mint",
    "growth-form": None,
    "growth-tension": None,
}
for _gk, _gw in _GROWTH_REFUSAL_KINDS.items():
    KIND_TO_WORK.setdefault(_gk, _gw)
