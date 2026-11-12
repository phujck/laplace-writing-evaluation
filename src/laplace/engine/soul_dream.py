"""soul_dream.py - the recursive content-dreamer: the conjugate of ``dreamer.dream`` over the
SEALED soul-corpus.

``dreamer.dream`` reparametrises the SKILL tree from telemetry-derived fitness.
``conceptric_dreamer.dream_conceptric`` reparametrises the SELF shard by clustering a region and
lifting the coarse parent. This is the THIRD instance of the one R&R loop, the substrate swapped to
the soul-corpus - the poured tranches of his life - and two things make it its own operator:

  1. **It is SEALED.** The orchestrator never reads soul CONTENT to do the semantic work. It ROUTES
     (enumerate the folded layer, parse the friction ledgers' MARKERS) and hands the two operations
     that cost intelligence - **FOLD-UP** and **WIRE** (his teaching: only these two; everything else
     routes mechanically) - to a sealed sub-Eigen wave (the ``wf_*`` workflows), exactly as ``dream``
     hands the forge brief to the host. Python is scaffold + seal + trace; the link is the sealed
     sub's (the ``keeper_ring`` / ``soul_resolve`` discipline).

  2. **Its day-window is the FRICTION LEDGER, not telemetry.** His corrections to a pour land in
     ``_friction.md`` / ``_CORRECTIONS.md`` / ``_WIRING_NOTES.md`` as banked friction-substrate -
     NEVER hand-patched (his ruling, ``memory-is-reconstruction``: confabulation is the expected
     output of memory-as-reconstruction; the fix is reconsolidation, the dream re-ingesting the
     records + corrections, not a manual patch). The dream reads them as the reconsolidation queue
     and emits a re-fold / re-wire brief with the correction injected as conditioning, so the pull
     reconsolidates endogenously. This is the half he named load-bearing: *once the cycle runs
     standing, his corrections flow in as friction and reconsolidate the pulls.*

  a skill / a self-node            <->  a folded soul ENTITY (person, group, relational map)
  ``assess`` (read fitness)        <->  ``assess_soul`` (enumerate + parse friction + rank a frontier)
  a lifecycle transition / a lift  <->  a FOLD-UP or a WIRE (the two intelligent operations)
  ``forge_skill`` (hand a brief)   <->  a sealed-sub fold / wire brief (the ``wf_*`` wave runs it)
  certify by orphan-drop           <->  certify by the sealed adjudicator's verdict + the local gate

Graded, conjugate with ``assess`` (E3): grade 0 is THE DAY - the friction since the last soul-dream
(the corrections just banked); grade >=1 is THE STANDING - re-fold the whole world (the
over-consolidated handles re-grown from their slices). The recursion - *open from the top, call down
the grades* - is across cycle invocations: each call hands the top batch of briefs, the wave runs
(small, fresh-session - E14), the next call re-assesses the shrunk frontier and surfaces the next
grade. The cycle IS the recursion; automating the cycle is the whole task (his ruling, 2026-06-10).

**The seal is absolute.** The rich plan (names + directives + briefs) is written to the gitignored
local layer the wave reads; the COMMITTED artifact (``soul_corpus/_dream_state.md``) and this module's
RETURN are content-free - counts, work-types, frontier sizes, the axes climbed, never a name or a fact.
"""

from __future__ import annotations
from laplace.core.checkout import source_tree

import json
import re
from pathlib import Path
from typing import Any

from laplace.engine import soul_consolidate
from laplace.engine import telemetry as _telemetry

# ---------------------------------------------------------------------------
# layer roots - sealed (gitignored) vs committed (content-free)
# ---------------------------------------------------------------------------

SHARD = "archive/soul_dump/_shard"                         # TRACKED since THE UNSEAL (2026-07-12, PV-20260712-unseal) - the poured tranches
PLAN_LOCAL = "archive/soul_dump/_shard/_dream_plan.json"   # tracked (the unseal) - the RICH plan the wave reads
DREAM_STATE = "soul_corpus/_dream_state.md"                # committed, content-free - counts + frontier only

# The semantic axes (soul_corpus/_grade_design.md, his coordinate system) - the order the upfold climbs.
SEMANTIC_AXES = ["person", "relationship", "goal", "time", "register"]

