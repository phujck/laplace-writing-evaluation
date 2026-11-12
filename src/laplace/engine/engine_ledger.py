"""engine_ledger.py — the engine's obligation ledger and row graph: what its record kinds MEAN.

The durable mechanisms (append, journal, row reading, the graph walk) are core:
:mod:`laplace.core.records`. This module is the engine domain's qualification of
them: its obligation-record classes, the resolution join, defer and strikes
conventions, and the engine's row-graph scope (its stores and legacy link dialect).
Writing's records are qualified separately, in :mod:`laplace.writing.records`.

THE EFFECTIVE-STATUS JOIN: one helper for a ledger row's EFFECTIVE status.

WO-20260820-ledger-semantics-hardening, cure (a). The live archaeology this session
paid: a work-order row's own ``status`` field is RAISE-TIME-ONLY — it is written when
the row is minted and is never rewritten when a later ``record: "resolution"`` row
consumes it (``consumes: <the raised id>``). A reader that trusts the stored field
alone can read ``status: "open"`` on a row that has in fact been resolved for weeks.
This module computes the EFFECTIVE status instead: if some resolution row's
``consumes`` names this row's id, the row is effectively that resolution's status
(default ``"resolved"``) NO MATTER what its own stored ``status`` field says. The
stored field is never mutated and never lies on its own terms — it is simply not the
last word on whether a row is done. Every reader that needs "is this row actually
still open" (desk renders, the handoff render, the probe sweep) should call through
here rather than re-deriving the RES-row join by hand.

Cure (c), same work-order: ``kind`` normalization. Two spellings of the same token
have both been written to the ledgers over the corpus's life — ``"work-order"``
(the convention every current reader filters on, 188 rows) and ``"work_order"``
(the ``record`` field's own convention, 51 rows, same rows in most cases but not a
guaranteed alias). ``normalize_kind`` / ``row_kind`` below canonicalize to the
hyphenated form AT READ TIME ONLY — no writer changes, no history rewrite; a row
minted tomorrow with either spelling in either field still classifies correctly.

Cure (b), same work-order: the ``strikes`` field's semantics are DEFINED here — see
:data:`STRIKES_EXEMPLAR` and :func:`strikes_exempt` — so the sweep, the desk and any
later reader share one statement of the convention instead of three paraphrases.

This module is read-only: it never writes to a ledger file. Callers load rows with
``laplace.core.records.rows.load_records`` (or bring their own already-parsed rows)
and pass them through the functions below.

THE ENGINE ROW GRAPH (``ROW_GRAPH``, walked by :mod:`laplace.core.records.lineage`).
Its stores are every ``*.jsonl`` under ``corpus_friction/`` and ``contract/`` plus
``proxy_verdicts.jsonl`` at the root. Its legacy map, each old field's implied rel
said once -- ``target``, by the record/kind that carries it (the field is too
overloaded to read kind-blind)::

    amendment  -> amends       an amendment changes its target, never replaces it
    resolution -> resolves     a resolution closes its target
    defer      -> amends       a defer changes the target's state without closing it
    undefer    -> amends       likewise, in the other direction
    ruling     -> grades       a ruling is a verdict ON its target
    prediction_scoring / prediction-scoring -> grades
    fence-verdict -> grades

Kind-independent fields, whose own NAME already states the relation::

    resolves    -> resolves
    supersedes  -> supersedes
    consumes    -> consumes
    absorbs     -> consumes    (an amendment absorbing a work order)
    cures       -> cures
    corrects    -> cures
    packet      -> grades      a verdict row naming the packet it judged
    evidence    -> grounds     an entry that IS a row id: this row rests on that one
    refs        -> grounds
    depends_on  -> grounds
    blocked_by  -> grounds

Each may hold a string or a list of them. ``packet``, ``cures`` and ``evidence``
routinely hold PROSE as well as ids -- the walker's resolution guard is what makes
reading them safe: prose does not resolve, so prose does not become an edge.

DELIBERATELY NOT CONSUMED. The graph-corpus verbs — ``add-node``, ``add-edge``,
``set-spine``, ``set-projection``, ``edit-essence``, ``set-status``, ``set-kind``,
``move-node``, ``delete-node``, ``remove-edge``, ``unset-spine``, ``friction``,
``fork``, ``conceptric-intent`` — also carry ``target``, but theirs is a NODE id
inside a conceptric graph, a different address space that happens to share a
field name. Walking them would silently splice two graphs together. ``note``'s
``target`` is left out too: a note beside a work order has no rel in the closed
vocabulary that is honestly true of it. Both are additions a future row can make
explicitly, with ``edges``.

CLI::

    python3 -m laplace.engine.engine_ledger <row-id> [--depth N] [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Optional

from laplace.core.identity import canonical_digest
from laplace.core.records import lineage

#: record types that consume another row's id via a `consumes` field. Only
#: "resolution" is observed in the corpus today (corpus_friction/work_orders.jsonl);
#: kept as a tuple, not a single string, so a sibling consuming-record type can be
#: added without touching every call site.
_CONSUMING_RECORDS = ("resolution",)

#: the fields a consuming record may use to name the row it closes, in PRECEDENCE
#: order. Live corpus (corpus_friction/work_orders.jsonl, 165 resolutions): 103 rows
#: carry all three, 26 consumes+target, 23 supersedes+target, 12 target alone — so a
#: consumes-only index misses 35 real closures and reads them as still open, which is
#: the exact archaeology this work-order cures. ``consumes`` is the field the
#: resolution schema defines for the join and wins wherever it is present; the other
#: two are the fallback for the rows that never carried it. A single live row
#: (RES-20260820-dreamer-freeze-flag) carries a PROSE-annotated ``consumes``
#: ("<id> (leg 1 only)") that its ``supersedes``/``target`` state cleanly — indexing
#: every named id, with per-id precedence, keeps both readings reachable.
LINK_FIELDS = ("consumes", "supersedes", "target", "consumed_by")
_LINK_FIELDS = LINK_FIELDS
SEMANTIC_LEDGER_INTEGRITY = "semantic-ledger-integrity"

RESOLUTION_CLOSE = "close"
RESOLUTION_REOPEN = "reopen"
RESOLUTION_UNKNOWN = "unknown"

_TYPED_DISPOSITION_FIELDS = ("disposition", "effect")
_REOPEN_DISPOSITIONS = frozenset({"open", "reopen", "reopened", "held_open"})
_CLOSE_DISPOSITIONS = frozenset({
    "close", "closed", "resolve", "resolved", "retire", "retired", "consume",
    "consumed", "absorb", "absorbed",
})
_LEGACY_HOLD_FIELDS = ("status", "text", "action", "note", "reason")
_LEGACY_HOLD_RE = re.compile(
    r"(?:\[\s*open\s*\]|\bheld(?:[\s_-]+)open\b)", re.IGNORECASE,
)

DEFER_DATE_ABSENT = "absent"
DEFER_DATE_CONDITION = "condition"
DEFER_DATE_VALID = "valid"
DEFER_DATE_INVALID = "invalid"



#: THE ``strikes`` FIELD, DEFINED (cure b). ``strikes`` is a STRING naming who or what
#: may strike a row off — NOT a count, and never a boolean. The promise ledger's own
#: exemplar (5 live rows in contract/promises.jsonl) is the value below: a mechanical
#: probe proves the ARTEFACT half of a promise only, never that the relational promise
#: to a person is kept, so such a row is never auto-proposed for strike-off no matter
#: how green its probe runs. A row with NO ``strikes`` field is strikeable-by-probe
#: (the work-order ledger's default — no exemption stated, none assumed). The field is
#: read, never written, by every reader in this repo.
STRIKES_EXEMPLAR = "never — artefact half only; reports, never auto-proposes"


def row_strikes(row: dict) -> Optional[str]:
    """The row's ``strikes`` field as a non-empty string, or ``None``. A non-string
    value is not a declaration and reads as absent — see :data:`STRIKES_EXEMPLAR`."""
    value = row.get("strikes")
    if isinstance(value, str) and value.strip():
        return value
    return None


def strikes_exempt(row: dict) -> bool:
    """True iff the row DECLARES a ``strikes`` exemption and is therefore never
    auto-proposed for strike-off. One statement of the convention: readers ask this
    rather than re-deriving ``not rec.get("strikes")`` at each call site."""
    return row_strikes(row) is not None


def normalize_kind(value: Optional[str]) -> Optional[str]:
    """Canonicalize a kind/record token to the hyphenated form every current reader
    filters on (``"work-order"``, not ``"work_order"``). Non-string / empty input
    passes through unchanged — this is a normalization, not a validator."""
    if not isinstance(value, str) or not value:
        return value
    return value.replace("_", "-")


#: The canonical obligation-ledger class vocabulary.  Classification is a semantic
#: operation, distinct from :func:`row_kind`'s lexical projection: a known ``record``
#: class wins, then a known ``kind`` class, then the historical id-prefix grammar.
#: Keeping this here makes account(), storyboard, the dashboard and the generic
#: effective-status join ask the same question of the same code.
RECORD_CLASSES = frozenset({
    "promise", "resolution", "work_order", "note", "defer", "undefer",
    "defer_note", "amendment", "ruling", "prediction", "prediction_scoring",
    "proxy_verdict", "gap", "cross_verdict", "score", "intent",
    "external_verdict", "open_stack_fork", "verdict", "finding", "walk_verdict",
    "walk_verdict_retraction", "shown_custody_link", "want", "synthesis",
})
CLASS_ALIASES = {"work_order_defer_note": "defer_note"}
PREFIX_RECORD = {
    "PRM": "promise", "RES": "resolution", "WO": "work_order", "NOTE": "note",
    "PV": "proxy_verdict", "GAP": "gap", "XV": "cross_verdict",
    "AMEND": "amendment", "RUL": "ruling", "SCORE": "score", "P": "prediction",
    # Obligation-store classes added after the original seven-class account. These
    # are fallbacks for historical rows whose explicit discriminator is absent.
    "FIND": "finding", "ADJ": "resolution", "DEFER": "defer",
    "VERDICT": "verdict", "RETRACT": "walk_verdict_retraction",
    "LINK": "shown_custody_link", "W": "want", "SYNTH": "synthesis",
}


def _class_token(value: Any) -> str:
    """Canonical account spelling for one possible class token."""
    if not isinstance(value, str) or not value.strip():
        return ""
    token = value.strip().lower().replace("-", "_")
    return CLASS_ALIASES.get(token, token)


def classify_row(row: dict) -> tuple[str | None, str]:
    """Return ``(class, source)`` under the one obligation classification law.

    ``source`` is ``record``, ``kind``, ``id-prefix`` or ``none``.  An explicit but
    unknown ``record`` does not hide a known ``kind`` (the live ``record:memo`` +
    ``kind:work-order`` shape), and absent/unknown fields do not hide a typed ``WO-``
    or ``RES-`` identity.  Consumers that serve diagnostics can use the source to name
    a prefix fallback; boolean readers simply consume the class.
    """
    for field in ("record", "kind"):
        token = _class_token(row.get(field))
        if token in RECORD_CLASSES:
            return token, field
    match = re.match(r"([A-Z]+)-", str(row.get("id", "")))
    if match and match.group(1) in PREFIX_RECORD:
        return PREFIX_RECORD[match.group(1)], "id-prefix"
    return None, "none"


def record_class(row: dict) -> str | None:
    """The canonical semantic class, without its diagnostic source."""
    return classify_row(row)[0]


def row_kind(row: dict) -> Optional[str]:
    """The row's normalized kind: prefer the ``kind`` field; fall back to ``record``
    when ``kind`` is absent or empty (some rows — e.g. resolutions — carry a
    meaningful ``record`` and an empty ``kind``). Always returns the hyphenated
    canonical form, or ``None`` if the row carries neither field."""
    kind = row.get("kind")
    if isinstance(kind, str) and kind:
        return normalize_kind(kind)
    return normalize_kind(row.get("record"))


def is_work_order(row: dict) -> bool:
    """True iff the row's normalized kind is ``"work-order"`` (accepts either
    on-disk spelling in either the ``kind`` or ``record`` field)."""
    return record_class(row) == "work_order"


def is_resolution(row: dict) -> bool:
    """True for either historical resolution shape, including kind-only rows.

    ``record`` is the class discriminator when present; ``kind`` is the fallback for
    older rows such as ``RES-20260820-walk-figure-trust-root``. Do not use
    :func:`row_kind` here: a modern resolution may carry a meaningful subtype in
    ``kind`` beside ``record: resolution`` and the record class must still win.
    """
    return record_class(row) == "resolution"


def evidence_refs(row: dict) -> list[str]:
    """Normalised, non-empty evidence refs carried by a disposition row.

    Strings and string lists are the two historical shapes. Non-string members do
    not become truthy placeholders: ``[None]`` is absent evidence, not proof.
    """
    raw = row.get("evidence")
    if isinstance(raw, str):
        return [raw.strip()] if raw.strip() else []
    if isinstance(raw, (list, tuple)):
        return [item.strip() for item in raw
                if isinstance(item, str) and item.strip()]
    return []


def _disposition_token(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip().casefold().replace("-", "_").replace(" ", "_")


def resolution_disposition(row: dict) -> str:
    """Return the typed effect of one resolution: close, reopen, or unknown.

    New rows may carry an explicit ``disposition``/``effect`` enum.  An explicit but
    unknown value is *not* allowed to fall through to the historical close default: it
    is an unknown boundary value and therefore changes no state.  Historical rows keep
    one compatibility seam.  ``status: open`` or a hold token in the five observed prose
    fields reopens; the token is Unicode-normalised, case-insensitive and whitespace/
    hyphen tolerant so a spelling or line-wrap cannot invert an authenticated act.

    The prose seam is a migration reader, not the target schema.  Typed relation
    migration can replace it without changing callers because every consumer asks this
    function rather than matching its own substring.
    """
    if not is_resolution(row):
        return RESOLUTION_UNKNOWN
    for field in _TYPED_DISPOSITION_FIELDS:
        if field not in row:
            continue
        token = _disposition_token(row.get(field))
        if token in _REOPEN_DISPOSITIONS:
            return RESOLUTION_REOPEN
        if token in _CLOSE_DISPOSITIONS:
            return RESOLUTION_CLOSE
        return RESOLUTION_UNKNOWN

    status = row.get("status")
    if isinstance(status, str) and status.strip().casefold() == "open":
        return RESOLUTION_REOPEN
    for field in _LEGACY_HOLD_FIELDS:
        value = row.get(field)
        if not isinstance(value, str):
            continue
        body = unicodedata.normalize("NFKC", value)
        if _LEGACY_HOLD_RE.search(body):
            return RESOLUTION_REOPEN
    return RESOLUTION_CLOSE


def resolution_reopens(row: dict) -> bool:
    """Whether a resolution-shaped row explicitly holds/reopens its target."""
    return resolution_disposition(row) == RESOLUTION_REOPEN


def defer_date_state(row: dict) -> tuple[str, date | None]:
    """Classify ``defer_until`` without turning malformed dates into conditions.

    A new condition belongs in ``trigger``. Once ``defer_until`` is present it is an ISO
    date, the exact historical ``condition`` enum, or a semantic wound; the invalid
    state must survive every reader boundary.
    """
    if "defer_until" not in row or row.get("defer_until") is None:
        return DEFER_DATE_ABSENT, None
    raw = row.get("defer_until")
    if not isinstance(raw, str) or not raw.strip():
        return DEFER_DATE_INVALID, None
    if raw.strip().casefold() == "condition":
        # Historical rows wrote this exact enum sentinel in the date slot. It is a
        # declared condition state, not permission for any arbitrary non-date to
        # become an immortal trigger.
        return DEFER_DATE_CONDITION, None
    try:
        return DEFER_DATE_VALID, date.fromisoformat(raw.strip())
    except ValueError:
        return DEFER_DATE_INVALID, None


def resolution_targets(row: dict) -> tuple[str, ...]:
    """Every non-empty target named by a resolution, once, in schema precedence.

    This is the public join vocabulary. Readers must not independently choose
    ``supersedes`` or ``consumes`` and silently miss the other historical shapes.
    Non-resolution rows return an empty tuple so an amendment carrying ``target``
    can never retire anything by accident.
    """
    if not is_resolution(row):
        return ()
    out: list[str] = []
    for field in _LINK_FIELDS:
        value = row.get(field)
        if not isinstance(value, str) or not value.strip():
            continue
        target = value.strip()
        if target not in out:
            out.append(target)
    return tuple(out)


def resolution_link_diagnostics(records: Iterable[dict], *, store: str,
                                path: Path | str | None = None) -> list[dict]:
    """Domain-level wounds in resolution links, content-addressed per source row.

    Historical rows may omit a link or carry an empty/null compatibility field.  A
    present non-null value, however, must be a string: silently ignoring a dict/list
    there can turn a poisoned attempted disposition into an apparently clean history.
    The mechanical JSONL reader cannot know this vocabulary, so this validator lives
    beside the one resolution join and is shared by every work-order account.
    """
    out: list[dict] = []
    for row in records:
        if not isinstance(row, dict) or not is_resolution(row):
            continue
        source_handle = canonical_digest(row)
        for field in LINK_FIELDS:
            value = row.get(field)
            if field not in row or value is None or isinstance(value, str):
                continue
            out.append({
                "integrity_class": SEMANTIC_LEDGER_INTEGRITY,
                "defect": "invalid-resolution-link",
                "store": store,
                **({"path": str(path)} if path is not None else {}),
                "id": row.get("id") or "resolution-without-id",
                "field": field,
                "source_handle": source_handle,
                "source_handle_kind": "canonical-json-object",
                "error": (f"resolution link {field!r} decoded as "
                          f"{type(value).__name__}, expected string or null"),
            })
    return out


def obligation_semantic_diagnostics(records: Iterable[dict], *, store: str,
                                    path: Path | str | None = None) -> list[dict]:
    """Every semantic wound shared by the promise and work-order ledgers.

    This is deliberately store-agnostic.  A target-as-dict or malformed defer date is
    the same wound in ``promises`` as in ``work_orders``; callers may not decide that
    one half of the apex census deserves diagnostics and the other does not.
    """
    rows = [row for row in records if isinstance(row, dict)]
    out = resolution_link_diagnostics(rows, store=store, path=path)
    for row in rows:
        # LAZY on purpose: canonical_digest is a canonical-json dump plus a sha256 over the
        # whole row, and it is wanted only by the two branches below that actually emit a defect.
        # Computed eagerly it ran once per row per sweep and was discarded for every clean row
        # (internals lane seq 1, cause walk-banked-not-verdict).
        disposition = resolution_disposition(row)
        if is_resolution(row) and disposition == RESOLUTION_UNKNOWN:
            typed = next((field for field in _TYPED_DISPOSITION_FIELDS if field in row), None)
            if typed is not None:
                out.append({
                    "integrity_class": SEMANTIC_LEDGER_INTEGRITY,
                    "defect": "invalid-resolution-disposition",
                    "store": store,
                    **({"path": str(path)} if path is not None else {}),
                    "id": row.get("id") or "resolution-without-id",
                    "field": typed,
                    "source_handle": canonical_digest(row),
                    "source_handle_kind": "canonical-json-object",
                    "error": (f"resolution disposition {typed!r} is not in the typed "
                              "close/reopen vocabulary; the row changes no state"),
                })
        state, _parsed = defer_date_state(row)
        if state != DEFER_DATE_INVALID:
            continue
        out.append({
            "integrity_class": SEMANTIC_LEDGER_INTEGRITY,
            "defect": "invalid-defer-until",
            "store": store,
            **({"path": str(path)} if path is not None else {}),
            "id": row.get("id") or "defer-without-id",
            "field": "defer_until",
            "source_handle": canonical_digest(row),
            "source_handle_kind": "canonical-json-object",
            "error": (f"defer_until {row.get('defer_until')!r} is not an ISO date; "
                      "conditions belong in trigger and this row changes no state"),
        })
    return out


def build_consumption_index(records: Iterable[dict]) -> dict[str, dict]:
    """id -> its last authenticated resolution disposition in file order.

    Every link in :data:`_LINK_FIELDS` remains reachable (a consumes-only index reads
    35 closed rows as open), while precedence applies within each source row and file
    order applies between rows.  An older ``consumes`` cannot permanently dominate a
    later held-open ``target`` merely because its field ranked higher.  For work-order
    targets, both close and reopen dispositions require evidence.
    """
    records = [rec for rec in records if isinstance(rec, dict)]
    work_order_ids = {str(rec.get("id")) for rec in records
                      if rec.get("id") and is_work_order(rec)}
    index: dict[str, dict] = {}
    for rec in records:
        if not is_resolution(rec):
            continue
        if resolution_disposition(rec) == RESOLUTION_UNKNOWN:
            continue
        for key in resolution_targets(rec):
            # One disposition law on every reader: a work-order resolution without
            # evidence is a refused attempt, whether it claims to close OR reopen.
            # Otherwise an unauthenticated ``HELD OPEN`` string can override an older
            # evidenced close in the generic index while account() rejects the same act.
            if key in work_order_ids and not evidence_refs(rec):
                continue
            index[key] = rec
    return index


def effective_status(row_id: str, stored_status: Any,
                      index: dict[str, dict]) -> tuple[str, str]:
    """(effective_status, reason). If ``row_id`` is consumed by some resolution row
    in ``index``, effective status is that resolution's own ``status`` field
    (default ``"resolved"`` if the resolution itself carries none), and the reason
    names the consuming row's id. Otherwise the row's stored status stands as-is and
    the reason is ``"stored"`` — the join found nothing to override."""
    consumer = index.get(str(row_id))
    if consumer is not None:
        if resolution_reopens(consumer):
            return "open", f"reopened_by:{consumer.get('id', '?')}"
        eff = consumer.get("status") or "resolved"
        return str(eff), f"consumed_by:{consumer.get('id', '?')}"
    return str(stored_status), "stored"


def effective_status_for_row(row: dict, index: dict[str, dict]) -> tuple[str, str]:
    """Convenience: ``effective_status`` reading ``id``/``status`` off ``row``
    itself. ``status`` defaults to ``"open"`` when the row carries none (the raise-
    time convention: an unstated status on a freshly-minted row means open)."""
    return effective_status(row.get("id", "?"), row.get("status", "open"), index)


# ------------------------------------------------------------------ the engine row graph

#: the two directories that hold the engine's row stores. Everything ``*.jsonl`` under them.
STORE_DIRS = ("corpus_friction", "contract")

#: row stores that live at the REPO ROOT, named one by one rather than globbed --
#: the root is not a store directory and must never become one by accident.
#: ``proxy_verdicts.jsonl`` is where HIS OWN WORDS live (the PV rows), which is to
#: say: the ground of a large share of the engine's rows. Left out until 2026-08-24,
#: every ``raised-by`` pointing at a steer of his read UNRESOLVED -- the walker
#: could show what a row rested on except when what it rested on was the author.
ROOT_STORES = ("proxy_verdicts.jsonl",)

#: legacy ``target``, keyed by the row's ``record``/``kind``. See the module docstring.
LEGACY_TARGET_BY_KIND: dict[str, str] = {
    "amendment": "amends",
    "resolution": "resolves",
    "defer": "amends",
    "undefer": "amends",
    "ruling": "grades",
    "prediction_scoring": "grades",
    "prediction-scoring": "grades",
    "fence-verdict": "grades",
}

#: legacy fields whose own name states the rel, read on any row kind.
LEGACY_FIELDS: dict[str, str] = {
    "resolves": "resolves",
    "supersedes": "supersedes",
    "consumes": "consumes",
    "absorbs": "consumes",
    "cures": "cures",
    "corrects": "cures",
    "packet": "grades",
    "evidence": "grounds",
    "refs": "grounds",
    "depends_on": "grounds",
    "blocked_by": "grounds",
}

ROW_GRAPH = lineage.Scope("engine", STORE_DIRS, ROOT_STORES, LEGACY_TARGET_BY_KIND, LEGACY_FIELDS)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python3 -m laplace.engine.engine_ledger",
        description="Walk the engine's row graph: what a row stands on, and what stands on it.")
    p.add_argument("row_id", help="a row id, optionally store-qualified as store.jsonl#id")
    p.add_argument("--depth", type=int, default=3,
                   help="how many generations each way (default 3; 0 = the row alone)")
    p.add_argument("--json", action="store_true", help="emit the neighborhood as JSON")
    p.add_argument("--root", default=None, help="repo root (default: the serving checkout)")
    a = p.parse_args(sys.argv[1:] if argv is None else argv)

    neigh = lineage.neighborhood(a.row_id, a.depth, root=a.root, scope=ROW_GRAPH)
    if a.json:
        print(json.dumps(neigh, ensure_ascii=False, indent=1))
    else:
        print(lineage.render(neigh, where=ROW_GRAPH.where()))
    return 0 if neigh["row"]["found"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
