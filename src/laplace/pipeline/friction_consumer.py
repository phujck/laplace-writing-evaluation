"""The friction consumer — drain (never apply) the unified friction channel.

The engine's analogue of :mod:`laplace.pipeline.evolution_consumer`, one level
up the stack: where that module consumes a manuscript's open conceptric-intent
queue, this one consumes the L1 friction ledger
(``corpus_friction/laplace_engine.jsonl`` — spine ``schema.FRICTION_FIELDS``,
written only through :func:`corpus_ingest.friction_add`). One door, three exits
(2026-07-11 learning-loop design, §1c):

1. **conceptric-class** — a ``friction`` whose ``owning_layer`` is a registered
   corpus is NOT drafted here: it is re-deposited onto that manuscript's
   feedback ledger (a ``conceptric-intent`` with a DETERMINISTIC id, so re-runs
   are no-ops) and left to ``consume_intents`` → ``RATIFY.md`` →
   ``evolve.py --apply``. Delegation, never duplication.
2. **engine-layer** ``friction`` records — rolled up by ``chain`` prefix where
   a chain of custody exists (same descent from global goal → one group with N
   witnesses; the hierarchy is natural), by ``owning_layer`` for the chainless
   residue — drafted as ``evolutions_engine/<date>/FIX_PROPOSALS.md``, one
   RATIFY-analogue per group, each entry quoting the record's full chain so a
   local fixer sees WHY, not only where. The drain counts the chainless (the
   seed records predate the field) so the gap stays visible.
   The engine's B10-analogue is SUITE + JUDGE: an applied bite
   must show the full pytest suite green on the POST state AND a separate
   verification pass (builder ≠ judge) against the friction that demanded it.
3. **``fork`` records** — an OPEN_STACK row drafted in the report; the drain
   never writes ``OPEN_STACK.md`` itself, it prints the row for the close
   ritual to bank.

DRAFT-ONLY, enforced STRUCTURALLY (the ``evolution_consumer`` discipline): the
drain has NO code path that applies a fix, shells out, or emits the
consumption supersede — the resolution record's shape is DESIGNED into the
draft as the post-apply step (:func:`make_friction_resolution` builds the dict;
nothing here appends it). "Consumed" means a later ``record: "resolution"``
line names the record's id in ``supersedes`` AND carries ``evidence``; the
EVIDENCE VALIDATOR (:func:`invalid_resolutions`) refuses to count — and flags
loudly — any resolution retiring a friction/fork with an empty ``evidence``
field: an evidence-less resolution leaves its target OPEN.

The drain also emits ``<ledger>.digest.md`` — the grade-0 fold projection.
``.jsonl`` is not in ``self_shard._TEXT_EXT``, so the raw ledger folds as a
name-only asset node; the digest is what the UPFOLD grades and the WIRE
cross-links.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

from laplace.pipeline import adjudicate as _adj
from laplace.pipeline import schema as _schema
from laplace.pipeline.ledger import append_jsonl, read_jsonl

#: the non-friction auxiliary pass-throughs (data/schematic/txn — and any later
#: joiner): known to the drain but never drafted, never escalated.
_BASE_AUX = _schema.AUXILIARY_RECORD_KINDS - set(_schema.FRICTION_KINDS)


# ---------------------------------------------------------------------------
# the open-set query + the evidence validator (pure — directly unit-tested)
# ---------------------------------------------------------------------------

def invalid_resolutions(records: list[dict]) -> list[dict]:
    """Resolutions that try to retire a friction/fork record WITHOUT evidence.
    Each is REFUSED: it does not count as consumption, its target stays OPEN,
    and the drain flags it in the summary. Resolutions on non-friction targets
    (intents, findings) are untouched — the validator guards only the friction
    channel's consumption contract."""
    recs = [r for r in records if isinstance(r, dict)]
    by_id = {r.get("id"): r for r in recs if r.get("id")}
    out: list[dict] = []
    for r in recs:
        if r.get("record") != _adj.RESOLUTION or not r.get("supersedes"):
            continue
        target = by_id.get(r["supersedes"])
        if (target is not None and target.get("kind") in _schema.FRICTION_KINDS
                and not str(r.get("evidence") or "").strip()):
            out.append(r)
    return out


