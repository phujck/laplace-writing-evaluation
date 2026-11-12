#!/usr/bin/env python3
"""Intake a HUMAN HOLD-OUT REVIEW into a project's feedback ledger as
kind-tagged, section-anchored, author-ruling-required findings.

The hold-out review is DIRECTIONALLY RIGHT, NOT canonical, and project-specific:
every item it carries is a CANDIDATE for the author's ruling, NEVER an
auto-applied edit. This script pours each item through the ONE hardened door
(:func:`laplace.pipeline.ledger.pour_finding`) so the finding surfaces on the
review surface for HIS adjudication (confirm / dismiss / defer / route) and is
never machine-actioned without his yes.

Design (the two mechanical constraints this respects):

  * ``intake_items`` (propagate) RAISES on any ``kind`` absent from
    ``schema.KIND_TO_WORK`` — pouring a raw taxonomy kind
    (``technical-consistency``, ``evidence-risk``, …) would plant a ValueError
    landmine that halts the running pipeline. And a routed kind like
    ``figure-standard`` auto-dispatches to a generation worker. Neither is
    candidate-only. So every finding is poured with ``kind="note"``
    (``KIND_TO_WORK["note"] is None`` → a comment, no work item, no auto-apply)
    and the review taxonomy rides a separate ``review_kind`` field. The finding
    is candidate-only BY CONSTRUCTION, not by discipline.
  * ``pour_finding`` requires a section anchor and is idempotent on a
    deterministic id, so a re-run of this script is a NO-OP (no double-pour).

The parser is GENERIC (any review md in the ``=== KIND ===`` / ``TOKEN ...``
shape); the ANCHOR MAP is the project-specific judgement (which N-section /
appendix owns each item, its escalation tier, and whether it is an author's-fork
that must never be auto-fixed). A document-spanning item is anchored to the
document grain (``ALL``) honestly rather than mis-anchored to a wrong precise
section.

Usage:
    python scripts/intake_holdout_review.py <review.md> <project> [--ledger PATH] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from laplace.pipeline.ledger import pour_finding, read_jsonl  # noqa: E402

# --------------------------------------------------------------------------
# the item token grammar (leading token identifies one review item)
# --------------------------------------------------------------------------
_HEADER_RE = re.compile(r"^===\s*(.+?)\s*===\s*$")
_ITEM_RE = re.compile(r"^(TC\d+|FIG-BLOCK|FIG\d+|CAPTIONS|ST\d+|CL\d+|AO\d+|PR\d+|ER\d+)\b")
_BRACKET_RE = re.compile(r"^\S+\s*\[([^\]]*)\]")

# --------------------------------------------------------------------------
# the ANCHOR MAP — the project-specific judgement (subset-sum-itqde SSG r2).
#   token -> (section_anchor, tier, author_fork)
# sections: §II=N2, §III=N3, §IV=N4, §V=N5, §VI=N6, §VII=N7, Concl=N8,
#           AppA=NA1, AppB=NA2, AppC=NA3; ALL = document grain.
# tiers:  top-escalation (physics fork) | high (release-blocker) |
#         medium | low | question (his ruling, not a fix).
# --------------------------------------------------------------------------
ANCHOR_MAP: dict[str, tuple[str, str, bool]] = {
    # technical-consistency — TOP escalation, author's-fork physics
    "TC1": ("N3", "top-escalation", True),   # t_k / Eq(11) / Fourier discretisation (spans N3/N4/Fig2)
    "TC2": ("N3", "top-escalation", True),   # "changes what the device must record" + (-2it_k)^m — N3 line 93
    # figure-standard — FIG-BLOCK is the release-blocker (high); rest feed re-authoring
    "FIG-BLOCK": ("ALL", "high", False),     # Fig5/6/7 + float backlog (whole doc) + AppB/AppC tables
    "FIG1": ("N1", "medium", False),         # fig:nf1 SSG pipeline schematic
    "FIG2": ("N4", "medium", False),         # fig:nf2 acquisition aperture / envelope
    "FIG3": ("N5", "medium", False),         # fig:f5-dp-price Bellman DP (never referenced)
    "FIG4": ("N5", "medium", False),         # fig:nf3 factorisation
    "FIG5": ("N5", "medium", False),         # fig:nf4 perturbative fingerprint / J-scaling
    "FIG6": ("N6", "medium", False),         # fig:nf5 decoder coverage
    "FIG7": ("N6", "medium", False),         # fig:nf6 operating-window vs J / ED-TEBD
    "FIG8": ("N7", "medium", False),         # fig:nf7 staircase spread / chi trend
    "FIG9": ("NA2", "medium", False),        # fig:N12-identities implementation verification (appendix)
    "CAPTIONS": ("ALL", "medium", False),    # caption style across all figures
    # structure
    "ST1": ("N2", "medium", False),          # §II & §III repeat maths — narrow §II
    "ST2": ("ALL", "medium", False),         # main-paper restructuring (whole doc)
    # claim-sharpening
    "CL1": ("N1", "medium", False),          # resolution-dial intro language (tau_max objection)
    "CL2": ("N1", "medium", False),          # coefficient-insertion scope in initial contract
    # artefact-omission
    "AO1": ("ALL", "medium", False),         # no abstract (front matter)
    "AO2": ("N4", "medium", False),          # resource table near end of §IV
    "AO3": ("NA2", "medium", False),         # AppB (NA2) + AppC (NA3) tables render as prose
    # prose
    "PR1": ("ALL", "low", False),            # anxious/defensive disclaimers throughout
    "PR2": ("ALL", "low", False),            # sentence density throughout
    # evidence-risk — QUESTIONS for his ruling, author's-fork (not defects to fix)
    "ER1": ("N6", "question", True),
    "ER2": ("N6", "question", True),
    "ER3": ("N6", "question", True),
    "ER4": ("N6", "question", True),
    "ER5": ("N6", "question", True),
    "ER6": ("NA2", "question", True),        # worst-case behind Fig9 (appendix)
    "ER7": ("NA2", "question", True),        # reproduce from clean checkout (data-availability appendix)
}

_TIER_SEVERITY = {
    "top-escalation": "critical",
    "high": "high",
    "medium": "medium",
    "low": "low",
    "question": "question",
}

# items ALREADY HANDLED elsewhere — NOT re-opened. Noted resolved for the record
# (not poured: a resolved pour re-appends on re-run, breaking idempotence — these
# carry no live work, so the honest move is to record the closure, not the fault).
ALREADY_RESOLVED = [
    {"item": "r2-declares-r1 PDF metadata", "review_kind": "technical-consistency",
     "resolved_by": "C1 fixed finalize PDF-metadata stamping"},
    {"item": "Type-3 fonts", "review_kind": "figure-standard",
     "resolved_by": "C1 fixed figstyle (Type-3 fonts eliminated)"},
    {"item": "mis-named slug", "review_kind": "artefact-omission",
     "resolved_by": "A6 judge active on the slug"},
]


def review_kind_from_header(header: str) -> str:
    """The taxonomy slug from a ``=== KIND (...) ===`` header — the text before
    the first parenthesis, lowercased (``TECHNICAL-CONSISTENCY`` →
    ``technical-consistency``)."""
    return header.split("(")[0].strip().lower()


def parse_items(md_text: str) -> list[dict]:
    """Parse the review md into one dict per item: ``token``, ``review_kind``,
    ``where`` (the leading bracket, if any), ``body`` (verbatim item text)."""
    items: list[dict] = []
    cur_kind = ""
    for raw in md_text.splitlines():
        line = raw.rstrip()
        hm = _HEADER_RE.match(line)
        if hm:
            cur_kind = review_kind_from_header(hm.group(1))
            continue
        im = _ITEM_RE.match(line)
        if not im:
            continue
        token = im.group(1)
        bm = _BRACKET_RE.match(line)
        where = bm.group(1).strip() if bm else token
        items.append({"token": token, "review_kind": cur_kind,
                      "where": where, "body": line.strip()})
    return items


def build_finding(item: dict, project: str) -> tuple[dict, str]:
    """Turn a parsed item into a finding dict + its section anchor, per the
    ANCHOR MAP. Every finding is candidate-only (``kind='note'`` → no work
    item), author-ruling-required, and carries its review taxonomy + tier."""
    token = item["token"]
    if token not in ANCHOR_MAP:
        raise KeyError(f"no anchor for review item {token!r} — extend ANCHOR_MAP")
    section, tier, author_fork = ANCHOR_MAP[token]
    severity = _TIER_SEVERITY[tier]
    grain = "document" if section == "ALL" else "section"
    finding = {
        "id": f"holdout-r2-{token}",
        "reader": "holdout-r2",
        "kind": "note",                       # KIND_TO_WORK['note'] is None: candidate-only
        "review_kind": item["review_kind"],   # the taxonomy tag (grouping)
        "where": f"{token}: {item['where']}",
        "issue": item["body"],                # verbatim item text (reader-view body)
        "comment": item["body"],              # verbatim item text (feedback-view body)
        "tier": tier,
        "severity": severity,
        "ruling_required": True,              # EVERY finding is his to rule on
        "author_fork": author_fork,           # physics / evidence: never auto-fixable
        "advisory": True,                     # directionally right, NOT canonical
        "by": "holdout-review-r2",
        "provenance": ("human hold-out review of SSG r2 (2026-07-10) — "
                       "directionally right, NOT canonical, SSG-specific; "
                       "CANDIDATE for the author's ruling, never auto-applied"),
        "anchor": {"section": section, "grain": grain},
    }
    return finding, section


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("review_md")
    ap.add_argument("project")
    ap.add_argument("--ledger", default="",
                    help="explicit feedback.jsonl (default: the project convention path)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    md_path = Path(args.review_md)
    md_text = md_path.read_text(encoding="utf-8")

    if args.ledger:
        ledger = Path(args.ledger)
    else:
        ledger = (_REPO_ROOT / "synthetics papers" / args.project
                  / "manuscript" / "whitepaper" / "feedback" / "feedback.jsonl")

    items = parse_items(md_text)
    poured: list[dict] = []
    before_ids = {r.get("id") for r in read_jsonl(ledger)}
    for item in items:
        finding, section = build_finding(item, args.project)
        if args.dry_run:
            poured.append({"id": finding["id"], "kind": finding["review_kind"],
                           "anchor": section, "tier": finding["tier"],
                           "author_fork": finding["author_fork"], "dry_run": True})
            continue
        rec = pour_finding(ledger, finding, section=section, project=args.project,
                           source="holdout-review-r2")
        poured.append({"id": rec["id"], "kind": finding["review_kind"],
                       "anchor": rec["section"], "tier": finding["tier"],
                       "author_fork": finding["author_fork"],
                       "new": finding["id"] not in before_ids})

    by_kind: dict[str, int] = {}
    for p in poured:
        by_kind[p["kind"]] = by_kind.get(p["kind"], 0) + 1

    print(json.dumps({
        "ledger": str(ledger),
        "poured_count": len(poured),
        "count_by_kind": by_kind,
        "poured": poured,
        "already_resolved_noted": ALREADY_RESOLVED,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