# The friction grammar - the markers the reconsolidation queue is written in. Marker-driven, never
# name-driven, so a new correction in his hand is read without touching this module.
_AUTHOR_MARKERS = ("AUTHOR CORRECTION", "AUTHOR-REJECTED", "AUTHOR REJECTED")
_RESOLVED_MARKERS = ("RECONSOLIDATED", "RE-WIRED", "✅ RESOLVED", "(resolved", "DONE —", "DONE -")
# Typed flags a sealed adjudicator banks. The priority orders the frontier; the kind picks the brief.
_FLAG_TYPES: dict[str, int] = {
    "WRONG MERGE": 0,            # an author-level identity error - re-wire first
    "OVER-CONSOLIDATION": 1,     # a handle coarsened past its substrate - re-fold from the slices
    "ATTRIBUTION BLEED": 1,      # a trait folded onto the wrong entity - re-fold both clean
    "OVERSTATEMENT": 2,          # a fact inflated - reconsolidate against the slices
    "GOOD CATCH": 3,             # the resolve was right, the judge over-flagged - a calibration datum
    "PIPELINE NOTE": 3,          # mechanical hygiene (label bleed, locator format) - not a re-fold
}


# ---------------------------------------------------------------------------
# enumerate the folded layer - structure only, no entity content read
# ---------------------------------------------------------------------------

def _shard_root(repo_root: Path) -> Path:
    return repo_root / SHARD


def _folded_dirs(repo_root: Path) -> list[Path]:
    """The ``*_folded`` tranche directories, sorted - the poured-and-folded worlds."""
    root = _shard_root(repo_root)
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and p.name.endswith("_folded"))


def _slice_prefixes(folded: Path) -> set[str]:
    """The entity prefixes that have recoverable grade-1 slices in ``_slices/`` (e.g. 'alicia' from
    ``alicia_A.json``) - the substrate a re-fold draws on, so an over-consolidated apex is re-grown
    from its slices, not from the coarsened handle (the friction's instruction)."""
    sdir = folded / "_slices"
    if not sdir.is_dir():
        return set()
    out: set[str] = set()
    for f in sdir.glob("*.json"):
        out.add(f.stem.rsplit("_", 1)[0].lower())  # alicia_A -> alicia
    return out


def scan_layer(repo_root: Path | str) -> dict[str, Any]:
    """Enumerate the soul-corpus's CURRENT folded state - STRUCTURE ONLY (filenames, presence), no
    entity content read. Entity names live here for the gitignored plan; they are projected away for
    the committed skeleton and the tool return (the seal)."""
    repo_root = Path(repo_root)
    tranches: list[dict[str, Any]] = []
    for folded in _folded_dirs(repo_root):
        slices = _slice_prefixes(folded)
        entities = []
        for f in sorted(folded.glob("*.json")):
            if f.name.startswith("_"):
                continue                                  # _RELATIONAL_MAP, _TRANCHE2_*, internal
            name = f.stem
            entities.append({
                "name": name,
                "recoverable": name.split("_", 1)[0].lower() in slices,
            })
        ledgers = [n for n in ("_friction.md", "_CORRECTIONS.md", "_WIRING_NOTES.md")
                   if (folded / n).is_file()]
        maps = [f.name for f in folded.glob("*RELATIONAL_MAP.json")]
        deferred = (folded / "_deferred_group").is_dir()
        tranches.append({
            "tranche": folded.name,
            "entities": entities,
            "n_entities": len(entities),
            "ledgers": ledgers,
            "maps": maps,
            "has_xworld": (folded / "_xworld").is_dir(),
            "deferred_group": deferred,
        })
    return {
        "tranches": tranches,
        "n_tranches": len(tranches),
        "n_entities": sum(t["n_entities"] for t in tranches),
        "n_deferred": sum(1 for t in tranches if t["deferred_group"]),
    }


# ---------------------------------------------------------------------------
# parse the friction ledgers - the reconsolidation queue (marker-driven)
# ---------------------------------------------------------------------------

def _is_resolved(text: str) -> bool:
    """A friction block is RESOLVED (drop from the active frontier) once a resolution marker is
    appended to it - the wave writes ``> RECONSOLIDATED <date>`` when it re-folds, so the ledger is
    append-only and self-documenting and the dream reads the delta (the reconsolidation record IS the
    ledger; ``memory-is-reconstruction``)."""
    up = text.upper()
    return any(m.upper() in up for m in _RESOLVED_MARKERS)


def _split_blocks(md: str) -> list[str]:
    """Split a friction ledger into blocks at ``##`` headers and ``>`` author-reject quote markers,
    keeping each header with its body."""
    blocks: list[str] = []
    cur: list[str] = []
    for line in md.splitlines():
        if line.startswith("## ") or line.startswith("> AUTHOR"):
            if cur:
                blocks.append("\n".join(cur))
            cur = [line]
        else:
            cur.append(line)
    if cur:
        blocks.append("\n".join(cur))
    return [b.strip() for b in blocks if b.strip()]