def _retired_ids(records: list[dict]) -> set[str]:
    """Ids retired by a later ``supersedes`` — :func:`adjudicate.live` semantics
    with the evidence validator applied: a refused resolution retires nothing."""
    refused = {r.get("id") for r in invalid_resolutions(records)}
    return {r.get("supersedes") for r in records
            if isinstance(r, dict) and r.get("supersedes")
            and r.get("id") not in refused}


def open_frictions(records: list[dict]) -> list[dict]:
    """The live, open friction/fork records: ``kind ∈ FRICTION_KINDS``,
    ``status == "open"`` (the maker's stamp; retirement is by supersession,
    never mutation), not named by a later valid ``supersedes``."""
    retired = _retired_ids([r for r in records if isinstance(r, dict)])
    return [r for r in records if isinstance(r, dict)
            and r.get("kind") in _schema.FRICTION_KINDS
            and r.get("id") not in retired
            and (r.get("status") or "open") == "open"]


def consumed_frictions(records: list[dict]) -> list[dict]:
    """friction/fork records retired by an EVIDENCE-carrying resolution — the
    one mechanical meaning of "consumed" (§1c)."""
    recs = [r for r in records if isinstance(r, dict)]
    by_id = {r.get("id"): r for r in recs if r.get("id")}
    out: list[dict] = []
    for r in recs:
        if (r.get("record") == _adj.RESOLUTION and r.get("supersedes")
                and str(r.get("evidence") or "").strip()):
            target = by_id.get(r["supersedes"])
            if target is not None and target.get("kind") in _schema.FRICTION_KINDS:
                out.append(target)
    return out


def make_friction_resolution(target_id: str, *, evidence: str, verb: str = "resolved",
                             reason: str = "", actor: str = "eigen",
                             project: str = "laplace_engine",
                             rec_id: str | None = None,
                             ts: str | None = None) -> dict:
    """The post-apply close-the-loop record: the EXISTING maker
    (:func:`adjudicate.make_resolution` — ledger-agnostic dict, a wiring choice
    not new machinery) pointed at the friction channel, with ``evidence``
    REQUIRED (commit hash / evolution dir + gates.json / OPEN_STACK row id).
    Raises :class:`ValueError` on empty evidence — an evidence-less resolution
    would leave its target open anyway (:func:`invalid_resolutions`), so the
    door refuses to build one. The DRAIN never calls this: consumption happens
    only after the author ratifies and an apply shows suite + judge."""
    if not str(evidence or "").strip():
        raise ValueError("evidence required: a resolution retiring a friction/"
                         "fork without evidence leaves its target OPEN")
    rec = _adj.make_resolution(target_id, verb=verb, reason=reason, actor=actor,
                               project=project, rec_id=rec_id, ts=ts)
    rec["evidence"] = str(evidence).strip()
    return rec


# ---------------------------------------------------------------------------
# the seed migration (§1b, RULED): supersede re-pours, never line edits
# ---------------------------------------------------------------------------

def migrate_where_records(ledger_path: Path | str) -> dict:
    """Re-pour EVERY open ``where``-shaped record under the FRICTION_FIELDS
    spine (``where`` → ``target``, everything else preserved verbatim). The
    ledger is live and growing, so the migration is defined by QUERY, never by
    count; ``append_jsonl`` is the only write shape, so the correction is
    superseding re-pours — the old line stays as history, retired by the
    re-pour's ``supersedes``. Idempotent: a second run finds zero targets."""
    path = Path(ledger_path)
    records = read_jsonl(path) if path.is_file() else []
    before = open_frictions(records)
    todo = [r for r in before if "where" in r]
    stamp = _dt.datetime.now().strftime("RW-%Y%m%d-%H%M%S-")
    poured: list[dict] = []
    for i, old in enumerate(todo):
        new = {k: v for k, v in old.items() if k != "where"}
        new["target"] = old.get("target") or old.get("where")
        new["id"] = f"{stamp}{400001 + i:06d}"     # 4000XX: the migration band
        new["supersedes"] = old.get("id")
        append_jsonl(path, new)
        poured.append({"superseded": old.get("id"), "id": new["id"]})
    after = open_frictions(read_jsonl(path))
    return {"ledger": str(path), "migrated": poured,
            "open_before": len(before), "open_after": len(after),
            "open_where_shaped_after": sum(1 for r in after if "where" in r)}


# ---------------------------------------------------------------------------
# the digest — the ledger's grade-0 fold projection (deterministic)
# ---------------------------------------------------------------------------

def _one_line(rec: dict, width: int = 160) -> str:
    text = " ".join(str(rec.get("value") or "").split())
    return text[:width] + ("…" if len(text) > width else "")


