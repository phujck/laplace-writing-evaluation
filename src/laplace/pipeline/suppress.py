"""Fingerprinted suppression — the calibration solvent's seam (Phase F).

The dismiss-verdict filter the fixer runs BEFORE spending tokens: a finding the
author (or a prior round) has ruled a non-fault is dropped before it reaches the
generating machinery, so no token is spent re-litigating it. This is the
mechanism that makes each calibration round cheaper than the last.

The hardening (his review, 2026-07-09): a suppression is not eternal. It carries
a **content fingerprint** of the node it was ruled on; when the node's content
changes materially the fingerprint no longer matches and the suppression goes
**STALE** — the finding is judgeable again. A regenerated node is a new object;
its old dismissal does not carry over. Suppression must never hide a reborn fault.

Ledger conventions (reused, not reinvented): a suppression rides the SAME
``feedback.jsonl`` append-only ledger as every intake/review record
(``schema.FEEDBACK_FIELDS``: id/project/ts/scope/kind/node_id/section/anchor/…).
It is marked by a top-level ``record: "suppression"`` discriminator and carries
``supersedes``-style provenance ``{reason, actor, round, fingerprint}`` (a later
suppression naming an earlier one's id revokes it — the widen/revoke gesture).

Two deliberate choices where the shared ledger constrains the record shape:

  * the ``kind`` field holds the *suppressed finding-kind* (so ``(node, kind)``
    matching reuses the finding's own kind), OR the wildcard ``"*"`` for a
    widen-scope suppression that silences every kind on the node;
  * a suppression record carries ``status: "resolved"`` so ``propagate.intake_items``
    — which reads the same ledger and refuses unrouted kinds — SKIPS it via the
    existing spent-record path (the ``status == "resolved"`` guard precedes the
    ``kind in KIND_TO_WORK`` check), so a wildcard ``"*"`` kind never trips the
    unrouted-kind door. This keeps suppress.py additive: the convergence CONTRACT
    modules (schema/propagate) are untouched.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import re
from pathlib import Path
from typing import Any, Iterable

from laplace.pipeline.ledger import append_jsonl, read_jsonl

#: the top-level discriminator marking a feedback record as a suppression.
RECORD_KIND = "suppression"
#: the record type that RETIRES an earlier suppression (the widen/dismiss undo).
#: Not a suppression itself, so :func:`load_suppressions` never counts it active;
#: its ``supersedes`` retires the named suppression id.
REVOKE_KIND = "suppression-revoke"
#: the wildcard finding-kind: silence every kind on the node (widen gesture).
WILDCARD = "*"

# ---------------------------------------------------------------------------
# content fingerprint
# ---------------------------------------------------------------------------

# a LaTeX line comment: an unescaped `%` to end of line. `(?<!\\)` leaves `\%`
# (an escaped percent) in place; the double-backslash edge (`\\%`) is accepted
# as good-enough for a fingerprint normaliser (documented, not silently perfect).
_COMMENT_RE = re.compile(r"(?<!\\)%.*$", re.MULTILINE)
_WS_RE = re.compile(r"\s+")


def normalise(text: str) -> str:
    """Whitespace/comment-normalised content: strip LaTeX line comments, collapse
    every whitespace run to a single space, trim. The invariant the fingerprint
    is stable under — reflowing, re-indenting, or re-commenting a node does NOT
    change its fingerprint; changing the *substance* does."""
    if not text:
        return ""
    stripped = _COMMENT_RE.sub("", text)
    return _WS_RE.sub(" ", stripped).strip()


def content_fingerprint(text: str) -> str:
    """A short, stable hash over the whitespace/comment-normalised content. Stable
    across processes (sha256, not the salted builtin ``hash``), so a fingerprint
    banked in the ledger this round matches next round for unchanged content."""
    norm = normalise(text)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# building + loading suppression records
# ---------------------------------------------------------------------------

def _finding_node(obj: dict) -> str:
    """The node/section id a finding or suppression is anchored to. Tolerant of
    the field spellings the surfaces emit (node_id / node / where)."""
    for k in ("node_id", "node", "where"):
        v = obj.get(k)
        if v:
            return str(v).strip()
    anchor = obj.get("anchor") or {}
    return str(anchor.get("node") or anchor.get("section") or "").strip()


def _supp_fingerprint(rec: dict) -> str:
    """The content fingerprint a suppression was ruled on (top-level, falling back
    to the provenance mirror)."""
    fp = rec.get("fingerprint")
    if fp:
        return str(fp)
    return str((rec.get("provenance") or {}).get("fingerprint") or "")


def make_suppression(node_id: str, kind: str, node_text: str, *, reason: str,
                     actor: str, round: int, project: str = "", section: str = "",
                     scope: str = "node", anchor: dict | None = None,
                     supersedes: str | None = None,
                     rec_id: str | None = None, ts: str | None = None) -> dict:
    """Construct a suppression record (not yet written). ``kind`` is the finding-
    kind to silence on ``node_id``, or :data:`WILDCARD` for every kind. The
    content fingerprint is taken from ``node_text`` NOW, so a later material edit
    to the node makes this suppression stale. Provenance is
    ``{reason, actor, round, fingerprint}``."""
    fp = content_fingerprint(node_text)
    now = ts or _dt.datetime.now().isoformat(timespec="seconds")
    rid = rec_id or _dt.datetime.now().strftime("SUP-%Y%m%d-%H%M%S-%f")
    rec = {
        "id": rid,
        "record": RECORD_KIND,
        "project": project,
        "ts": now,
        "scope": scope,
        "kind": kind,
        "node_id": node_id,
        "section": section,
        "anchor": anchor or {},
        "text": f"suppressed {kind!r} on {node_id!r}: {reason}",
        "source": actor,
        "fingerprint": fp,
        "provenance": {"reason": reason, "actor": actor, "round": round,
                       "fingerprint": fp},
        # so propagate.intake_items skips it (spent-record path) and never trips
        # its unrouted-kind door on a wildcard kind.
        "status": "resolved",
    }
    if supersedes:
        rec["supersedes"] = supersedes
    return rec


def make_revocation(supp_id: str, *, reason: str = "", actor: str = "author",
                    round: int = 0, project: str = "", rec_id: str | None = None,
                    ts: str | None = None) -> dict:
    """A REVOKE record superseding an active suppression ``supp_id`` — the widen
    gesture's one-click undo (and any dismissal's undo). :func:`load_suppressions`
    honours the ``supersedes`` field, so appending this retires ``supp_id`` from
    the active set on the next load. Carries ``status: "resolved"`` so
    ``propagate.intake_items`` skips it via the spent-record path, exactly like a
    suppression."""
    now = ts or _dt.datetime.now().isoformat(timespec="seconds")
    return {
        "id": rec_id or _dt.datetime.now().strftime("REV-%Y%m%d-%H%M%S-%f"),
        "record": REVOKE_KIND,
        "project": project,
        "ts": now,
        "supersedes": supp_id,
        "source": actor,
        "text": f"revoked suppression {supp_id!r}" + (f": {reason}" if reason else ""),
        "provenance": {"reason": reason, "actor": actor, "round": round},
        "status": "resolved",
    }


def append_suppression(feedback_path: str | Path, rec: dict) -> None:
    """Append one suppression (or revocation) record to the shared feedback
    ledger — both ride the one door append-only."""
    append_jsonl(feedback_path, rec)


def is_suppression(rec: dict) -> bool:
    return isinstance(rec, dict) and rec.get("record") == RECORD_KIND


def load_suppressions(feedback_path: str | Path) -> list[dict]:
    """The ACTIVE suppression records in the ledger: every ``record: "suppression"``
    record that has not been retired by a later record's ``supersedes`` (the
    revoke/widen gesture). Order-preserving (ledger order)."""
    records = read_jsonl(feedback_path)
    superseded = {r["supersedes"] for r in records
                  if isinstance(r, dict) and r.get("supersedes")}
    return [r for r in records
            if is_suppression(r) and r.get("id") not in superseded]


# ---------------------------------------------------------------------------
# the filter — the fixer's pre-spend gate
# ---------------------------------------------------------------------------

def _matches_node_kind(supp: dict, node: str, kind: str) -> bool:
    """Whether a suppression targets this (node, kind): node ids equal AND the
    suppression kind is the finding kind OR the wildcard."""
    if _finding_node(supp) != node:
        return False
    sk = str(supp.get("kind") or "")
    return sk == WILDCARD or sk == kind


def filter_findings(findings: Iterable[dict], suppressions: Iterable[dict],
                    node_text: dict[str, str]) -> dict[str, list[dict]]:
    """Split ``findings`` into ``{kept, suppressed, stale}``.

    A finding is **suppressed** iff an active suppression matches its ``(node,
    kind)`` AND the suppression's stored fingerprint equals the node's CURRENT
    fingerprint (from ``node_text``: node/section id -> current text). A
    ``(node, kind)`` match whose fingerprint MISMATCHES marks the suppression
    **STALE** — it is returned separately and NEVER applied, and the finding is
    kept (a regenerated node is judgeable again). A finding whose node is absent
    from ``node_text`` cannot have its fingerprint confirmed, so it is kept (we
    re-judge rather than hide a possibly-changed node).

    ``stale`` is the list of stale suppression records (deduplicated by id).
    ``kept``/``suppressed`` are the input findings, partitioned.
    """
    supps = list(suppressions)
    kept: list[dict] = []
    suppressed: list[dict] = []
    stale: list[dict] = []
    stale_ids: set[str] = set()

    for finding in findings:
        node = _finding_node(finding)
        kind = str(finding.get("kind") or "")
        matched = [s for s in supps if _matches_node_kind(s, node, kind)]
        if not matched:
            kept.append(finding)
            continue
        # is the current node text known, and does any match's fingerprint still hold?
        if node not in node_text:
            # cannot confirm the fingerprint -> do not hide it.
            kept.append(finding)
            continue
        current_fp = content_fingerprint(node_text[node])
        live = [s for s in matched if _supp_fingerprint(s) == current_fp]
        dead = [s for s in matched if _supp_fingerprint(s) != current_fp]
        if live:
            suppressed.append(finding)
        else:
            kept.append(finding)
        for s in dead:
            sid = s.get("id")
            if sid not in stale_ids:
                stale_ids.add(sid)
                stale.append(s)

    return {"kept": kept, "suppressed": suppressed, "stale": stale}