def _flag_kind(text: str) -> tuple[str, int] | None:
    """If a block names a typed adjudicator flag, return (kind_slug, priority)."""
    up = text.upper()
    for marker, prio in _FLAG_TYPES.items():
        if marker in up:
            return marker.lower().replace(" ", "_").replace("-", "_"), prio
    return None


def _entity_from_header(header: str) -> str:
    """Best-effort target label from a section header (LOCAL only) - the name before '(' in
    ``## Alicia Magann (apex adjudication flags...)``, or a short slug of an author-correction
    header. Used to label and dedup the plan; never committed."""
    h = header.lstrip("#> ").strip()
    h = re.split(r"\s*\(", h)[0]                 # drop the parenthetical
    h = re.split(r"\s+[—-]\s+", h)[0]            # drop a dash-summary
    h = h.replace("AUTHOR CORRECTION", "").replace("AUTHOR-REJECTED", "").strip()
    return (h[:60] or "unnamed").strip()


def parse_friction(repo_root: Path | str) -> list[dict[str, Any]]:
    """Parse every friction ledger into typed reconsolidation items - the queue the dream consumes.

    Each item: ``op='reconsolidate'``, a ``kind`` (author_correction / over_consolidation / ...), a
    ``priority`` (0 = his ground truth, first), the LOCAL ``target`` + ``directive`` + ``source`` (the
    ledger's own instruction, carried into the brief, stripped from anything committed). Author blocks
    outrank typed flags outrank per-entity adjudication sections. Resolved blocks are dropped."""
    repo_root = Path(repo_root)
    items: list[dict[str, Any]] = []
    for folded in _folded_dirs(repo_root):
        for ledger_name in ("_friction.md", "_CORRECTIONS.md", "_WIRING_NOTES.md"):
            path = folded / ledger_name
            if not path.is_file():
                continue
            md = path.read_text(encoding="utf-8", errors="replace")
            for block in _split_blocks(md):
                if _is_resolved(block):
                    continue
                head = block.splitlines()[0]
                src = f"{folded.name}/{ledger_name}"
                up = block.upper()
                if any(m in up for m in (_m.upper() for _m in _AUTHOR_MARKERS)):
                    items.append({
                        "op": "reconsolidate", "kind": "author_correction", "priority": 0,
                        "axis": "person", "target": _entity_from_header(head),
                        "directive": block, "source": src, "recoverable": True,
                    })
                    continue
                flag = _flag_kind(block)
                if flag:
                    kind, prio = flag
                    # PIPELINE_NOTE / GOOD_CATCH are signals, not re-folds: bank them as mechanical
                    # or calibration notes (op='note'), so the frontier is not padded with non-work.
                    op = "note" if kind in ("pipeline_note", "good_catch") else "reconsolidate"
                    items.append({
                        "op": op, "kind": kind, "priority": prio,
                        "axis": "person", "target": _entity_from_header(head),
                        "directive": block, "source": src, "recoverable": True,
                    })
                    continue
                if head.startswith("## ") and "ADJUDICATION FLAGS" in up:
                    items.append({
                        "op": "reconsolidate", "kind": "adjudication_flags", "priority": 2,
                        "axis": "person", "target": _entity_from_header(head),
                        "directive": block, "source": src, "recoverable": True,
                    })
    return items


def _wiring_blocks(md: str) -> list[str]:
    """Split ``_WIRING_NOTES.md`` into PER-BULLET blocks: each ``- **...**`` directive plus its
    trailing lines (continuations, the ``> RE-WIRED`` / author-reject marker the wave appends) up to
    the next bullet or ``##`` header. The conjugate of :func:`_split_blocks` for the friction ledgers,
    so a wire retires from the frontier on ITS OWN resolution marker - not the whole file's."""
    blocks: list[str] = []
    cur: list[str] = []
    for line in md.splitlines():
        s = line.strip()
        if s.startswith("- **") or s.startswith("## "):
            if cur:
                blocks.append("\n".join(cur))
            cur = [line]
        elif cur:
            cur.append(line)
    if cur:
        blocks.append("\n".join(cur))
    return [b.strip() for b in blocks if b.strip().startswith("- **")]


