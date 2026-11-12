"""Author edit-in-place records — the TERMINAL rung of the interaction ladder (B4).

His ruling (2026-07-10): the interaction ladder is edit-in-place (the author's
authority, TERMINAL — never regenerated) → local patch → paragraph regen →
section regen → substrate evolution. When the author edits a paragraph (or a
whole section) by hand on the review surface, that is the last word on those
bytes: the pipeline never regenerates over them.

Structured edit CAPTURE from day one (the EDIT_FATES analogue): every author edit
banks ONE append-only ``author-edit`` record on the SAME ``feedback.jsonl`` the
adjudication/suppression records ride (the one door). A record carries a
before/after/anchor/kind and — mirroring the suppression's spent-record shape —
``status: "resolved"`` so ``propagate.intake_items`` (and the route's findings
filter) treat it as spent: an edit is never itself WORK, only a protection. The
exploitation ladder (learning FROM the banked edits) stays dormant until the
author ratifies each rung; this module only DEPOSITS, correctly shaped, and reads
the protected units back for the route.

The id/provenance conventions mirror :mod:`adjudicate` exactly (timestamp id via a
prefix, a ``{actor, verdict, round, ts}`` provenance block); the ``live_edits`` /
supersede semantics mirror :func:`adjudicate.live`.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Iterable

from laplace.pipeline.suppress import content_fingerprint

#: the top-level ``record`` discriminator for an author edit-in-place.
RECORD_KIND = "author-edit"


# ---------------------------------------------------------------------------
# small shared shape helpers (mirror adjudicate.py)
# ---------------------------------------------------------------------------

def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _rid(prefix: str) -> str:
    return _dt.datetime.now().strftime(f"{prefix}-%Y%m%d-%H%M%S-%f")


def _prov(actor: str, verdict: str, round, ts: str) -> dict:
    return {"actor": actor, "verdict": verdict, "round": round, "ts": ts}


# ---------------------------------------------------------------------------
# the record builder (the surface applies + appends through the one door)
# ---------------------------------------------------------------------------

def make_author_edit(section: str, paragraph_id: str, file: str, before: str,
                     after: str, kind: str = "unspecified", lines=None,
                     round=None, *, project: str = "", actor: str = "author",
                     rec_id: str | None = None, ts: str | None = None,
                     spec_ids: list[str] | None = None) -> dict:
    """One append-only ``author-edit`` record capturing a hand edit the author
    applied in place. ``status: "resolved"`` (an edit is a PROTECTION, never work —
    intake stays spent); the content ``fingerprint`` is taken over ``before`` NOW
    (the bytes the edit replaced), so the record dates itself to the state it acted
    on. ``paragraph_id`` may be ``""`` — a whole-section edit — which protects the
    entire section. The record is not yet written; the surface appends it."""
    now = ts or _now()
    return {
        "id": rec_id or _rid("EDIT"),
        "record": RECORD_KIND,
        "project": project,
        "ts": now,
        "before": before,
        "after": after,
        "anchor": {"section": section, "paragraph_id": paragraph_id,
                   "file": file, "lines": lines,
                   **({"spec_ids": list(dict.fromkeys(spec_ids))} if spec_ids is not None else {})},
        "kind": kind,
        "fingerprint": content_fingerprint(before or ""),
        "source": actor,
        "status": "resolved",              # an edit is never work; intake skips it
        "provenance": _prov(actor, "edit-in-place", round, now),
    }


# ---------------------------------------------------------------------------
# readers — the surface + the route consume these; a supersede retires an edit
# ---------------------------------------------------------------------------

def live_edits(records: Iterable[dict]) -> list[dict]:
    """The author-edit records not retired by a later ``supersedes`` (the same
    revoke gesture the adjudication/suppression records honour — an edit can be
    withdrawn append-only, never by rewriting history)."""
    recs = [r for r in records if isinstance(r, dict)]
    superseded = {r.get("supersedes") for r in recs if r.get("supersedes")}
    return [r for r in recs
            if r.get("record") == RECORD_KIND and r.get("id") not in superseded]


def protected_units(records: Iterable[dict]) -> set:
    """The ``(section, paragraph_id)`` units the author edited by hand — the spans
    the pipeline never regenerates over. ``paragraph_id`` is ``""`` for a
    whole-section edit (which protects the whole section). Live edits only; a
    superseded edit's protection lifts."""
    out: set = set()
    for r in live_edits(records):
        anchor = r.get("anchor") or {}
        section = str(anchor.get("section") or "").strip()
        paragraph_id = str(anchor.get("paragraph_id") or "").strip()
        if section:
            out.add((section, paragraph_id))
            for ident in anchor.get("spec_ids") or []:
                if isinstance(ident, str) and ident:
                    out.add((section, ident))
    return out


# ---------------------------------------------------------------------------
# THE FRAGMENT-LANDING RETIRE (W-CONSUMER, 2026-07-22) — the findings consumer's
# LAND half. edits.py is the terminal record-banking rung; this is its machine-side
# twin. When a REGENERATED fragment for a section LANDS at round N, every OPEN machine
# finding anchored to that section from a PRIOR round is CONSUMED: the regeneration
# superseded the bytes those findings were raised on. Each retires with an append-only
# ``consumed_by {round, packet}`` resolution (manuscript_bridge.feedback_consume). The
# CURRENT round's fresh findings (the panel's re-detection of survivors — a new id, a new
# content fingerprint) are untouched, so retirement never hides a live defect; a survivor
# is simply re-found by the panel. This is the ledger-explicit form of the round-
# supersession `ledger.live_findings` already performs implicitly (only the latest panel
# round is live), so the raw ledger, the census counts, and every consumer finally agree.
# ---------------------------------------------------------------------------

def retire_consumed_findings(feedback_path: "str | Path", section: str, *,
                             round: int, packet_id: str, project: str = "",
                             actor: str = "findings-consumer",
                             repo: "Path | None" = None,
                             records: "Iterable[dict] | None" = None) -> dict:
    """Retire the machine findings a landed fragment consumed. Selects the OPEN machine
    findings anchored to ``section`` from rounds STRICTLY BEFORE ``round`` (the current
    round's fresh re-mint is kept), and appends one consumed-by resolution per finding via
    :func:`manuscript_bridge.feedback_consume`. Append-only — a surviving defect is
    re-opened plainly by the next panel scan. Idempotent across re-lands of the SAME round:
    an already-consumed (superseded) finding is no longer live, so a second call finds
    nothing new. Returns ``{retired:[ids], count, section, round, packet}``."""
    from laplace.manuscript import manuscript_bridge as _mb
    from laplace.pipeline.ledger import read_jsonl
    path = Path(feedback_path)
    recs = list(records) if records is not None else (
        read_jsonl(path) if path.is_file() else [])
    victims = _mb.machine_findings_for_section(recs, section, before_round=round)
    retired: list[str] = []
    for f in victims:
        res = _mb.feedback_consume(repo, project, f, round=round, packet=packet_id,
                                   actor=actor, ledger=path)
        if res.get("ok"):
            retired.append(res["supersedes"])
    return {"retired": retired, "count": len(retired), "section": section,
            "round": round, "packet": packet_id}
