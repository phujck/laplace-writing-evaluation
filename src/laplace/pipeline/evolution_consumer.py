"""The evolution consumer — draft (never apply) evolution contracts from the
open conceptric-intent queue.

The G-3 route-to-conceptric verb (:func:`adjudicate.make_conceptric_intent`)
deposits TYPED, node-anchored intents onto ``<manuscript>/feedback/feedback.jsonl``
and :func:`review_surface.substrate_queue` surfaces the open ones. The apply
path already exists, mechanised, in :mod:`laplace.pipeline.evolve` (load a
contract, plan its records, execute under a truncate-back transaction). What was
missing is the CONSUMER between the queue and the operator: the map from an
open intent to a drafted ``evolution_plan.json`` the author can read, ratify,
and only THEN apply.

DRAFT-ONLY for CONCEPTRIC-intents (author ruling, binding; still in force). The
conceptric path drafts contracts and rehearses them (``evolve.execute`` at the
operator's default, which is a dry run); it has NO code path that executes an
apply. That is enforced STRUCTURALLY, not by discipline: the consumer never
passes the dry-run flag at all (so it can only ever get the safe default), never
invokes the apply CLI, and never writes the intent-resolving supersede record for
a conceptric-intent — nothing is consumed until the author ratifies and an apply
succeeds. The supersede record's shape is DESIGNED into ``RATIFY.md`` as the
post-apply step, not emitted here.

Draft-only explicitly superseded for the PROJECTION-intent (plan-altitude) path
(C3.5, Fork 8 ruled: ``PV-20260713T221204Z-weld-apply-bridge``, 2026-07-13). The
2026-07-12 fork-law amendment — "a derivable fork is unfinished work wearing a
fork's clothes… his correction is retrospective through the ledger, never
prospective through a queue" — GOVERNS OVER the older in-code draft-only law for
this path ONLY. :func:`apply_plan_proposals` auto-derives each open
projection-intent into a storyboard plan op and APPLIES it through the plan-ledger
door, writing :func:`adjudicate.make_intent_revocation` (the intent-resolving
supersede) + an :data:`adjudicate.RATIFIED_OPERATION` delta record. The
CONCEPTRIC path above is untouched by this repeal.

The intent → op-template map (the frame is fixed; the content comes from the
intent's payload + the node's conceptric neighbourhood):

- ``essence-wrong``   → a ``reshapes`` entry carrying ``edit-essence`` text.
- ``edge-missing``    → ``edges`` entries (``add-edge``) from the source node to
                        the derivable target(s).
- ``content-missing`` → a ``mints`` entry (``add-node`` + ``set-projection`` seed
                        + ``add-edge``\\ s) wiring the new node to the intent's
                        source node and, where derivable, the shared spine beat
                        via ``section_target`` (→ the projection's ``section_ref``
                        slot, SKILL.md step 5).
- any other kind (``grade-wrong``, free-text ``other``, …) → NO draft; an
  escalation entry in the report.

The MECHANICAL grade rule for a minted node (binding, made concrete): the grade
is the MODAL grade of the node's edge-neighbours at mint, floored at the minimum
neighbour grade, ties resolving DOWN; with no neighbours it falls to the
corpus's minimum live grade (the documented bounded default). The conceptric
stores NO grade field — grade is DERIVED by :func:`corpus_ingest.dep_grade`
(derivational depth + spine elevation), surfaced as the integer ``"grade"`` key
on neighbourhood/view nodes. So the rule's output is an ADVISORY the author
sanity-checks placement against; it rides the mint as an informational ``grade``
key (which :func:`evolve.plan_records` ignores) and is stated in ``RATIFY.md``.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from laplace.research import corpus_ingest as _ci
from laplace.pipeline import adjudicate as _adj
from laplace.pipeline import evolve as _evolve

# the intent kinds this consumer has an op-template for; every other kind
# (grade-wrong, the free-text 'other', anything unrecognised) escalates.
DRAFTABLE_INTENTS = ("essence-wrong", "edge-missing", "content-missing")

# the seven build-completion gates the evolution contracts invoke by name
# (verify.check_conceptric_build): the five conceptric gates + the plan
# validator + the dirty report. Named here for the RATIFY.md PREVIEW — text
# only, the consumer NEVER executes a gate.
SEVEN_GATES = ("connectivity", "projection_labels", "glossary", "substrate",
               "figures", "plan_validator", "dirty_report")

_MINT_KIND_DEFAULT = "derivation-step"   # a LOGICAL_KINDS member (corpus_ingest)


# ---------------------------------------------------------------------------
# the queue reader — REUSE the substrate_queue matching, do not reimplement it
# ---------------------------------------------------------------------------

def open_intents(records: list[dict]) -> list[dict]:
    """The live, open conceptric-intent records — the exact semantics
    :func:`review_surface.substrate_queue` reads: :func:`adjudicate.live`
    (non-superseded; a ``revoke-intent`` drops its target) filtered to the
    ``CONCEPTRIC_INTENT`` record kind. The ``status == "open"`` guard mirrors
    the record's own field (:func:`adjudicate.make_conceptric_intent` stamps
    ``"open"``; the queue is retired by supersession, never by mutation)."""
    return [r for r in _adj.live(records)
            if r.get("record") == _adj.CONCEPTRIC_INTENT
            and r.get("status", "open") == "open"]


def open_projection_intents(records: list[dict]) -> list[dict]:
    """The live, open projection-intent records — the PLAN-altitude sibling of
    :func:`open_intents`. Same live semantics (:func:`adjudicate.live`:
    non-superseded; a ``revoke-intent`` drops its target) filtered to the
    ``PROJECTION_INTENT`` record kind. These type a whole-artefact/plan finding
    to the plan; :func:`draft_plan_proposals` renders them into a
    ``PLAN_PROPOSALS.md`` PREVIEW (the read side).

    This is also the APPLY side's work-list: draft-only is superseded for the
    projection-intent path (C3.5, Fork 8 ruled:
    ``PV-20260713T221204Z-weld-apply-bridge``; the 2026-07-12 fork-law amendment
    governs), so :func:`apply_plan_proposals` auto-derives every row returned here
    and applies the derivable ones through the storyboard plan-ledger door. A
    consumed intent leaves this list by its :func:`adjudicate.make_intent_revocation`
    — retirement is still supersession, never mutation, so the author's correction
    stays retrospective through the ledger. The draft-only law is UNTOUCHED for
    conceptric-intents (:func:`open_intents` / :func:`draft_contract`)."""
    return [r for r in _adj.live(records)
            if r.get("record") == _adj.PROJECTION_INTENT
            and r.get("status", "open") == "open"]


# ---------------------------------------------------------------------------
# the mechanical grade rule (pure — directly unit-tested)
# ---------------------------------------------------------------------------

def mint_grade(neighbour_grades: list[int], default_grade: int = 0) -> int:
    """The grade a minted node takes: the MODAL neighbour grade, floored at the
    minimum neighbour grade, ties resolving DOWN. No neighbours → the bounded
    default (the caller passes the corpus's minimum live grade).

    {2, 2, 3} → 2 (mode 2). {1, 3} tie → 1 (the lower of the tied modes). []
    → ``default_grade``."""
    grades = [int(g) for g in neighbour_grades if g is not None]
    if not grades:
        return int(default_grade)
    counts = Counter(grades)
    top = max(counts.values())
    modes = [g for g, c in counts.items() if c == top]
    mode = min(modes)                     # ties resolve DOWN
    return max(mode, min(grades))         # floored at the minimum neighbour grade


def min_live_grade(net: dict | None) -> int:
    """The corpus's minimum live grade — the documented bounded default for a
    neighbourless mint. Empty/absent net → 0 (a floor node)."""
    if not net or not net.get("nodes"):
        return 0
    dg = _ci.dep_grade(net)
    return min(dg.values()) if dg else 0


def _grade_map(net: dict | None) -> dict[str, int]:
    if not net or not net.get("nodes"):
        return {}
    return _ci.dep_grade(net)


def _net_nodes(net: dict | None) -> set[str]:
    return set((net or {}).get("nodes") or {})


# ---------------------------------------------------------------------------
# op-template helpers — content from the payload + the node's neighbourhood
# ---------------------------------------------------------------------------

def _slug(text: str, fallback: str = "node") -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (s or fallback)[:48]


# The id prefix IS the stable kind vocabulary (projection_spec.py:92 — ids are
# kind-prefixed); map a minted id's prefix onto its LOGICAL_KINDS node_kind so a
# ``mint ref:foo`` note yields a citation, not a derivation-step. Unlisted prefixes
# fall to the derivation-step default (the neutral content node).
_PREFIX_TO_KIND = {
    "ref": "citation", "def": "definition", "thm": "theorem", "lemma": "lemma",
    "res": "result", "result": "result", "postulate": "postulate",
    "technique": "technique", "portal": "portal", "support": "support",
    "goal": "goal", "derivation": "derivation-step", "irf": "intermediate-result",
    "ds": "derivation-step",
}

# An explicit ``mint <prefix>:<slug>`` token in the note names the node id verbatim
# (the author's ratified identity, e.g. "content-missing: mint ref:scale-space-theory").
# A node id is kind-prefixed and space-free, so the token match is exact.
_MINT_ID_RE = re.compile(r"\bmint\s+([a-z][a-z0-9]*:[a-z0-9][a-z0-9\-]*)",
                         re.IGNORECASE)


def _mint_id_and_kind(note: str, source: str) -> tuple[str, str]:
    """Derive a content-missing mint's ``(id, node_kind)``. An explicit
    ``mint <prefix>:<slug>`` token in the note names the id verbatim, and the id
    PREFIX selects the node_kind (a ``ref:`` mint is a citation, not a whole-note
    slug under ``derivation:``). Absent an explicit token, fall back to the prior
    behaviour: the derivation-namespaced slug of the note."""
    m = _MINT_ID_RE.search(note or "")
    if m:
        nid = m.group(1)
        prefix = nid.split(":", 1)[0].lower()
        return nid, _PREFIX_TO_KIND.get(prefix, _MINT_KIND_DEFAULT)
    nid = f"{_MINT_KIND_DEFAULT.split('-')[0]}:{_slug(note or source, 'content')}"
    return nid, _MINT_KIND_DEFAULT


def _mint_id_from_quote(quote: str, note: str, source: str) -> tuple[str, str]:
    """The CONTENT-DERIVED mint id (the RATIFY-queue defect D1, 2026-07-19): a
    batch of intents sharing one generic issue-note slugs to ONE COLLIDING id.
    When the intent carries mined substrate (``gap.quote``), the id slugs from
    the QUOTE — unique per substance, stable per re-draft. An explicit
    ``mint <prefix>:<slug>`` token in the note still wins (the author's named
    identity outranks any derivation)."""
    m = _MINT_ID_RE.search(note or "")
    if m or not (quote or "").strip():
        return _mint_id_and_kind(note, source)
    nid = f"{_MINT_KIND_DEFAULT.split('-')[0]}:{_slug(quote, 'content')}"
    return nid, _MINT_KIND_DEFAULT


def _note(intent: dict) -> str:
    return (intent.get("payload") or {}).get("note") or ""


def _source_node(intent: dict) -> str:
    return intent.get("node") or intent.get("node_id") or ""


def _mentioned_nodes(note: str, known: set[str], exclude: str = "") -> list[str]:
    """Node ids named verbatim in the note that resolve to real nodes (the
    deterministic 'where derivable' — a node id never contains whitespace, so a
    token match is exact)."""
    toks = set(re.split(r"[\s,;()]+", note or ""))
    return [n for n in known if n in toks and n != exclude]


def _section_ref_of(net: dict | None, node: str) -> str:
    """The shared spine beat a node is placed on (its projection ``section_ref``),
    the anchor SKILL.md step 5 wires a mint to. Empty when not derivable."""
    n = ((net or {}).get("nodes") or {}).get(node) or {}
    return (n.get("projection") or {}).get("section_ref") or ""


def _spine_beat(net: dict | None) -> str:
    """The first shared spine beat, the fallback anchor when the source node
    carries no section_ref."""
    spine = (net or {}).get("spine") or []
    return spine[0].get("id") if spine and isinstance(spine[0], dict) else ""


# ---------------------------------------------------------------------------
# the intent → contract draft
# ---------------------------------------------------------------------------

def _meta(corpus: str) -> dict:
    return {
        "project": corpus,
        "from_version": {"name": "current"},
        "to_version": {"name": "drafted"},
        "contract": "canon://skills/conceptric_evolution",
    }


# ---------------------------------------------------------------------------
# the fitness stamp (P3) — a LIGHT summary of the fitness panel, fields only.
# The rule (ψ) and the threshold (φ) are HIS; this stamps READINGS, never a
# verdict — no threshold, no ordering. It rides a drafted contract's meta (the
# fitness AT DRAFT time) and the ratify queue's payload (fitness NOW), so his
# ratification read sees whether the readings moved since the draft was cut.
# ---------------------------------------------------------------------------

def _fitness_light(f: dict | None) -> dict | None:
    """A light summary of a :func:`fitness_panel.read_fitness` result:
    ``{debt_n, freeze_pass, r10_clean, at}``. ``None`` when the panel is absent /
    not present — the declared empty, never a fabricated number."""
    if not f or not f.get("present"):
        return None
    traj = f.get("debt_trajectory") or []
    last = traj[-1] if traj else {}
    r10 = f.get("r10_clean")
    if r10 is None and isinstance(f.get("freeze"), dict):
        r10 = f["freeze"].get("mechanical_pass")
    return {"debt_n": last.get("n"),
            "freeze_pass": (f.get("freeze") or {}).get("pass"),
            "r10_clean": r10,
            "at": last.get("at") or f.get("at")}


def _read_fitness_safe(corpus: str, repo_root: Path | str | None) -> dict | None:
    """One :func:`fitness_panel.read_fitness` call, degrading to ``None`` on any
    failure (an unregistered corpus, an absent panel) — the stamp is advisory."""
    try:
        from laplace.pipeline import fitness_panel as fp
        return fp.read_fitness(corpus, repo_root if repo_root else ".")
    except Exception:
        return None


def _draft_sections(intent: dict, net: dict | None) -> tuple[dict, dict]:
    """Map ONE draftable intent to its contract sections + a draft-detail block
    (the grade advisory, the derivation notes). Returns (sections, detail).
    Raises :class:`ValueError` when the template cannot be filled (→ escalation)."""
    kind = intent.get("intent") or "other"
    note = _note(intent)
    source = _source_node(intent)
    known = _net_nodes(net)
    gmap = _grade_map(net)
    detail: dict[str, Any] = {"template": kind, "source_node": source}

    if kind == "essence-wrong":
        if not source:
            raise ValueError("essence-wrong intent carries no source node")
        if not note.strip():
            raise ValueError("essence-wrong intent carries no note to draft the "
                             "corrected essence from")
        detail["note_is_proposed_essence"] = True
        return {"reshapes": [{"id": source, "essence": note.strip()}]}, detail

    if kind == "edge-missing":
        if not source:
            raise ValueError("edge-missing intent carries no source node")
        targets = _mentioned_nodes(note, known, exclude=source)
        if not targets and net is not None:
            # fall back to the node's unconfirmed derives-from candidates
            nb = _ci.neighborhood(net, source)
            targets = [b["id"] for b in nb.get("below", [])
                       if b.get("prov") == "candidate"]
        if not targets:
            raise ValueError("edge-missing intent names no derivable target node "
                             "(none in the note, no neighbourhood candidate)")
        detail["edge_direction"] = f"{source} derives-from <target> (author flips if reversed)"
        detail["targets"] = targets
        return {"edges": [{"node": source, "target": t} for t in targets]}, detail

    if kind == "content-missing":
        # the id: an explicit `mint <prefix>:<slug>` note token wins; else the
        # CONTENT-derived slug from the mined substrate (defect D1: a shared
        # generic note must never collide a batch onto one id); else the note.
        gap_quote = str(((intent.get("gap") or {}).get("quote")) or "")
        nid, node_kind = _mint_id_from_quote(gap_quote, note, source)
        # wire the mint to the intent's source node (+ the shared spine beat).
        # An explicit per-intent `section_target` outranks derivation (defect
        # D2: a generic source node falls back to the spine beat — the caller
        # who KNOWS the owning section says so on the intent).
        edges = [source] if source else []
        section_ref = (str(intent.get("section_target") or "")
                       or _section_ref_of(net, source) or _spine_beat(net))
        neighbour_targets = list(edges)
        if section_ref and section_ref in known:
            neighbour_targets.append(section_ref)
        neighbour_grades = [gmap[t] for t in neighbour_targets if t in gmap]
        grade = mint_grade(neighbour_grades, default_grade=min_live_grade(net))
        # THE MINED SUBSTRATE (the growth leg's quarry law, 2026-07-19): a
        # source-delta gap rides its intent with the LOST SPAN verbatim
        # (``gap.quote`` — the source-aware quarry probed his draft, where the
        # span lives). That span IS the essence the mint exists to carry; the
        # issue-note is only the finding's description of the loss. Seed the
        # essence from the quote when present so the drafted node grows the
        # conceptric from HIS text, and his ratification read sees the substance,
        # not just the diagnosis.
        quote = str(((intent.get("gap") or {}).get("quote")) or "").strip()
        mint = {
            "id": nid,
            "node_kind": node_kind,
            "essence_seed": quote or note.strip() or f"content for {source}",
            "edges": edges,
            "grade": grade,                # advisory only — plan_records ignores it
        }
        if quote:
            detail["mined_substrate"] = quote
            detail["substrate_provenance"] = "gap.quote (the lost span, verbatim from the source draft)"
        if section_ref:
            mint["section_target"] = section_ref   # → projection.section_ref
        detail.update({"minted_node": nid, "grade": grade,
                       "grade_rule": "modal neighbour grade, floored at min, ties DOWN",
                       "neighbour_grades": neighbour_grades,
                       "section_ref": section_ref})
        return {"mints": [mint]}, detail

    raise ValueError(f"no op-template for intent kind {kind!r}")


def _gate_preview(sections: dict) -> dict[str, str]:
    """Text-only PREVIEW: which of the seven gates the draft plausibly stresses.
    No gate is executed here — this is a reading aid for the author."""
    stresses: dict[str, str] = {}
    if sections.get("mints"):
        stresses["connectivity"] = "new node must reach a spine beat (else orphan)"
        stresses["projection_labels"] = "the mint's projection seed mints latex_label at birth"
        stresses["substrate"] = "add-node changes the live node set"
        stresses["plan_validator"] = "the new node needs placement in a section"
        stresses["dirty_report"] = "the anchoring section reprojects"
    if sections.get("edges"):
        stresses["connectivity"] = "new derives-from edges change reachability"
        stresses["substrate"] = "the edge set changes"
    if sections.get("reshapes"):
        stresses["glossary"] = "an essence rewrite may touch deprecated terms"
        stresses["substrate"] = "an essence edit changes node content"
    return {g: stresses.get(g, "not plausibly stressed") for g in SEVEN_GATES}


def _rehearsal(corpus: str, evo_dir: Path,
               repo_root: Path | str | None) -> dict:
    """The dry-run rehearsal. Calls :func:`evolve.execute` WITHOUT the
    ``dry_run`` flag — the operator's default is ``True``, so the consumer can
    only ever rehearse, never apply. Best-effort: an unregistered corpus / a
    ledger-less project is reported as skipped, not raised."""
    try:
        return _evolve.execute(corpus, evo_dir, repo_root=repo_root)
    except Exception as e:  # noqa: BLE001 — the rehearsal is advisory, never fatal
        return {"ok": None, "skipped": True, "reason": str(e)}


def _ratify_md(intent: dict, corpus: str, contract: dict, records: list[dict],
               detail: dict, gate_preview: dict, rehearsal: dict) -> str:
    """The author's ratification sheet — everything needed to ratify or reject,
    and the post-apply close-the-loop step DESIGNED but not executed."""
    intent_id = intent.get("id") or ""
    exp_added, exp_removed = _evolve._expected_delta(contract)
    op_kinds = Counter(r["kind"] for r in records)
    lines: list[str] = []
    lines.append(f"# RATIFY — {intent.get('intent')} on {_source_node(intent)!r}")
    lines.append("")
    lines.append("DRAFT-ONLY. Nothing below is applied. Ratify, then apply via "
                 "`scripts/evolve.py` yourself; the consumer never applies.")
    lines.append("")
    lines.append("## Intent")
    lines.append(f"- id: `{intent_id}`")
    lines.append(f"- kind: `{intent.get('intent')}`")
    lines.append(f"- node: `{_source_node(intent)}`")
    lines.append(f"- verbatim note: {_note(intent)!r}")
    lines.append(f"- by: `{intent.get('source') or ''}`  ts: `{intent.get('ts') or ''}`")
    lines.append("")
    if detail.get("mined_substrate"):
        lines.append("## Mined substrate (the essence the mint carries)")
        lines.append(f"- provenance: {detail.get('substrate_provenance')}")
        lines.append("")
        lines.append(f"> {detail['mined_substrate']}")
        lines.append("")
    ctx = str(((intent.get("gap") or {}).get("context")) or "")
    if ctx:
        lines.append("## Source context (his ask, 2026-07-19: \"generally I need the "
                     "context of what I said\" — the surrounding source passage, verbatim)")
        lines.append("")
        for cl in ctx.splitlines():
            lines.append(f"> {cl}" if cl.strip() else ">")
        lines.append("")
    lines.append("## Drafted ops (evolve.plan_records)")
    for r in records:
        lines.append(f"- `{r['kind']}` node=`{r.get('node')}`"
                     + (f" target=`{r.get('target')}`" if r.get("target") else "")
                     + (f" value=`{json.dumps(r.get('value'))}`" if r.get("value") else ""))
    lines.append(f"- op-kind counts: `{dict(op_kinds)}`")
    lines.append("")
    if "grade" in detail:
        lines.append("## Minted-node grade (mechanical rule, advisory)")
        lines.append(f"- rule: {detail['grade_rule']}")
        lines.append(f"- neighbour grades: `{detail.get('neighbour_grades')}`")
        lines.append(f"- computed grade: **{detail['grade']}** "
                     "(the conceptric derives grade from edges; this is the "
                     "grade the mint will land at, for sanity-check)")
        lines.append("")
    lines.append("## Expected delta (evolve._expected_delta)")
    lines.append(f"- added: `{sorted(exp_added)}`")
    lines.append(f"- removed: `{sorted(exp_removed)}`")
    lines.append("")
    lines.append("## Gate PREVIEW (seven build-completion gates — text only, none executed)")
    for g in SEVEN_GATES:
        lines.append(f"- `{g}`: {gate_preview[g]}")
    lines.append("")
    lines.append("## Dry-run rehearsal (evolve.execute, dry_run default True)")
    if rehearsal.get("skipped"):
        lines.append(f"- skipped: {rehearsal.get('reason')}")
    else:
        for k in ("ok", "round_trip_exact", "already_applied", "records",
                  "before_count", "after_count", "added", "removed", "error"):
            if k in rehearsal:
                lines.append(f"- {k}: `{rehearsal[k]}`")
    lines.append("")
    lines.append("## Close the loop (POST-APPLY — the consumer does NOT write this)")
    lines.append("Once ratified AND the apply round-trips, retire the consumed "
                 "intent by appending its supersede to `feedback/feedback.jsonl`:")
    lines.append("")
    lines.append("```python")
    lines.append("from laplace.pipeline import adjudicate")
    lines.append(f"adjudicate.make_intent_revocation({intent_id!r}, "
                 f"reason='consumed by evolution', project={corpus!r})")
    lines.append("```")
    lines.append("")
    lines.append("`adjudicate.live` drops any record named by a later "
                 "`supersedes`, so appending this retires the intent from the "
                 "substrate queue on the next read.")
    return "\n".join(lines) + "\n"


def draft_contract(intent: dict, net: dict | None, corpus: str,
                   out_dir: Path | str,
                   repo_root: Path | str | None = None) -> dict:
    """Draft ONE open conceptric-intent into an evolution contract directory.

    Writes ``<out_dir>/evolutions/<slug>_<date>/evolution_plan.json`` (conforming
    EXACTLY to :func:`evolve.load_contract`) plus ``RATIFY.md`` (the intent id +
    verbatim note, the drafted ops, the expected delta, the seven-gate preview,
    the dry-run rehearsal, and the DESIGN of the post-apply supersede step).

    Returns a draft record on success, or an escalation record
    (``{"escalated": True, ...}``) when the intent has no op-template or its
    template cannot be filled — nothing is written for an escalation."""
    kind = intent.get("intent") or "other"
    intent_id = intent.get("id") or ""
    if kind not in DRAFTABLE_INTENTS:
        return {"escalated": True, "intent_id": intent_id, "intent": kind,
                "node": _source_node(intent),
                "reason": f"no op-template for {kind!r} (free-text/other or "
                          "grade-wrong routes to the author)"}
    try:
        sections, detail = _draft_sections(intent, net)
    except ValueError as e:
        return {"escalated": True, "intent_id": intent_id, "intent": kind,
                "node": _source_node(intent), "reason": str(e)}

    date = (intent.get("ts") or _dt.date.today().isoformat())[:10]
    # The intent id is the disambiguator: two same-kind intents on the same
    # node the same day must NEVER share a dir — the second draft silently
    # overwrote the first while the batch summary reported both (the judge's
    # probe). And a dir that still exists is refused, never clobbered.
    tail = _slug(intent_id.rsplit("-", 1)[-1], "i") if intent_id else "i"
    slug = f"{kind}_{_slug(_source_node(intent) or intent_id, intent_id)}_{tail}"
    evo_dir = Path(out_dir) / "evolutions" / f"{slug}_{date}"
    if (evo_dir / "evolution_plan.json").exists():
        return {"escalated": True, "intent_id": intent_id, "intent": kind,
                "node": _source_node(intent),
                "reason": f"draft dir already holds a contract: {evo_dir} — "
                          "refusing to overwrite; ratify or remove it first"}
    evo_dir.mkdir(parents=True, exist_ok=True)

    meta = _meta(corpus)
    # P3: stamp the fitness readings AT DRAFT time onto the contract meta (one
    # fitness_panel call; None on absence). Fields only — no threshold, no ordering.
    meta["fitness_at_draft"] = _fitness_light(_read_fitness_safe(corpus, repo_root))
    contract = {"meta": meta, **sections}
    (evo_dir / "evolution_plan.json").write_text(
        json.dumps(contract, indent=2, ensure_ascii=False), encoding="utf-8")

    # load it back the way the operator will, then plan + rehearse
    loaded = _evolve.load_contract(evo_dir)
    records = _evolve.plan_records(loaded)
    rehearsal = _rehearsal(corpus, evo_dir, repo_root)
    gate_preview = _gate_preview(sections)
    (evo_dir / "RATIFY.md").write_text(
        _ratify_md(intent, corpus, loaded, records, detail, gate_preview,
                   rehearsal), encoding="utf-8")

    return {"escalated": False, "intent_id": intent_id, "intent": kind,
            "node": _source_node(intent), "evolution_dir": str(evo_dir),
            "op_kinds": dict(Counter(r["kind"] for r in records)),
            "records": len(records), "grade": detail.get("grade"),
            "rehearsal_ok": rehearsal.get("ok")}


# ---------------------------------------------------------------------------
# the projection-intent draft — a PLAN PROPOSAL, DRAFT-ONLY (no apply, no op)
# ---------------------------------------------------------------------------

# The plan verb → the storyboard op it maps to (schema.PLAN_OP_KINDS vocabulary),
# with a one-line rationale template. A meta-object verb maps to a `set-meta` merge;
# a section-object verb maps to the structural op that carries it.
#
# DRAFT-ONLY SUPERSEDED HERE (C3.5, Fork 8: PV-20260713T221204Z-weld-apply-bridge;
# the 2026-07-12 fork-law amendment governs for the projection-intent path). This
# map is BOTH the reading aid `draft_plan_proposals` renders AND the derivation
# `apply_plan_proposals` executes: a DERIVABLE op (a resolved meta target under a
# verb with a mechanical transform) is now applied through the storyboard plan-
# ledger door. The old "nothing here mutates a plan or a ledger" invariant no
# longer holds for the plan-altitude path; it still holds for conceptric-intents.
_VERB_TO_PROPOSED_OP = {
    "CUT":     {"meta": "set-meta", "section": "remove-node"},
    "DEMOTE":  {"meta": "set-meta", "section": "reorder-sections"},
    "SPLIT":   {"meta": "set-meta", "section": "set-nodes"},
    "REORDER": {"meta": "set-meta", "section": "reorder-sections"},
    "REOPEN":  {"meta": "set-meta", "section": "add-node"},
    "RESPINE": {"meta": "set-meta", "section": "set-nodes"},
    "RESTART": {"meta": "set-meta", "section": "set-nodes"},
}


def _proposed_plan_op(intent: dict) -> dict:
    """Map ONE open projection-intent to a PROPOSED plan op (advisory). Returns
    ``{verb, object_kind, object_key, proposed_op, note, finding_kind}`` — the
    row a PLAN PROPOSAL renders. Never executes; ``proposed_op`` is a
    :data:`schema.PLAN_OP_KINDS` handle the author applies by hand if ratified."""
    verb = intent.get("verb") or "CUT"
    obj = intent.get("object") or {}
    object_kind = obj.get("kind") or "meta"
    object_key = obj.get("sid") or obj.get("key") or ""
    payload = intent.get("payload") or {}
    proposed = _VERB_TO_PROPOSED_OP.get(verb, {}).get(object_kind, "set-meta")
    return {"id": intent.get("id") or "", "verb": verb, "object_kind": object_kind,
            "object_key": object_key, "proposed_op": proposed,
            "target": intent.get("target") or "",
            "note": payload.get("note") or "",
            "finding_kind": payload.get("finding_kind") or "",
            "by": intent.get("source") or "", "ts": intent.get("ts") or ""}


def _plan_proposals_md(corpus: str, rows: list[dict]) -> str:
    """The author's PLAN PROPOSAL sheet — every open projection-intent as the plan
    op it maps to. This is the READ side (the preview); the APPLY side is
    :func:`apply_plan_proposals` (C3.5, Fork 8: PV-20260713T221204Z-weld-apply-
    bridge). Mirrors :func:`_ratify_md`'s close-the-loop design for the substrate
    queue."""
    lines: list[str] = []
    lines.append(f"# PLAN PROPOSALS — {corpus}")
    lines.append("")
    lines.append("PREVIEW. Each row is the plan op an open projection-intent maps "
                 "to. A DERIVABLE op (a resolved meta target under a verb with a "
                 "mechanical transform) is APPLIED by `apply_plan_proposals` "
                 "through the storyboard plan-ledger door — which then writes the "
                 "intent-resolving supersede (`make_intent_revocation`) + a "
                 "`ratified-operation` delta record. An un-derivable op (unresolved "
                 "object, RESTART, SPLIT, or a section op) applies NOTHING and is "
                 "recorded needs-author, kept open. The in-code draft-only law is "
                 "explicitly superseded for this plan-altitude path only "
                 "(2026-07-12 fork-law amendment governs); it still holds for "
                 "conceptric-intents.")
    lines.append("")
    if not rows:
        lines.append("_No open projection-intents in the queue._")
        return "\n".join(lines) + "\n"
    for r in rows:
        lines.append(f"## `{r['verb']}` {r['object_kind']}:`{r['object_key']}`")
        lines.append(f"- intent id: `{r['id']}`")
        lines.append(f"- rules on finding: `{r['target']}`"
                     + (f" (kind `{r['finding_kind']}`)" if r["finding_kind"] else ""))
        lines.append(f"- PROPOSED plan op: `{r['proposed_op']}` on "
                     f"{r['object_kind']} `{r['object_key']}` "
                     "(applied by `apply_plan_proposals` when derivable)")
        if r["note"]:
            lines.append(f"- note: {r['note']!r}")
        lines.append(f"- by: `{r['by']}`  ts: `{r['ts']}`")
        lines.append("")
    lines.append("## Close the loop (the apply bridge writes this)")
    lines.append("`apply_plan_proposals` applies each DERIVABLE op through the "
                 "storyboard plan-ledger door and retires the consumed intent by "
                 "appending its supersede (`make_intent_revocation`) + a "
                 "`ratified-operation` delta record to `feedback/feedback.jsonl`:")
    lines.append("")
    lines.append("```python")
    lines.append("from laplace.pipeline import evolution_consumer")
    lines.append(f"evolution_consumer.apply_plan_proposals('<manuscript dir>', "
                 f"{corpus!r}, by='gerard')")
    lines.append("```")
    return "\n".join(lines) + "\n"


def draft_plan_proposals(intents: list[dict], corpus: str,
                         out_dir: Path | str) -> dict:
    """Render EVERY open projection-intent into a PREVIEW ``PLAN_PROPOSALS.md`` under
    ``out_dir`` — the plan-altitude sibling of :func:`draft_contract`. Each intent
    becomes the plan op it maps to (verb + object + note). This is the READ side and
    STAYS a pure markdown render — it executes nothing, touches no ledger. The APPLY
    side is :func:`apply_plan_proposals` (C3.5, Fork 8:
    ``PV-20260713T221204Z-weld-apply-bridge``); the draft-only law is superseded for
    the projection-intent path THERE, not here. Returns a summary
    ``{"proposals": [...], "path": <PLAN_PROPOSALS.md>}``; the empty-queue case
    still writes the sheet so its absence never reads as a stale queue."""
    rows = [_proposed_plan_op(i) for i in intents]
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    md_path = out / "PLAN_PROPOSALS.md"
    md_path.write_text(_plan_proposals_md(corpus, rows), encoding="utf-8")
    return {"proposals": rows, "path": str(md_path)}


# ---------------------------------------------------------------------------
# the batch driver — every open intent in a manuscript's ledger
# ---------------------------------------------------------------------------

def _feedback_ledger(manuscript_dir: Path) -> Path:
    return manuscript_dir / "feedback" / "feedback.jsonl"


def consume(manuscript_dir: Path | str, corpus: str, net: dict | None,
            out_dir: Path | str,
            repo_root: Path | str | None = None) -> dict:
    """Draft contracts for EVERY open intent in a manuscript's feedback ledger.
    Returns ``{"drafted": [...], "escalated": [...], "plan_proposals": {...}}``.
    The conceptric intents draw evolution contracts (:func:`draft_contract`); the
    PLAN-altitude projection-intents draw a DRAFT ``PLAN_PROPOSALS.md``
    (:func:`draft_plan_proposals`). Draft-only throughout — nothing auto-applies."""
    from laplace.pipeline.ledger import read_jsonl
    md = Path(manuscript_dir)
    ledger = _feedback_ledger(md)
    records = read_jsonl(ledger) if ledger.is_file() else []
    drafted: list[dict] = []
    escalated: list[dict] = []
    for intent in open_intents(records):
        res = draft_contract(intent, net, corpus, out_dir, repo_root=repo_root)
        (escalated if res.get("escalated") else drafted).append(res)
    plan_proposals = draft_plan_proposals(
        open_projection_intents(records), corpus, out_dir)
    return {"drafted": drafted, "escalated": escalated,
            "plan_proposals": plan_proposals}


# ---------------------------------------------------------------------------
# the APPLY bridge — DRAFT-ONLY SUPERSEDED for the projection-intent path
# (C3.5, Fork 8 ruled: PV-20260713T221204Z-weld-apply-bridge; the 2026-07-12
# fork-law amendment governs). Auto-derive-and-apply with retrospective ledger
# correction: a DERIVABLE open projection-intent is executed through the
# storyboard plan-ledger door, the consumed intent is retired via
# make_intent_revocation, and a ratified-operation record banks the ACTUAL plan
# delta. An UN-DERIVABLE op applies NOTHING and is recorded needs-author (kept
# open). The draft-only law remains in force for conceptric-intents (draft_contract).
# ---------------------------------------------------------------------------

#: the verbs an apply REFUSES — no mechanical transform derivable from
#: (verb + resolved object) alone: RESTART re-plans the whole artefact from the
#: conceptric; SPLIT divides one section into two (which nodes go where is a
#: content judgment). Both route to needs-author regardless of object kind.
_UNDERIVABLE_VERBS = ("RESTART", "SPLIT")


def _plan_namespaces(plan: dict) -> tuple[set[str], set[str], str]:
    """The two live namespaces a projection-intent's object can name — REUSED from
    the C3.4 door (:func:`restart_reader._plan_target_namespaces`), never
    reimplemented: the section ids and the ``plan.meta`` keys. Resolving against the
    LIVE plan re-checks C3.4 at APPLY time — the plan may have moved since the intent
    was minted. Returns ``(sids, meta_keys, basis)``.

    FAIL-CLOSED on a structurally-defective plan (JSON-shaped but not plan-shaped:
    ``meta`` not a mapping, ``sections`` carrying a non-dict, …). The C3.4 door
    RAISES on that shape by design; here the raise is caught and the namespaces
    degrade to EMPTY with ``basis`` naming the defect
    (:data:`restart_reader.PLAN_UNREADABLE_BASIS`) — the same degradation C3.4 makes
    on the read side. Empty namespaces resolve NOTHING, so every intent routes to
    needs-author and stays open: a broken plan can never be mutated by this bridge,
    and it is loud in the ledger instead of escaping as an untyped ``AttributeError``
    that would take the whole apply run with it."""
    from laplace.pipeline.readers import restart_reader as _rr
    try:
        sids, meta_keys = _rr._plan_target_namespaces(plan)
    except Exception as exc:                      # JSON-shaped, not plan-shaped
        return set(), set(), f"{_rr.PLAN_UNREADABLE_BASIS}: {type(exc).__name__}: {exc}"
    return sids, meta_keys, ""


def _derive_projection_op(intent: dict, plan: dict) -> tuple[str | None, str, str, str]:
    """Classify ONE open projection-intent for the apply bridge. Returns
    ``(op_kind, object_kind, object_key, reason)``. ``op_kind is None`` ⇒
    un-derivable (needs-author) and ``reason`` names why; otherwise ``op_kind`` is
    the storyboard :data:`schema.PLAN_OP_KINDS` op to execute.

    Derivability (fail-closed):

    * a STRUCTURALLY-DEFECTIVE live plan refuses EVERY intent, with the C3.4
      ``plan-unreadable`` basis as the reason (nothing is applied to a plan the
      resolver cannot read);
    * the object must RESOLVE against the LIVE plan (C3.4) — an unaddressable meta
      key or section id is REFUSED (``"unresolved-object"``);
    * :data:`_UNDERIVABLE_VERBS` (RESTART, SPLIT) have no mechanical transform;
    * a ``meta`` object under any remaining verb maps to ``set-meta`` (the one
      cleanly-derivable transform: annotate the resolved meta key with the applied
      ruling, non-lossy);
    * a ``section`` object needs a node/order parameter the intent does not carry
      (content judgment) — recorded needs-author, not guessed."""
    verb = intent.get("verb") or "CUT"
    obj = intent.get("object") or {}
    object_kind = obj.get("kind") or "meta"
    object_key = obj.get("sid") or obj.get("key") or ""
    sids, meta_keys, basis = _plan_namespaces(plan)
    if basis:                                     # the plan itself is unreadable
        return None, object_kind, object_key, basis
    resolved = bool(object_key) and (
        object_key in (meta_keys if object_kind == "meta" else sids))
    if not resolved:
        return None, object_kind, object_key, "unresolved-object"
    if verb in _UNDERIVABLE_VERBS:
        return None, object_kind, object_key, f"no-mechanical-transform:{verb}"
    op_kind = _VERB_TO_PROPOSED_OP.get(verb, {}).get(object_kind)
    if object_kind == "meta" and op_kind == "set-meta":
        return "set-meta", object_kind, object_key, ""
    return None, object_kind, object_key, "content-judgment:section-op-needs-author"


def _apply_ruling_value(prior: object, intent: dict, *, by: str, ts: str) -> dict:
    """The non-lossy set-meta value for a derived meta op: the applied ruling wraps
    the resolved meta key, PRESERVING its prior value under ``value`` so the delta
    is reversible (append-only ledger) and no author content is destroyed."""
    payload = intent.get("payload") or {}
    return {
        "value": prior,                      # the prior meta[key], preserved
        "projection_ruling": {
            "verb": intent.get("verb") or "",
            "resolves": intent.get("target") or "",   # the R10 finding id
            "intent": intent.get("id") or "",
            "note": payload.get("note") or "",
            "finding_kind": payload.get("finding_kind") or "",
            "applied_by": by,
            "applied_ts": ts,
            "provenance": "C3.5 apply bridge "
                          "(PV-20260713T221204Z-weld-apply-bridge)",
        },
    }


def apply_plan_proposals(out_dir: Path | str, corpus: str, *, by: str,
                         feedback_path: Path | str | None = None) -> dict:
    """Auto-derive-and-apply the OPEN projection-intents for ``corpus`` (C3.5, Fork
    8 ruled: ``PV-20260713T221204Z-weld-apply-bridge``). For each open
    projection-intent in the feedback ledger under ``out_dir``
    (``<out_dir>/feedback/feedback.jsonl``, or ``feedback_path`` when given):

    * DERIVABLE (:func:`_derive_projection_op`) → EXECUTE the op through the
      storyboard plan-ledger door (:func:`storyboard.plan_write` — append-only,
      validated, reversible), then bank a :func:`adjudicate.make_intent_revocation`
      (retiring the intent from :func:`open_projection_intents`) + a
      :data:`adjudicate.RATIFIED_OPERATION` record carrying the ACTUAL before/after
      plan delta, both to the SAME feedback ledger;
    * UN-DERIVABLE → apply NOTHING, bank a ``ratified-operation`` record with
      ``outcome="needs-author"`` (the intent stays open), de-duped by (intent,
      reason) so a re-run does not pile up records.

    Idempotent by construction: an applied intent is retired by its revocation, so
    the next run's :func:`open_projection_intents` no longer lists it — no
    double-apply. ``by`` is the actor stamped on every record (the retrospective
    correction rides these ledger rows, never a prospective per-item queue — the
    2026-07-12 fork-law amendment). DRAFT-ONLY is superseded for THIS
    plan-altitude path only; conceptric-intents remain draft-only.

    Returns ``{"applied": [...], "needs_author": [...], "ledger": <path>}``."""
    from laplace.pipeline.ledger import read_jsonl, append_jsonl
    from laplace.manuscript import storyboard as _sb

    ledger = (Path(feedback_path) if feedback_path
              else _feedback_ledger(Path(out_dir)))
    records = read_jsonl(ledger) if ledger.is_file() else []

    loaded = _sb._load_plan(corpus)
    if loaded is None:
        return {"applied": [], "needs_author": [],
                "ledger": str(ledger), "error": f"no projection plan for {corpus!r}"}
    plan = loaded[1]

    # needs-author records already banked (target, reason) — a re-run that still
    # can't derive the intent must not append a duplicate row.
    seen_needs = {(r.get("target"), r.get("reason"))
                  for r in _adj.live(records)
                  if r.get("record") == _adj.RATIFIED_OPERATION
                  and r.get("outcome") == "needs-author"}

    applied: list[dict] = []
    needs_author: list[dict] = []

    for intent in open_projection_intents(records):
        intent_id = intent.get("id") or ""
        op_kind, object_kind, object_key, reason = _derive_projection_op(intent, plan)

        if op_kind is None:                       # UN-DERIVABLE → needs-author
            if (intent_id, reason) not in seen_needs:
                rec = _adj.make_ratified_operation(
                    intent_id, outcome="needs-author", verb=intent.get("verb") or "",
                    object_kind=object_kind, object_key=object_key, reason=reason,
                    corpus=corpus, actor=by, project=corpus)
                append_jsonl(ledger, rec)
                seen_needs.add((intent_id, reason))
            needs_author.append({"intent": intent_id, "reason": reason,
                                 "verb": intent.get("verb"), "object_key": object_key})
            continue

        # DERIVABLE → execute through the storyboard plan-ledger door
        ts = _dt.datetime.now().isoformat(timespec="seconds")
        prior = (plan.get("meta") or {}).get(object_key)
        op = {"kind": "set-meta",
              "value": {object_key: _apply_ruling_value(prior, intent, by=by, ts=ts)},
              "by": by}
        res = _sb.plan_write(corpus, op)
        if not res.get("ok"):                     # the door refused → fail-closed
            fail_reason = f"door-refused:{res.get('error') or res.get('note') or 'rejected'}"
            if (intent_id, fail_reason) not in seen_needs:
                rec = _adj.make_ratified_operation(
                    intent_id, outcome="needs-author", verb=intent.get("verb") or "",
                    object_kind=object_kind, object_key=object_key, reason=fail_reason,
                    corpus=corpus, actor=by, project=corpus)
                append_jsonl(ledger, rec)
                seen_needs.add((intent_id, fail_reason))
            needs_author.append({"intent": intent_id, "reason": fail_reason})
            continue

        # re-read the plan for the ACTUAL applied value + the next iteration's namespaces
        reloaded = _sb._load_plan(corpus)
        plan = reloaded[1] if reloaded else plan
        after = (plan.get("meta") or {}).get(object_key)

        op_rec = _adj.make_ratified_operation(
            intent_id, outcome="applied", verb=intent.get("verb") or "",
            object_kind=object_kind, object_key=object_key, op_kind=op_kind,
            before=prior, after=after, corpus=corpus, actor=by, project=corpus)
        append_jsonl(ledger, op_rec)
        revoke = _adj.make_intent_revocation(
            intent_id, reason="consumed by apply bridge (C3.5)",
            actor=by, project=corpus)
        append_jsonl(ledger, revoke)
        applied.append({"intent": intent_id, "verb": intent.get("verb"),
                        "op_kind": op_kind, "object_key": object_key,
                        "before": prior, "after": after})

    return {"applied": applied, "needs_author": needs_author, "ledger": str(ledger)}


# ---------------------------------------------------------------------------
# THE EVOLUTION DESK's reader — the ratify queue as one bounded payload
# (2026-07-20, the night arc: his ratification stage gets a surface; until now
# it lived in RATIFY.md files and chat. View = mechanism: everything below is
# read through the drafted contracts + the feedback ledger — nothing re-authored.)
# ---------------------------------------------------------------------------

def _ratify_md_sections(text: str) -> dict[str, str]:
    """Pull the substance + context blocks out of a banked RATIFY.md (the sheet
    is the human render; the payload re-reads the same bytes, never a paraphrase)."""
    out = {"substance": "", "context": ""}
    import re as _re
    m = _re.search(r"## Mined substrate.*?\n\n> (.+?)\n\n", text, _re.S)
    if m:
        out["substance"] = m.group(1).strip()
    m = _re.search(r"## Source context.*?\n\n((?:> ?.*\n)+)", text)
    if m:
        out["context"] = "\n".join(l[2:] if l.startswith("> ") else l.lstrip(">")
                                   for l in m.group(1).splitlines()).strip()
    return out


def read_ratify_queue(manuscript_dir: Path | str, corpus: str = "") -> dict:
    """The EVOLUTION DESK payload: every drafted evolution contract joined against
    the feedback ledger's live status. Pure read, bounded (substance capped, context
    flagged-present with a capped excerpt). Status per intent:

    * ``open``     — drafted, awaiting his ruling (the draft-only law's gate);
    * ``held``     — a live DEFER targets it (the HOLD verb — valid, not this run);
    * ``applied``  — revoked by consumption + a ratified-operation banked;
    * ``rejected`` — revoked without an apply.

    ``corpus`` (P3, optional — byte-compatible for existing positional callers) names
    the project so the payload can carry a ONE ``fitness_now`` light summary (one
    fitness_panel call, computed once per read). Each queue row carries its
    ``fitness_at_draft`` (stamped onto the contract meta when the draft was cut), so
    his ratification read sees whether the readings moved since. Fields only — no
    threshold, no ordering.
    """
    from laplace.pipeline.ledger import read_jsonl
    md = Path(manuscript_dir)
    evroot = md / "evolution" / "evolutions"
    ledger = _feedback_ledger(md)
    records = read_jsonl(ledger) if ledger.is_file() else []
    live_ids = {r.get("id") for r in open_intents(records)}
    deferred = _adjudicate_deferred(records)
    applied_ids = {r.get("target") for r in records
                   if r.get("record") == _adj.RATIFIED_OPERATION
                   and r.get("outcome") == "applied"}
    revoked = {r.get("supersedes"): str(r.get("text") or "")
               for r in records if r.get("record") == _adj.INTENT_REVOKE}

    queue: list[dict[str, Any]] = []
    if evroot.is_dir():
        for d in sorted(evroot.iterdir()):
            plan_p, ratify_p = d / "evolution_plan.json", d / "RATIFY.md"
            if not plan_p.is_file():
                continue
            try:
                plan = json.loads(plan_p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            meta = plan.get("meta") or {}
            intent_id = str(meta.get("intent_id") or
                            "CI-" + "-".join(d.name.split("_")[-2:][:1]))
            # the durable join: the dir tail carries the intent id's tail
            tail = d.name.split("_")[-2] if "_" in d.name else ""
            match = next((i for i in (live_ids | set(revoked) | applied_ids | deferred)
                          if i and str(i).endswith(tail)), intent_id)
            intent_id = match
            sheets = (_ratify_md_sections(ratify_p.read_text(encoding="utf-8"))
                      if ratify_p.is_file() else {"substance": "", "context": ""})
            mints = plan.get("mints") or []
            if intent_id in applied_ids:
                status = "applied"
            elif intent_id in revoked:
                status = "rejected"
            elif intent_id in deferred:
                status = "held"
            else:
                status = "open" if intent_id in live_ids else "orphan-draft"
            queue.append({
                "intent_id": intent_id,
                "dir": d.name,
                "status": status,
                "substance": sheets["substance"][:400],
                "context_present": bool(sheets["context"]),
                "context": sheets["context"][:700],
                "mint_ids": [m.get("id") for m in mints],
                "section_target": next((m.get("section_target") for m in mints
                                        if m.get("section_target")), ""),
                "ops": {k: len(v) for k, v in plan.items()
                        if k in ("mints", "reshapes", "edges") and v},
                "hold_reason": revoked.get(intent_id, "") if status == "rejected" else "",
                # P3: the fitness readings stamped onto the contract meta at draft time
                "fitness_at_draft": (plan.get("meta") or {}).get("fitness_at_draft"),
            })
    counts: dict[str, int] = {}
    for q in queue:
        counts[q["status"]] = counts.get(q["status"], 0) + 1
    payload = {"present": bool(queue), "queue": queue, "counts": counts,
               "ledger": str(ledger),
               "law": ("draft-only: nothing applies without the author's word through "
                       "the ratify door; hold = DEFER (valid, not this run); every "
                       "action is an append-only ledger record, correctable "
                       "retrospectively")}
    # P3: the fitness NOW light summary — computed ONCE per read when the corpus is
    # named (fields only; None when the panel is absent). His ratification read pairs
    # this against each row's fitness_at_draft to see whether the readings moved.
    if corpus:
        payload["fitness_now"] = _fitness_light(_read_fitness_safe(corpus, "."))
    return payload


def _adjudicate_deferred(records: list[dict]) -> set:
    from laplace.pipeline import adjudicate as _adj
    return _adj.deferred_ids(records)