def parse_wiring(repo_root: Path | str) -> list[dict[str, Any]]:
    """Parse ``_WIRING_NOTES.md`` bullet directives into WIRE items - the inter-grade semantic links
    that have not been folded into the standing world yet (cross-world resolves, family/friend
    circles). A bullet whose OWN block is author-rejected or resolved is dropped (the rejection /
    ``> RE-WIRED`` marker retires it; the rejection is itself a reconsolidation item via
    :func:`parse_friction`) - so the wire frontier shrinks as the wave closes wires, the same way the
    friction frontier shrinks on ``> RECONSOLIDATED``."""
    repo_root = Path(repo_root)
    items: list[dict[str, Any]] = []
    for folded in _folded_dirs(repo_root):
        path = folded / "_WIRING_NOTES.md"
        if not path.is_file():
            continue
        md = path.read_text(encoding="utf-8", errors="replace")
        for block in _wiring_blocks(md):
            if _is_resolved(block) or any(m in block.upper() for m in ("AUTHOR-REJECTED", "AUTHOR REJECTED")):
                continue
            first = block.splitlines()[0].strip()
            m = re.match(r"- \*\*(.+?)\*\*", first)
            if not m:
                continue
            label = m.group(1)
            items.append({
                "op": "wire", "kind": "cross_link", "priority": 1,
                "axis": "relationship", "target": label[:60],
                "directive": first, "source": f"{folded.name}/_WIRING_NOTES.md", "recoverable": True,
            })
    return items


def scan_folds(repo_root: Path | str) -> list[dict[str, Any]]:
    """Poured-but-unfolded work - today the deferred group chats (the multi-speaker fold variant: the
    circle's members become first-class entities). Detected structurally by a ``_deferred_group/``
    directory; the README inside names the variant, not read here."""
    repo_root = Path(repo_root)
    out: list[dict[str, Any]] = []
    for folded in _folded_dirs(repo_root):
        if (folded / "_deferred_group").is_dir():
            out.append({
                "op": "fold", "kind": "deferred_group", "priority": 2,
                "axis": "person", "target": f"{folded.name}/_deferred_group",
                "directive": "multi-speaker fold: lift the group's members to first-class entities",
                "source": f"{folded.name}/_deferred_group/README.md", "recoverable": True,
            })
    return out


def scan_value_axis(repo_root: Path | str) -> list[dict[str, Any]]:
    """The value-axis producer (the binding ring, his 2026-06-10): surface the trait/value/stance
    recurrence work the dream was otherwise blind to. Mechanical - coverage counts only (via
    ``soul_provenance``); every semantic judgement stays in the wave's briefs.

    Two item kinds:
      * ``trait_provenance`` - one per entity whose voice/generator items are not yet
        locator-carrying: re-fold those fields from the recoverable slices under the locator law.
        The cycle IS the backfill - no mechanical matcher ever writes a locator (a paraphrased
        synthesis matched by string would risk confabulated provenance).
      * ``value_axis_cluster`` - the standing cross-entity recurrence-cluster: fold recurring
        locator-carrying traits into trait nodes (``_shard/_traits/``) wired by exhibits/generates
        edges, coupling read off shared locators. Emitted as soon as ANY locator-carrying trait
        substrate exists; instead of gating on a coverage threshold, the brief makes unlocatored
        instances INVISIBLE to the ring (phi is watched, not imposed)."""
    from laplace.engine import soul_provenance   # lazy - soul_provenance imports this module's helpers
    repo_root = Path(repo_root)
    cov = soul_provenance.coverage(repo_root)
    items: list[dict[str, Any]] = []
    n_trait_loc = 0
    for stem, fields in sorted(cov["files"].items()):
        n = sum(fields.get(f, {}).get("n", 0) for f in ("voice", "generator"))
        w = sum(fields.get(f, {}).get("with_locator", 0) for f in ("voice", "generator"))
        n_trait_loc += w
        if n and w < n:
            items.append({
                "op": "fold", "kind": "trait_provenance", "priority": 2, "axis": "register",
                "target": stem,
                "directive": (f"re-fold {stem}'s voice + generator fields ({n - w} of {n} items "
                              "locator-less) from its recoverable slices under the locator law: the "
                              "same content re-derived as locator-carrying objects - no new claims, "
                              "no invented locators, honest-null where substrate cannot be pointed at"),
                "source": "soul_dream.scan_value_axis", "recoverable": True,
            })
    if n_trait_loc:
        items.append({
            "op": "fold", "kind": "value_axis_cluster", "priority": 3, "axis": "register",
            "target": "_traits (the value ring)",
            "directive": (f"recurrence-cluster the locator-carrying voice/generator instances "
                          f"({n_trait_loc} currently) across ALL entities into trait nodes under "
                          "_shard/_traits/: one node per recurring trait/value/stance, its instances "
                          "as {entity, statement, locator} refs; an instance without a locator is "
                          "INVISIBLE to the ring (it couples at zero) - no coverage threshold "
                          "imposed; wire the typed edges (entity exhibits trait; a generator "
                          "statement generates trait); merges conservative - a wrong merge corrupts "
                          "where a miss recovers"),
            "source": "soul_dream.scan_value_axis", "recoverable": True,
        })
    return items


