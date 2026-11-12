"""One pure graded-serve contract for every Atlas seat-pull surface.

Pull is the banked cursor act.  Grading is a projection over that returned envelope: it
never reads the store, advances a cursor, acknowledges, or mutates its input.  The CLI and
MCP tool both call this module so budget, displacement, previews and explicit descent cannot
drift into provider-specific dialects.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

GRADE_SCHEMA = "laplace.seat-fabric-graded-pull/1"
DEFAULT_PULL_BUDGET = 6
DEFAULT_PREVIEW_CHARS = 120


def expiry_from(expires_at: str) -> str:
    """Grade one timezone-bearing expiry without changing message state."""

    if not expires_at:
        return "no expiry"
    try:
        expiry = datetime.fromisoformat(expires_at)
        if expiry.tzinfo is None:
            return "unreadable expiry"
        left = (expiry - datetime.now(timezone.utc)).total_seconds()
    except (TypeError, ValueError):
        return "unreadable expiry"
    if left <= 0:
        return "EXPIRED-UNPULLED"
    if left < 6 * 3600:
        return f"RED expires in {left / 3600:.1f}h"
    return f"expires in {left / 3600:.0f}h"


def _preview(body: str, limit: int) -> tuple[str, bool]:
    flat = " ".join(str(body).split())
    if limit <= 0 or len(flat) <= limit:
        return flat, False
    return flat[: max(1, limit - 3)].rstrip() + "...", True


def _mcp_descend(message_id: str) -> str:
    return (
        "laplace_descend(kind='fabric-message', "
        f"reference={message_id!r})"
    )


def _grade_row(
    raw: dict[str, Any],
    *,
    preview_chars: int,
    with_body: bool,
    descend_for: Callable[[str], str],
) -> dict[str, Any]:
    row = {key: value for key, value in raw.items() if key != "body"}
    body = str(raw.get("body", ""))
    preview, truncated = _preview(body, preview_chars)
    expiry = expiry_from(str(raw.get("expires_at") or ""))
    if expiry == "EXPIRED-UNPULLED":
        expiry = "EXPIRED-AT-PULL"
    message_id = str(raw.get("message_id", ""))
    handle = str(raw.get("body_handle", ""))
    row.update(
        expiry_grade=expiry,
        body_chars=len(body),
        body_preview=preview,
        body_preview_truncated=truncated,
        descend=descend_for(message_id),
    )
    if with_body:
        row["body"] = body
    row["grade"] = (
        f"#{raw.get('cursor', '?')} {message_id}  {raw.get('sender_seat_id', '?')} -> "
        f"{raw.get('recipient_seat_id', '?')}  {raw.get('message_type', '?')}  [{expiry}]  "
        f"{len(body)}c  {handle[:18]}  :: {preview}"
    )
    return row


def grade_pull(
    envelope: dict[str, Any],
    *,
    budget: int = DEFAULT_PULL_BUDGET,
    preview_chars: int = DEFAULT_PREVIEW_CHARS,
    descend: tuple[str, ...] = (),
    full: bool = False,
    descend_for: Callable[[str], str] = _mcp_descend,
) -> dict[str, Any]:
    """Project one banked pull into bounded summaries with named displacement.

    Explicit descents outrank the budget and carry full bodies. ``full=True`` is the old
    unbounded body dump made explicit. A displaced message is already pulled, so every
    displaced id and the across-session body descent are carried in the result.
    """

    messages = list(envelope.get("messages") or [])
    descend_ids = {str(item) for item in descend}
    ordered = sorted(messages, key=lambda item: int(item.get("cursor", 0) or 0))
    requested = [item for item in ordered if str(item.get("message_id")) in descend_ids]
    rest = [item for item in ordered if str(item.get("message_id")) not in descend_ids]
    if budget is None or budget <= 0 or full:
        served_ids = {str(item.get("message_id")) for item in ordered}
    else:
        room = max(0, budget - len(requested))
        served_ids = {str(item.get("message_id")) for item in requested}
        served_ids |= {str(item.get("message_id")) for item in rest[:room]}

    served = [item for item in ordered if str(item.get("message_id")) in served_ids]
    displaced = [item for item in ordered if str(item.get("message_id")) not in served_ids]
    rows = [
        _grade_row(
            item,
            preview_chars=preview_chars,
            with_body=full or str(item.get("message_id")) in descend_ids,
            descend_for=descend_for,
        )
        for item in served
    ]
    displaced_ids = [str(item.get("message_id")) for item in displaced]
    graded = dict(envelope)
    graded.update(
        messages=rows,
        graded=True,
        grade_schema=GRADE_SCHEMA,
        pull_budget=budget,
        pulled_count=len(messages),
        served_count=len(rows),
        displaced_count=len(displaced_ids),
        displaced_message_ids=displaced_ids,
        grade_lines=[row["grade"] for row in rows],
        descend_hint=descend_for("<message_id>"),
    )
    graded["displacement"] = (
        ""
        if not displaced_ids
        else (
            f"DISPLACED {len(displaced_ids)} of {len(messages)} by the pull budget "
            f"({budget}). They ARE PULLED - this pull's banked cursor advance covered them, "
            "so they will not return on the next pull; descend by id: "
            + ", ".join(displaced_ids)
        )
    )
    return graded