def _chain_of(rec: dict) -> list[str]:
    """The record's chain of custody, normalised: a list of non-empty goal
    frames coarse→fine, or [] for a chainless (pre-chain seed) record."""
    raw = rec.get("chain")
    if not isinstance(raw, (list, tuple)):
        return []
    return [str(f).strip() for f in raw if str(f).strip()]


def _group_key(rec: dict) -> tuple[str, str]:
    """The rollup law (2026-07-11 chain-of-custody addendum): records sharing a
    chain PREFIX — every frame above the local action, i.e. the same descent
    from global goal — roll into ONE group with N witnesses (a one-frame chain
    groups by that frame). Chainless records fall back to ``owning_layer``, the
    pre-chain grouping. The tag sorts chain groups ahead of layer groups, so
    the hierarchy reads coarse→fine before the ungrouped residue."""
    chain = _chain_of(rec)
    if chain:
        return ("chain", " › ".join(chain[:-1] or chain))
    return ("layer", str(rec.get("owning_layer") or "(unassigned)"))


def _group_heading(key: tuple[str, str]) -> str:
    return f"chain: {key[1]}" if key[0] == "chain" else key[1]


def digest_md(records: list[dict], name: str = "laplace_engine") -> str:
    """Open/consumed rolled up by chain prefix where chains exist (the
    hierarchical rollup — same descent, one group, N witnesses), by owning
    layer for the chainless residue; one line per open record. Derived from
    ledger CONTENT only (no generation timestamp), so an unchanged ledger
    digests to identical bytes — the re-run is idempotent by construction."""
    opens = open_frictions(records)
    consumed = consumed_frictions(records)
    flagged = invalid_resolutions(records)
    kinds = {k: sum(1 for r in opens if r.get("kind") == k)
             for k in _schema.FRICTION_KINDS}
    chainless = sum(1 for r in opens if not _chain_of(r))
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in opens:
        groups.setdefault(_group_key(r), []).append(r)
    lines = [f"# {name} — friction-ledger digest (grade 0)", "",
             f"open: {len(opens)} (friction: {kinds.get('friction', 0)}, "
             f"fork: {kinds.get('fork', 0)}) · consumed: {len(consumed)} · "
             f"flagged evidence-less resolutions: {len(flagged)} · "
             f"chainless: {chainless}", ""]
    for key in sorted(groups):
        recs = sorted(groups[key], key=lambda r: str(r.get("id") or ""))
        witnesses = f" ({len(recs)} witnesses)" if key[0] == "chain" else ""
        lines.append(f"## {_group_heading(key)} — {len(recs)} open{witnesses}")
        for r in recs:
            chain = _chain_of(r)
            action = f" ⟨{chain[-1]}⟩" if chain else ""
            lines.append(f"- `{r.get('id')}` [{r.get('kind')}] "
                         f"{r.get('node')} — {_one_line(r)}{action}")
        lines.append("")
    if flagged:
        lines.append("## flagged — evidence-less resolutions (targets stay OPEN)")
        for r in sorted(flagged, key=lambda r: str(r.get("id") or "")):
            lines.append(f"- `{r.get('id')}` names `{r.get('supersedes')}` "
                         "with no evidence — refused")
        lines.append("")
    return "\n".join(lines)


def digest_path(ledger_path: Path | str) -> Path:
    return Path(ledger_path).with_suffix(".digest.md")


# ---------------------------------------------------------------------------
# the three exits
# ---------------------------------------------------------------------------

def _corpus_project(owning_layer: str):
    """Exit-1 detector: an ``owning_layer`` naming a registered project with a
    feedback ledger is conceptric-class. Engine layers ('protocol/…', 'scripts/…')
    never resolve — :func:`registry.resolve` rejects path-shaped names."""
    try:
        from laplace.pipeline import registry
        proj = registry.resolve((owning_layer or "").strip())
        return proj if (proj is not None and proj.feedback_ledger) else None
    except Exception:  # noqa: BLE001 — routing enrichment, never fatal
        return None


