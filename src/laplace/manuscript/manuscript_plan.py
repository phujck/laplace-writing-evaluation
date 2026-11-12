"""The manuscript projection plan as read models consume it: the plan plus its node -> section index and the board's
display framing of the contribution rank. Moved out of the served shared_ui on 2026-10-21; pure reads.
"""
from __future__ import annotations

import json
from typing import Any

from laplace.pipeline import registry


# ---- moved from laplace.web.shared_ui (2026-10-21, core native/physical closure)
def board_contribution_rank(meta: dict) -> dict[str, list[str]] | None:
    """The board's DISPLAY-voice framing of ``meta.contribution_rank`` - a THIRD
    frame over the SAME ``schema.contribution_rank_lines`` split (dispatch.py's
    kernel wraps it as policy voice, narrative.py's packet as authored-content
    voice; this is the board's own compact-strip voice). Returns None when the
    plan carries no rank (or it parses to nothing), so callers can keep the
    meta key additive - present only when there is a real judgement to show.
    The one parse lives in schema.contribution_rank_lines; this never re-parses
    the rank shape itself, only reframes its two output lists as a named dict."""
    from laplace.pipeline import schema
    primary, excluded = schema.contribution_rank_lines(meta.get("contribution_rank"))
    if not primary and not excluded:
        return None
    return {"primary": primary, "excluded": excluded}


def plan_payload(corpus: str) -> dict[str, Any] | None:
    """The plan plus the derived node -> section index the cross-links need.
    Returns None when the corpus is unknown or has no plan on disk."""
    p = registry.plan_path_for(corpus)
    if p is None:
        return None
    try:
        plan = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    meta = plan.get("meta") or {}
    sections = list(plan.get("sections") or []) + list(plan.get("appendices") or [])
    node_index: dict[str, dict] = {}
    for sec in sections:
        sid, title = sec.get("id"), sec.get("title")
        if not sid:
            continue
        for key in ("nodes_in_order", "beats", "figures"):
            for nid in sec.get(key) or []:
                if isinstance(nid, str):
                    node_index.setdefault(nid, {"section": sid, "title": title})
    out_meta = {k: meta.get(k) for k in ("project", "artefact", "form", "target_dir")}
    # meta.contribution_rank (2026-07-13, the return-path push): the ONE authored
    # judgement the board must display where the author looks - additive (a
    # rank-less plan's meta stays byte-identical to before board_contribution_rank
    # existed).
    rank = board_contribution_rank(meta)
    if rank is not None:
        out_meta["contribution_rank"] = rank
    return {
        "corpus": corpus,
        "target_dir": meta.get("target_dir"),
        "meta": out_meta,
        "sections": [{"id": s.get("id"), "title": s.get("title"),
                      "nodes_in_order": s.get("nodes_in_order") or [],
                      "beats": s.get("beats") or [],
                      "figures": s.get("figures") or []} for s in sections],
        "node_index": node_index,
    }
