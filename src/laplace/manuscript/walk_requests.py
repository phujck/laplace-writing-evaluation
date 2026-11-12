"""The one reader for typed REQUEST rows the redline walk banks.

The walk's card asks (``paintCardAsks`` / ``bankCardComment`` in
``static_shared/walk.mjs``) bank a plain comment through the existing feedback
door (``review_surface.adjudicate`` verb ``comment`` -> ``manuscript_bridge.
feedback_add``) whose text starts with ``"request:"``. Three shapes exist
today:

  * ``"request: find supporting references for this passage"`` (scope
    delivery) -> the citation-direction organ.
  * ``"request: remake this figure (fig:...)"`` (scope delivery, the row's
    anchor carries the figure label through the figure door) -> the figure
    remake campaign.
  * ``"request: a new section after §..."`` (scope structure) -> the
    storyboard/structure intents.

Anything else that still starts with ``"request:"`` is typed ``other-request``
rather than dropped: the walk's own asks are not the only door that can bank a
row in this register.

A request is retired the same way every other ledger row is: a later row
whose ``supersedes`` names its id (the revoke door, ``review_surface.
adjudicate`` verb ``revoke``, appended through ``adjudicate.make_resolution``).
The ledger is append-only, so a revoked request is kept here, flagged
``revoked``, never dropped.

This module does one thing: read a corpus's feedback ledger and hand back the
request rows, typed and flagged, for the organs above to poll. It writes
nothing and adjudicates nothing.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from laplace.pipeline.ledger import read_jsonl

#: the walk's own register: a row is a request iff its comment starts with this,
#: case-sensitive.
REQUEST_PREFIX = "request:"

#: (text prefix, type) in check order — first match wins. The figure and
#: new-section asks carry variable text after the prefix shown here (a figure
#: label, a section title), so these are prefix matches, not exact ones.
_TYPE_RULES: tuple[tuple[str, str], ...] = (
    ("request: find supporting references for this passage", "find-refs"),
    ("request: remake this figure", "remake-figure"),
    ("request: a new section after §", "new-section"),
)

#: the anchor fields this reader surfaces, normalised across the rewrite-style
#: anchor (``file``) and the comment-style anchor (``source_file``) into one
#: ``file`` key. Only the fields a given row actually carries are included.
_ANCHOR_FIELDS = ("section", "block", "figure", "quote")

_EMPTY_COUNTS = {"find-refs": 0, "remake-figure": 0, "new-section": 0,
                  "other-request": 0, "total": 0, "revoked": 0}


def _classify(text: str) -> str:
    for prefix, kind in _TYPE_RULES:
        if text.startswith(prefix):
            return kind
    return "other-request"


def _rationale(text: str) -> str:
    """The part after the first ``" — "`` (em dash), or "" when none rides
    the comment."""
    sep = " — "
    if sep in text:
        return text.split(sep, 1)[1]
    return ""


def _anchor_of(row: dict) -> dict:
    a = row.get("anchor")
    if not isinstance(a, dict):
        return {}
    out = {k: a[k] for k in _ANCHOR_FIELDS if a.get(k) not in (None, "")}
    file_val = a.get("file") or a.get("source_file")
    if file_val:
        out["file"] = file_val
    return out


def _relpath(path: Path, repo_root: Path | None) -> str:
    if repo_root is not None:
        try:
            return path.resolve().relative_to(Path(repo_root).resolve()).as_posix()
        except (OSError, ValueError):
            pass
    return str(path)


def _empty(corpus: str, note: str) -> dict:
    return {"corpus": corpus, "ledger": None, "requests": [], "counts": {}, "note": note}


def _resolve_ledger(corpus: str, repo_root: Path | None,
                    ledger: str | Path | None) -> tuple[Path | None, str | None]:
    """``(path, error_words)`` — never raises. ``ledger`` (an explicit path,
    the projection-viewer-reuse idiom :func:`manuscript_bridge.feedback_add`
    already carries) bypasses the registry entirely; otherwise the corpus is
    resolved through the project registry, exactly as every other consumer of
    a corpus's feedback ledger does."""
    if ledger is not None:
        return Path(ledger), None
    from laplace.pipeline import registry
    ctx = registry.project_context(corpus, repo_root)
    if ctx is None:
        return None, f"{corpus!r} is not a registered corpus"
    if ctx.feedback_ledger is None:
        return None, f"{corpus!r} has no feedback ledger registered"
    return ctx.feedback_ledger, None


def collect(corpus: str, repo_root: Path | None = None, *,
            ledger: str | Path | None = None) -> dict[str, Any]:
    """Read ``corpus``'s feedback ledger and return every typed REQUEST row.

    ``{"corpus", "ledger": <repo-relative path or None>, "requests": [...],
    "counts": {...}}``; a ``"note"`` key explains an absent ledger in plain
    words instead of raising. Each request:
    ``{"id", "ts", "by", "type", "text", "rationale", "anchor", "scope",
    "revoked"}`` — ``type`` is one of ``find-refs`` / ``remake-figure`` /
    ``new-section`` / ``other-request``; ``text`` is the full banked comment;
    ``rationale`` is the part after the first ``" — "`` in that comment,
    or ``""``; ``anchor`` carries whichever of ``section`` / ``block`` /
    ``figure`` / ``file`` / ``quote`` the row's own anchor has; ``revoked`` is
    ``True`` when a later row's ``supersedes`` names this row's id.

    ``ledger`` overrides registry resolution with an explicit path (test
    seam / projection-viewer reuse); pass it alongside any ``corpus`` label
    when the caller already holds the ledger path directly."""
    path, note = _resolve_ledger(corpus, repo_root, ledger)
    if path is None:
        return _empty(corpus, note or "no feedback ledger could be resolved")
    if not path.is_file():
        return _empty(corpus, f"no feedback ledger file at {path}")

    rows = read_jsonl(path)
    dict_rows = [r for r in rows if isinstance(r, dict)]
    superseded_ids = {r.get("supersedes") for r in dict_rows if r.get("supersedes")}

    requests: list[dict[str, Any]] = []
    counts = dict(_EMPTY_COUNTS)
    for row in dict_rows:
        text = row.get("comment")
        if not isinstance(text, str) or not text.startswith(REQUEST_PREFIX):
            continue
        rid = row.get("id")
        rtype = _classify(text)
        revoked = rid in superseded_ids
        requests.append({
            "id": rid, "ts": row.get("ts"), "by": row.get("by"), "type": rtype,
            "text": text, "rationale": _rationale(text), "anchor": _anchor_of(row),
            "scope": row.get("scope") or "", "revoked": revoked,
        })
        counts[rtype] += 1
        counts["total"] += 1
        if revoked:
            counts["revoked"] += 1

    return {"corpus": corpus, "ledger": _relpath(path, repo_root),
            "requests": requests, "counts": counts}


def pending(corpus: str, repo_root: Path | None = None, *,
            ledger: str | Path | None = None) -> list[dict[str, Any]]:
    """``collect()``'s requests with ``revoked`` False — the live worklist the
    consuming organs actually act on."""
    return [r for r in collect(corpus, repo_root, ledger=ledger)["requests"]
            if not r["revoked"]]