def _delegate(repo_root: Path, proj, rec: dict) -> dict:
    """Exit 1 — re-deposit a conceptric-class friction onto the manuscript's
    feedback ledger as a ``conceptric-intent`` (intent ``other``: the machine
    cannot rule the substrate-fault kind, so it queues for the author there).
    The intent id is DETERMINISTIC (``CI-<friction id>``), and an id already on
    the target ledger makes the re-deposit a no-op — the re-run is idempotent."""
    intent_id = f"CI-{rec.get('id')}"
    ledger = Path(repo_root) / proj.feedback_ledger
    existing = {x.get("id") for x in (read_jsonl(ledger) if ledger.is_file() else [])}
    entry = {"friction_id": rec.get("id"), "intent_id": intent_id,
             "project": proj.name, "ledger": proj.feedback_ledger}
    if intent_id in existing:
        entry["deposited"] = False
        return entry
    note = " ".join(filter(None, [
        str(rec.get("value") or ""),
        f"(reporter's proposal: {rec['proposal']})" if rec.get("proposal") else "",
        f"[delegated from engine friction {rec.get('id')}]"]))
    intent = _adj.make_conceptric_intent(rec.get("node") or "", "other", note=note,
                                         actor=rec.get("by") or "eigen",
                                         project=proj.name, rec_id=intent_id,
                                         ts=rec.get("ts"))
    append_jsonl(ledger, intent)
    entry["deposited"] = True
    return entry


def open_stack_row(rec: dict, date: str) -> str:
    """Exit 3 — the drafted OPEN_STACK row (the de-stager's columns:
    ``| # | Fork | First raised | Recurred | Status | Trigger / note |``).
    Printed for the close ritual to bank; the drain never writes OPEN_STACK.md."""
    text = _one_line(rec, 200)
    first = (rec.get("ts") or date)[:10]
    return (f"| F? | **{rec.get('node')}** — {text} | {first} | 1 | 🔴 | "
            f"ledger `{rec.get('id')}`; blocked-on: author ruling |")


def _fix_proposals_md(groups: dict[tuple[str, str], list[dict]], date: str,
                      ledger_rel: str) -> str:
    """Exit 2 — one RATIFY-analogue per group. Groups are the rollup law's:
    chain PREFIX where a chain of custody exists (the shared descent, N
    witnesses), owning layer for the chainless. Each entry quotes the record's
    full chain so a local fixer sees the descent from global goal to the
    stumble — the why, not only the where. The frictions quoted, the proposed
    bite (from the reporters' advisory proposals), the verification named, and
    the post-apply resolution DESIGNED but never emitted."""
    lines = [f"# FIX_PROPOSALS — engine frictions, drained {date}", ""]
    lines.append("DRAFT-ONLY. Nothing below is applied; the drain never applies and "
                 "never writes the retiring resolution. The engine's B10-analogue is "
                 "SUITE + JUDGE: an applied bite must show (a) the full pytest suite "
                 "green on the POST state and (b) a separate verification pass "
                 "(builder ≠ judge) confirming the fix against the friction that "
                 "demanded it. An apply that cannot show both is not an apply.")
    lines.append("")
    for key in sorted(groups):
        recs = sorted(groups[key], key=lambda r: str(r.get("id") or ""))
        lines.append(f"## {_group_heading(key)} — {len(recs)} open friction(s)")
        lines.append("")
        for r in recs:
            lines.append(f"### `{r.get('id')}` — {r.get('node')}")
            lines.append(f"- friction (verbatim): {r.get('value')!r}")
            chain = _chain_of(r)
            if chain:
                lines.append("- chain of custody (coarse→fine): "
                             + " → ".join(chain))
            if r.get("cost"):
                lines.append(f"- cost: {r.get('cost')}")
            lines.append(f"- by: `{r.get('by') or ''}`  ts: `{r.get('ts') or ''}`")
            if r.get("proposal"):
                lines.append("- reporter's proposal (advisory, never an "
                             f"instruction): {r.get('proposal')}")
            lines.append("")
        lines.append("**Proposed bite:** shape the code/doc change from the quoted "
                     "proposals; the author ratifies before any build.")
        lines.append("**Verification:** `pytest -q` green on the POST state + a "
                     "judge pass against the quoted frictions.")
        lines.append("")
        lines.append("**Close the loop (POST-APPLY — the drain does NOT write this).** "
                     "Once ratified AND suite+judge pass, retire each consumed "
                     f"friction by appending to `{ledger_rel}`:")
        lines.append("")
        lines.append("```python")
        lines.append("from laplace.pipeline import friction_consumer, ledger")
        first_id = recs[0].get("id")
        lines.append(f"rec = friction_consumer.make_friction_resolution({first_id!r},")
        lines.append("    evidence='<commit hash / evolution dir / OPEN_STACK row>')")
        lines.append(f"ledger.append_jsonl({ledger_rel!r}, rec)")
        lines.append("```")
        lines.append("")
        lines.append("An evidence-less resolution leaves its target OPEN — the "
                     "drain's validator flags it.")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# the batch driver — the drain