def reshape_flags(repo_root: Path | str) -> list[dict[str, Any]]:
    """Structural reshape work from ``soul_consolidate.grade_stats`` - a level grown past the width
    bound IS the signal a new grade is required (his: usability-pressure sets the grades). The
    threshold (φ, F1) is his; the FLAG is mechanical. op='reshape', the lowest priority - structure
    follows the corrections."""
    repo_root = Path(repo_root)
    try:
        graded = soul_consolidate.build_graded(repo_root)
        stats = soul_consolidate.grade_stats(graded)
    except Exception:                                    # noqa: BLE001 - a missing index is not a dream failure
        return []
    out: list[dict[str, Any]] = []
    for flag in stats.get("reshape_flags", []):
        out.append({
            "op": "reshape", "kind": "too_wide", "priority": 4,
            "axis": "time" if flag["grade"] == 2 else "goal", "target": flag["node"],
            "directive": flag["why"], "source": "soul_consolidate.grade_stats",
            "recoverable": True, "children": flag["children"], "grade": flag["grade"],
        })
    return out


# ---------------------------------------------------------------------------
# the sealed-sub briefs - the two intelligent operations, handed out (not run here)
# ---------------------------------------------------------------------------

_SEAL_RULE = (
    "SEAL (the BOUNDARY, not a paraphrase rule - his 2026-06-10): the seal governs what is COMMITTED "
    "or RETURNED, never the local working layer. The committed handle + any tool return stay "
    "content-free / refs-only - no name, no fact rides into git or a context. The gitignored local "
    "fold is working material on HIS machine: it MAY carry VERBATIM source - take the information, do "
    "NOT paraphrase to dodge a seal that does not apply here (paraphrase-only made the floor itself a "
    "re-encoding, i.e. a confabulation with no clean ground - the harmful tilt). Builder != judge "
    "still holds, but the cheap jury checks FAITHFULNESS to the substrate + the commit/return "
    "boundary ONLY - NOT verbatim-purity on the local layer (that over-check is retired)."
)

_PROVENANCE_RULE = (
    "PROVENANCE (the locator law + VISIBLE source, his 2026-06-10): EVERY item in EVERY field - "
    "voice, history, relations, generator, conjectural - is an object {<content>, 'locator': "
    "'<slice>:<line-range>[, ...]'}, never a bare string; and on the local layer carry a short "
    "verbatim 'source' snippet too, so provenance is SEEN, not merely pointed at (he wants to see "
    "where it came from). Prefer the source text - verbatim is faithful, paraphrase is lossy. NEVER "
    "invent a locator: an item whose substrate cannot be pointed at rides locator=null + a flag "
    "(honest-null beats confabulated provenance). The cross-link (keeper_ring coupling) is READ OFF "
    "shared locators downstream, never re-derived."
)


def _brief(item: dict[str, Any]) -> str:
    """The sealed-sub prompt for one work item - the brief the ``wf_*`` wave executes. The two
    intelligent operations carry the LEDGER'S OWN directive (his correction injected as conditioning,
    not a hand-patch): the wave RE-FOLDS / RE-WIRES with the correction as a constraint, so the pull
    reconsolidates endogenously."""
    op, kind = item["op"], item["kind"]
    directive = item.get("directive", "")
    if op == "reconsolidate":
        return (
            f"SEALED RECONSOLIDATION ({kind}). The author / a sealed adjudicator flagged this fold; "
            f"re-fold the affected entity CLEAN from its grade-1 slices (the recoverable substrate), "
            f"applying the correction as a CONSTRAINT - drop the rejected traits, do not carry the "
            f"coarsened handle. Do NOT hand-patch; the re-fold IS the reconsolidation.\n\n"
            f"THE FRICTION (verbatim from the ledger - his ground truth or the adjudicator's flag):\n"
            f"{directive}\n\n{_SEAL_RULE}\n\n{_PROVENANCE_RULE}"
        )
    if op == "wire":
        return (
            f"SEALED WIRE ({kind}). Resolve this inter-grade link into the standing relational world "
            f"under a builder != judge adjudicator - the second operation that costs intelligence "
            f"(THIS is that). Do not hand-merge.\n\nTHE LINK (from the wiring notes):\n{directive}\n\n"
            f"{_SEAL_RULE}\n\n{_PROVENANCE_RULE}"
        )
    if op == "fold":
        return (
            f"SEALED FOLD ({kind}). {directive}. Use the ONE recursive operator (slice the floor, "
            f"recur the slices up into a grade-up handle, detail recoverable from the slices below); "
            f"gate each on its adjudicator.\n\n{_SEAL_RULE}\n\n{_PROVENANCE_RULE}"
        )
    # reshape / note: structural or advisory - no sealed wave, surfaced for his φ call / the record.
    return f"{op.upper()} ({kind}): {directive}"