# ---------------------------------------------------------------------------

def drain(repo_root: Path | str, ledger_path: Path | str | None = None,
          out_dir: Path | str | None = None, date: str | None = None) -> dict:
    """Drain the friction ledger: route every open record out one of the three
    exits, draft ``FIX_PROPOSALS.md``, emit the digest, flag evidence-less
    resolutions, escalate unknown kinds. Returns the summary dict the CLI
    prints (``drafted``/``escalated`` mirroring ``consume_intents``). The
    engine ledger itself is NEVER written — draft-only throughout."""
    repo_root = Path(repo_root)
    ledger = Path(ledger_path) if ledger_path else (
        repo_root / "corpus_friction" / "laplace_engine.jsonl")
    date = date or _dt.date.today().isoformat()
    records = read_jsonl(ledger) if ledger.is_file() else []
    opens = open_frictions(records)
    flagged = invalid_resolutions(records)
    consumed = consumed_frictions(records)

    # escalation: an open, unretired record whose kind is admitted NOWHERE
    # (not a rewire, not a pass-through, not friction/fork, not an adjudication
    # record) — mis-shaped writes the typed door would have refused.
    known = set(_schema.REWIRE_KINDS) | _schema.AUXILIARY_RECORD_KINDS
    retired = _retired_ids(records)
    escalated = [
        {"escalated": True, "id": r.get("id"), "kind": r.get("kind"),
         "node": r.get("node"),
         "reason": f"unknown kind {r.get('kind')!r}: admitted by no write gate "
                   "— routes to the author"}
        for r in records if isinstance(r, dict)
        and r.get("record") not in _adj.ADJ_RECORD_KINDS
        and (r.get("status") or "open") == "open"
        and r.get("id") not in retired
        and r.get("kind") not in known]

    forks = [r for r in opens if r.get("kind") == "fork"]
    delegated: list[dict] = []
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in opens:
        if r.get("kind") != "friction":
            continue
        proj = _corpus_project(str(r.get("owning_layer") or ""))
        if proj is not None:
            delegated.append(_delegate(repo_root, proj, r))
        else:
            groups.setdefault(_group_key(r), []).append(r)

    drafted: list[dict] = []
    fix_path = None
    if groups:
        try:
            ledger_rel = str(ledger.relative_to(repo_root))
        except ValueError:
            ledger_rel = str(ledger)
        out_root = Path(out_dir) if out_dir else repo_root
        evo_dir = out_root / "evolutions_engine" / date
        evo_dir.mkdir(parents=True, exist_ok=True)
        fix_path = evo_dir / "FIX_PROPOSALS.md"
        fix_path.write_text(_fix_proposals_md(groups, date, ledger_rel),
                            encoding="utf-8")
        # summary entries mirror the rollup law: a chain group names its
        # prefix (the shared descent), a chainless group its owning layer
        drafted = []
        for key in sorted(groups):
            ids = [r.get("id") for r in
                   sorted(groups[key], key=lambda r: str(r.get("id") or ""))]
            if key[0] == "chain":
                drafted.append({"chain_prefix": key[1].split(" › "),
                                "frictions": ids})
            else:
                drafted.append({"owning_layer": key[1], "frictions": ids})

    dpath = digest_path(ledger)
    dpath.write_text(digest_md(records, ledger.stem), encoding="utf-8")

    return {"ledger": str(ledger), "open": len(opens), "consumed": len(consumed),
            # the visible gap: open records with NO chain of custody (seed
            # records predate the field; chain is recommended, not required)
            "chainless": sum(1 for r in opens if not _chain_of(r)),
            "drafted": drafted,
            "fix_proposals": str(fix_path) if fix_path else None,
            "open_stack_rows": [open_stack_row(r, date) for r in
                                sorted(forks, key=lambda r: str(r.get("id") or ""))],
            "delegated": delegated,
            "flagged": [{"resolution": r.get("id"), "target": r.get("supersedes"),
                         "reason": "evidence-less resolution — target stays OPEN"}
                        for r in flagged],
            "escalated": escalated,
            "digest": str(dpath)}