# ---------------------------------------------------------------------------
# assess_soul - the read/propose (mutates nothing); the conjugate open of the dream's close
# ---------------------------------------------------------------------------

def _rank(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Frontier order: lowest priority number first (his corrections lead), then re-fold before wire
    before fold before reshape, deterministically by target for a stable plan."""
    op_order = {"reconsolidate": 0, "wire": 1, "fold": 2, "reshape": 3, "note": 5}
    return sorted(items, key=lambda i: (i["priority"], op_order.get(i["op"], 4), i["target"]))


def assess_soul(repo_root: Path | str, grade: int = 0) -> dict[str, Any]:
    """``assess`` generalised to the soul-corpus: enumerate the folded layer, parse the friction
    ledgers (the reconsolidation queue) + the wiring notes + the deferred folds + the structural
    reshape flags, and rank them into a work-FRONTIER with a sealed-sub brief per item. Mutates
    nothing - the apply half (the wave) runs the briefs; this is the open.

    Graded (E3): grade 0 surfaces the DAY's reconsolidations first (the corrections just banked);
    grade >=1 (the standing) keeps the whole frontier, the over-consolidated handles re-grown from
    their slices regardless of recency."""
    repo_root = Path(repo_root)
    layer = scan_layer(repo_root)
    friction = parse_friction(repo_root)
    wires = parse_wiring(repo_root)
    folds = scan_folds(repo_root)
    values = scan_value_axis(repo_root)
    reshapes = reshape_flags(repo_root)

    work = [i for i in (friction + wires + folds + values + reshapes) if i["op"] != "note"]
    notes = [i for i in friction if i["op"] == "note"]
    for i in work:
        i["brief"] = _brief(i)

    frontier = _rank(work)
    # The day-grade leads with his ground truth (the author corrections); the standing carries all.
    if grade == 0:
        # Surface the priority-0 / priority-1 reconsolidations as the head; the tail still rides.
        frontier = _rank([i for i in work if i["priority"] <= 1]) + _rank([i for i in work if i["priority"] > 1])

    by_op: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    for i in work:
        by_op[i["op"]] = by_op.get(i["op"], 0) + 1
        by_kind[i["kind"]] = by_kind.get(i["kind"], 0) + 1

    return {
        "grade": grade,
        "layer": layer,
        "frontier": frontier,
        "notes": notes,
        "n_work": len(work),
        "by_op": by_op,
        "by_kind": by_kind,
        "axes": SEMANTIC_AXES,
        "note": "PROXY proposal - mutates nothing. The two intelligent operations (fold-up, wire) are "
                "handed as sealed-sub briefs the wf_* wave runs (small batches, fresh session - E14); "
                "the dream certifies the result by the adjudicator's verdict + the local gate, never "
                "by a proxy. His corrections ride as friction and reconsolidate the pulls.",
    }


# ---------------------------------------------------------------------------
# the seal projection - committed/returned views carry no name, no fact
# ---------------------------------------------------------------------------

def _safe_item(item: dict[str, Any]) -> dict[str, Any]:
    """Project a work item to its content-free fields - op / kind / priority / axis / recoverable.
    The target, directive, brief and source (which name people and carry his words) are dropped."""
    out = {k: item[k] for k in ("op", "kind", "priority", "axis", "recoverable") if k in item}
    if "grade" in item:
        out["grade"] = item["grade"]
    return out


def safe_view(assessment: dict[str, Any]) -> dict[str, Any]:
    """The content-free projection of an assessment - what may be committed or returned to a context.
    Counts, work-types, frontier shape, axes; never a name or a fact (the seal)."""
    return {
        "grade": assessment["grade"],
        "n_tranches": assessment["layer"]["n_tranches"],
        "n_entities": assessment["layer"]["n_entities"],
        "n_work": assessment["n_work"],
        "by_op": assessment["by_op"],
        "by_kind": assessment["by_kind"],
        "n_notes": len(assessment.get("notes", [])),
        "frontier": [_safe_item(i) for i in assessment["frontier"]],
        "axes": assessment["axes"],
    }


# ---------------------------------------------------------------------------
# persist - the RICH plan (sealed, gitignored) + the content-free state (committed)
# ---------------------------------------------------------------------------

def write_plan_local(repo_root: Path | str, assessment: dict[str, Any]) -> Path:
    """Persist the RICH work-plan (targets + directives + briefs) to the gitignored local layer the
    ``wf_*`` wave reads. This is the only artifact that carries names + his words, and it never leaves
    the sealed tree."""
    repo_root = Path(repo_root)
    out = repo_root / PLAN_LOCAL
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(assessment, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def write_dream_state(repo_root: Path | str, assessment: dict[str, Any]) -> Path:
    """Persist the COMMITTED, content-free dream state - counts + the frontier shape, no name, no
    fact. The conjugate of ``soul_consolidate.write_skeleton``: the structural skeleton is the graded
    store's shape; this is the dream's frontier shape."""
    repo_root = Path(repo_root)
    view = safe_view(assessment)
    out = repo_root / DREAM_STATE
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Soul-dream state (content-free, the frontier shape)",
        "",
        "<!-- COMMITTED, content-free. The recursive content-dreamer's current work-frontier over the",
        "sealed soul-corpus: counts and work-types only. Every name, directive and brief lives in the",
        "gitignored plan (archive/soul_dump/_shard/_dream_plan.json) the wf_* wave reads. The two",
        "intelligent operations (fold-up, wire) are handed as sealed-sub briefs; reconsolidations lead",
        "(his corrections, banked as friction, never hand-patched). -->",
        "",
        f"- **grade:** {view['grade']} ({'the day — corrections first' if view['grade'] == 0 else 'the standing — re-fold the world'})",
        f"- **tranches folded:** {view['n_tranches']}",
        f"- **entities (grade-1/2 handles):** {view['n_entities']}",
        f"- **open work items:** {view['n_work']}  ·  advisory notes: {view['n_notes']}",
        "",
        "## Frontier by operation",
        "",
    ]
    for op in ("reconsolidate", "wire", "fold", "reshape"):
        n = view["by_op"].get(op, 0)
        if n:
            lines.append(f"- **{op}:** {n}")
    lines += ["", "## Frontier by kind (the friction grammar)", ""]
    for kind, n in sorted(view["by_kind"].items(), key=lambda kv: -kv[1]):
        lines.append(f"- `{kind}`: {n}")
    lines += ["", "## Semantic axes (the coordinates the upfold climbs — _grade_design.md)", "",
              "- " + " → ".join(view["axes"]), ""]
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# certify by RESULTS - the sealed adjudicator's verdict + the structural local gate
# ---------------------------------------------------------------------------

def _latest_verdict(folded: Path, target: str) -> dict[str, Any] | None:
    """Read the most recent ``_verdicts/*.json`` matching a target's first name, if any. The verdict
    files are the sealed adjudicator's record (faithful / partial / confabulated + seal_clean +
    detail_recoverable) - the RESULT the dream certifies against, never a proxy."""
    vdir = folded / "_verdicts"
    if not vdir.is_dir():
        return None
    key = target.split()[0].split("_")[0].lower() if target else ""
    cands = sorted(vdir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for v in cands:
        if not key or key in v.stem.lower():
            try:
                return {"file": v.name, **json.loads(v.read_text(encoding="utf-8", errors="replace"))}
            except (OSError, json.JSONDecodeError):
                continue
    return None


def certify(repo_root: Path | str, target: str = "", op: str = "reconsolidate") -> dict[str, Any]:
    """Certify a wave's result BY RESULTS (his close, 2026-06-07), the conjugate of
    ``conceptric_dreamer._certify``: the structural LOCAL gate must hold (pointers reconstruct -
    ``soul_consolidate.local_faithfulness``) AND the sealed adjudicator's verdict must be faithful
    (a *partial* that recurses is acceptable under the graded frame, F14 his; a *confabulated*
    verdict fails and the wave is reverted, the why-not banked as the next friction). This reads the
    result; the wave writes it. Returns the gate + the verdict, no content."""
    repo_root = Path(repo_root)
    try:
        graded = soul_consolidate.build_graded(repo_root)
        gate = soul_consolidate.local_faithfulness(repo_root, graded)
        faithful = bool(gate.get("pass"))
    except Exception as exc:                              # noqa: BLE001
        return {"certified": False, "faithful": False, "why_not": f"local gate unavailable: {exc}"}

    verdict_label = None
    for folded in _folded_dirs(repo_root):
        v = _latest_verdict(folded, target)
        if v:
            verdict_label = v.get("verdict") or v.get("fate") or v.get("faithfulness")
            break

    if not faithful:
        return {"certified": False, "faithful": False, "verdict": verdict_label,
                "why_not": "structural faithfulness broke (a pointer or the soul seal regressed)"}
    if verdict_label is not None and isinstance(verdict_label, str) and "confab" in verdict_label.lower():
        return {"certified": False, "faithful": True, "verdict": verdict_label,
                "why_not": "the sealed adjudicator returned confabulated - revert, bank the why-not"}
    return {"certified": True, "faithful": True, "verdict": verdict_label, "why_not": None}


# ---------------------------------------------------------------------------
# soul_dream - the re-entrant graded cycle (the conjugate of dreamer.dream)
# ---------------------------------------------------------------------------

def _commit(repo_root: Path, paths: list[Path], message: str) -> str | None:
    from laplace.core import versioning as gitio
    return gitio.commit(repo_root, [p for p in paths if p is not None], message)


def default_repo_root() -> Path:
    return source_tree()


def soul_dream(
    repo_root: Path | str | None = None,
    apply: bool = True,
    grade: int = 0,
    commit: bool = True,
) -> dict[str, Any]:
    """Run the content-dreamer's R&R cycle - the conjugate of ``dreamer.dream`` over the soul-corpus.

    RE-ENTRANT and idempotent (like the session checkpoint): each call assesses the current frontier,
    refreshes the structural graded store, writes the rich plan (gitignored) + the content-free state
    (committed), and HANDS the two intelligent operations as sealed-sub briefs - it does NOT spawn the
    wave (E14: pours run in small batches, a fresh session between tranches; and the engine, like
    ``dream``, makes no LLM call of its own - judgement routes to the wave). The wave runs the briefs,
    appends its resolution markers to the ledgers, and the NEXT call re-assesses the shrunk frontier
    and surfaces the next grade. The cycle IS the recursion (open from the top, call down the grades).

    ``apply`` refreshes the graded store + writes the plan/state + commits the content-free skeletons
    (revertible); ``apply=False`` is a dry assessment. Graded: grade 0 = the day (corrections lead),
    grade >=1 = the standing (re-fold the world). Returns the content-free summary + the local plan
    path the wave consumes - never a name or a fact (the seal)."""
    repo_root = Path(repo_root) if repo_root is not None else default_repo_root()
    assessment = assess_soul(repo_root, grade=grade)
    view = safe_view(assessment)

    out: dict[str, Any] = {
        "grade": grade,
        "assessment": view,
        "applied": False,
        "boundary_advanced": False,
    }

    if not apply:
        out["note"] = "dry assessment - nothing written. Pass apply=True to refresh the store + hand the briefs."
        return out

    # Mechanical curation, in-process (the routing that should be mechanical): keep grades 0-2 of the
    # structural store current as new tranches land, then persist the rich plan (sealed) + the
    # content-free state (committed).
    changed: list[Path] = []
    try:
        graded = soul_consolidate.build_graded(repo_root)
        stats = soul_consolidate.grade_stats(graded)
        soul_consolidate.write_graded_local(repo_root, graded)          # gitignored
        skel = soul_consolidate.write_skeleton(repo_root, stats)        # committed, content-free
        changed.append(skel)
    except Exception as exc:                                            # noqa: BLE001
        out["store_refresh"] = f"skipped: {exc}"

    plan_path = write_plan_local(repo_root, assessment)                 # gitignored - the wave reads this
    state_path = write_dream_state(repo_root, assessment)               # committed, content-free
    changed.append(state_path)

    out["applied"] = True
    out["plan_local"] = str(plan_path)
    out["committed"] = [str(p) for p in changed]
    out["next"] = (
        "run the wf_* fold/wire wave against the local plan in a FRESH session (E14: small batches, "
        "gate each on its adjudicator); reconsolidations (his corrections) first, then wires, then "
        "the deferred fold. Re-call soul_dream after the wave to certify the verdicts and re-assess."
    )

    if commit and changed:
        msg = (f"soul dream (grade {grade}): {view['n_work']} work items "
               f"({', '.join(f'{k}={v}' for k, v in sorted(view['by_op'].items()))})")
        sha = _commit(repo_root, changed, msg)
        out["commit"] = sha

    # The soul clock marks WHEN the dream last consolidated (a 'last ran' stamp). It does NOT mark the
    # friction done - an item is resolved only when the wave appends its resolution marker to the
    # ledger; re-running soul_dream re-hands the same briefs until then (re-entrant, correct). The
    # clock advances on a grade-0 (day) apply, conjugate to dreamer.dream's day-boundary.
    if grade == 0:
        _telemetry.log("soul_dream_complete", n_work=view["n_work"], by_op=view["by_op"])
        out["boundary_advanced"] = True
    return out


def main(argv: list[str] | None = None) -> int:
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    args = argv if argv is not None else sys.argv[1:]
    grade = int(args[0]) if args else 0
    apply = "--apply" in args
    out = soul_dream(grade=grade, apply=apply, commit=False)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
