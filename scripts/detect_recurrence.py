#!/usr/bin/env python3
"""detect_recurrence.py — mechanise "the correction that recurs was never mechanised."

Gerard has banked this lesson twice in EIGEN_DIARY.md (2026-07-11 figstyle
no-titles correction; the disclosure-editorial pass) and each time the fix was
to *notice by hand* that the same friction had fired more than once before it
got welded into the code. This script is the mechanical noticer: it reads the
open friction/fork records out of every ``corpus_friction/*.jsonl`` ledger,
clusters them by owning layer/node plus token overlap, and flags any cluster
with two or more open witnesses and no linked resolution as a RECURRENCE — a
correction that fired more than once without ever being mechanised.

It never calls an LLM and it never writes ``OPEN_STACK.md``: each flagged
cluster carries a drafted one-line OPEN_STACK row (draft text only) for the
close ritual — or the author — to ratify and paste in by hand, same
draft-only discipline as ``drain_frictions.py``.

    scripts/detect_recurrence.py [--ledger PATH ...] [--out FILE] [--min-witnesses N] [--check]

``--ledger`` may be repeated; default is every ``corpus_friction/*.jsonl`` in
the repo. ``--check`` suppresses the JSON body and only sets the exit code:
1 if any recurrence cluster was found (so the close ritual can gate on it),
0 if clean. Without ``--check`` the JSON report always prints to stdout, and
also lands at ``--out`` if given.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
FRICTION_DIR = REPO_ROOT / "corpus_friction"

# a record counts as an open friction/fork witness when it has this shape —
# the friction-channel schema (drain_frictions.py / friction_consumer.py),
# not the unrelated conceptric graph-op records (add-node, add-edge, ...)
# that share these same *.jsonl directories.
FRICTION_KINDS = {"friction", "fork"}
OPEN_STATUS = "open"

# a resolution record supersedes a friction by id — see RES-* records in
# corpus_friction/laplace_engine.jsonl: {"record": "resolution",
# "target": "<friction id>", "supersedes": "<friction id>", ...}
RESOLUTION_RECORD_KIND = "resolution"

# tokens too common across the corpus to mean anything for clustering —
# the IDF floor is applied on top of this stopword floor.
STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "it",
    "this", "that", "with", "as", "by", "at", "be", "was", "were", "are",
    "not", "no", "but", "so", "if", "than", "then", "into", "out", "up",
    "its", "it's", "one", "does", "do", "did", "has", "have", "had", "will",
    "would", "could", "should", "there", "their", "which", "when", "where",
    "over", "under", "per", "via", "each", "any", "all", "some", "own",
}
TOKEN_RE = re.compile(r"[a-z0-9_./]+")

# a token must appear in at most this fraction of ALL open witnesses to
# count toward a cluster signature — the mechanical IDF floor (no LLM
# judgement call). Kept tight (not the textbook 0.5) because this corpus
# mixes narrow code-identifier vocabularies with prose-heavy fork/review
# batches; a loose ceiling lets one author's boilerplate phrasing across a
# same-sitting batch of otherwise-unrelated review items pass as a
# "recurrence" signature.
MAX_DOC_FREQ_FRACTION = 0.08
GLOBAL_DOC_FREQ_FLOOR = 3
MIN_TOKEN_LEN = 3

DEFAULT_MIN_WITNESSES = 2


def _default_ledgers() -> list[Path]:
    if not FRICTION_DIR.is_dir():
        return []
    return sorted(FRICTION_DIR.glob("*.jsonl"))


def _read_records(ledger: Path) -> Iterable[dict[str, Any]]:
    with ledger.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict):
                rec["_ledger"] = str(ledger)
                rec["_lineno"] = lineno
                yield rec


def load_ledger_records(ledgers: list[Path]) -> list[dict[str, Any]]:
    """Read every record — friction/fork witnesses and resolution records alike
    — out of the given ledgers. Ordering across files is not meaningful; each
    record carries its own ``_ledger``/``_lineno`` provenance."""
    records: list[dict[str, Any]] = []
    for ledger in ledgers:
        if ledger.is_file():
            records.extend(_read_records(ledger))
    return records


def open_witnesses(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The friction/fork records that are open — the population clustered for
    recurrence. Records shaped like the conceptric graph ops (add-node,
    add-edge, set-spine, ...) that share the corpus_friction/ directory are
    not friction-shaped and are excluded."""
    return [r for r in records
            if r.get("kind") in FRICTION_KINDS and r.get("status") == OPEN_STATUS]


def resolved_ids(records: list[dict[str, Any]]) -> set[str]:
    """Every friction id that a resolution record names as ``target`` or
    ``supersedes`` — a linked resolution, regardless of which ledger the
    resolution record itself landed in."""
    resolved: set[str] = set()
    for r in records:
        if r.get("record") == RESOLUTION_RECORD_KIND:
            for key in ("target", "supersedes"):
                val = r.get(key)
                if val:
                    resolved.add(val)
    return resolved


def tokenize(text: str) -> set[str]:
    if not text:
        return set()
    tokens = TOKEN_RE.findall(text.lower())
    return {t for t in tokens if len(t) >= MIN_TOKEN_LEN and t not in STOPWORDS}


def witness_signature_text(rec: dict[str, Any]) -> str:
    """The text a witness contributes to clustering: node/owning_layer (the
    mechanical grouping key) plus value/proposal/where (the free-text
    keyword-overlap signal). A field that grew structure (a dict/list value —
    ledger rows evolved these after this detector was written) contributes its
    JSON text rather than crashing the sweep."""
    parts = [rec.get("node", ""), rec.get("owning_layer", ""),
              rec.get("value", ""), rec.get("proposal", ""), rec.get("where", "")]
    text_parts = []
    for p in parts:
        if not p:
            continue
        text_parts.append(p if isinstance(p, str) else json.dumps(p, ensure_ascii=False))
    return " ".join(text_parts)


def cluster_key(rec: dict[str, Any]) -> str:
    """The mechanical grouping key: same owning_layer if present, else same
    node. This is the coarse bucket; keyword overlap (the IDF floor) narrows
    a bucket into recurrence signatures below."""
    layer = (rec.get("owning_layer") or "").strip()
    node = (rec.get("node") or "").strip()
    return layer or node or "(unowned)"


def _global_doc_freq(witnesses: list[dict[str, Any]]) -> tuple[Counter[str], int]:
    """Document frequency of each token across *all* open witnesses (not just
    one cluster) — the population the IDF floor is measured against, so a
    token generic to the whole ledger (e.g. "protocol") can't manufacture a
    signature just because it recurs inside one bucket too."""
    doc_freq: Counter[str] = Counter()
    for w in witnesses:
        doc_freq.update(tokenize(witness_signature_text(w)))
    return doc_freq, len(witnesses)


def build_clusters(witnesses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group open witnesses by cluster_key (the coarse owning_layer/node
    bucket), then narrow each bucket down to the sub-cluster that actually
    shares keyword signal — two passes so a same-owning_layer bucket of
    otherwise-unrelated items can't get reported as one recurrence just for
    sharing a tag:

    1. candidate tokens: appear in >=2 members of the raw bucket, and clear
       the IDF floor (global document frequency <= MAX_DOC_FREQ_FRACTION of
       all open witnesses — ledger-wide filler can't qualify either).
    2. the real cluster is only the members that actually contain a
       candidate token; the signature is then recomputed over *that*
       narrowed membership (count >= 2), so every reported witness_id
       genuinely shares the reported signature and no straggler that merely
       shared the coarse tag rides along.

    A bucket with no qualifying signature, or whose narrowed membership
    drops below 2, is dropped — no signature, no claimed recurrence."""
    global_doc_freq, total_witnesses = _global_doc_freq(witnesses)
    # a floor under the ceiling: on a small ledger, MAX_DOC_FREQ_FRACTION of
    # the population can round below 2, which would make the "local count
    # >=2" candidate test and the IDF ceiling mutually impossible to satisfy
    # at once. GLOBAL_DOC_FREQ_FLOOR keeps the ceiling meaningful regardless
    # of corpus size.
    doc_freq_ceiling = max(GLOBAL_DOC_FREQ_FLOOR,
                          int(total_witnesses * MAX_DOC_FREQ_FRACTION))

    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for w in witnesses:
        buckets[cluster_key(w)].append(w)

    clusters: list[dict[str, Any]] = []
    for key, members in buckets.items():
        if len(members) < 2:
            continue
        member_tokens = {id(m): tokenize(witness_signature_text(m)) for m in members}

        raw_freq: Counter[str] = Counter()
        for toks in member_tokens.values():
            raw_freq.update(toks)
        candidates = {t for t, c in raw_freq.items()
                     if c >= 2 and global_doc_freq.get(t, 0) <= doc_freq_ceiling}
        if not candidates:
            continue

        narrowed = [m for m in members if member_tokens[id(m)] & candidates]
        if len(narrowed) < 2:
            continue

        narrowed_freq: Counter[str] = Counter()
        for m in narrowed:
            narrowed_freq.update(member_tokens[id(m)] & candidates)
        signature = sorted(t for t, c in narrowed_freq.items() if c >= 2)
        if not signature:
            continue

        clusters.append({"key": key, "members": narrowed, "signature": signature})
    return clusters


def flag_recurrences(clusters: list[dict[str, Any]], resolved: set[str],
                      min_witnesses: int) -> list[dict[str, Any]]:
    """A cluster is a RECURRENCE when it has >= min_witnesses open witnesses
    and none of them has a linked resolution. (If any member is resolved,
    the correction *was* mechanised via that resolution's evidence trail —
    not a silent recurrence.)"""
    flagged = []
    for c in clusters:
        members = c["members"]
        if len(members) < min_witnesses:
            continue
        if any(m.get("id") in resolved for m in members):
            continue
        flagged.append(c)
    return flagged


def _draft_open_stack_row(cluster: dict[str, Any]) -> str:
    members = cluster["members"]
    ids = [m.get("id", "?") for m in members]
    sig = ", ".join(cluster["signature"][:6])
    key = cluster["key"]
    return (f"- [ ] MECHANISE: {len(members)}x recurrence at `{key}` "
            f"({sig}) — witnesses {', '.join(ids)}; never mechanised, "
            f"correction recurred (see EIGEN_DIARY.md: \"the correction that "
            f"recurs is a correction that was never mechanised\")")


def _cluster_dates(cluster: dict[str, Any]) -> list[str]:
    return sorted({m.get("ts", "") for m in cluster["members"] if m.get("ts")})


def build_report(ledgers: list[Path], min_witnesses: int) -> dict[str, Any]:
    records = load_ledger_records(ledgers)
    witnesses = open_witnesses(records)
    resolved = resolved_ids(records)
    clusters = build_clusters(witnesses)
    recurrences = flag_recurrences(clusters, resolved, min_witnesses)
    # rank: most witnesses first, ties broken by most recent witness
    recurrences.sort(key=lambda c: (len(c["members"]), max(_cluster_dates(c) or [""])),
                     reverse=True)

    cluster_reports = []
    for c in recurrences:
        members = c["members"]
        cluster_reports.append({
            "owning_key": c["key"],
            "witness_ids": [m.get("id") for m in members],
            "dates": _cluster_dates(c),
            "signature": c["signature"],
            "witness_count": len(members),
            "open_stack_row": _draft_open_stack_row(c),
        })

    return {
        "ledgers": [str(p) for p in ledgers],
        "open_witness_count": len(witnesses),
        "resolved_id_count": len(resolved),
        "min_witnesses": min_witnesses,
        "recurrence_count": len(cluster_reports),
        "recurrences": cluster_reports,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="detect_recurrence.py",
        description="Mechanical recurrence detector over the open friction/fork "
                    "records of corpus_friction/*.jsonl — mechanises "
                    "\"the correction that recurs is a correction that was "
                    "never mechanised.\"")
    ap.add_argument("--ledger", action="append", default=[],
                    help="a friction ledger to scan (repeatable); default: "
                         "every corpus_friction/*.jsonl")
    ap.add_argument("--out", default="",
                    help="also write the JSON report to this path")
    ap.add_argument("--min-witnesses", type=int, default=DEFAULT_MIN_WITNESSES,
                    help=f"minimum open witnesses to flag a cluster "
                         f"(default: {DEFAULT_MIN_WITNESSES})")
    ap.add_argument("--check", action="store_true",
                    help="suppress the JSON body; exit 1 if any recurrence "
                         "found, 0 if clean (for the close ritual's gate)")
    try:
        args = ap.parse_args(argv)
    except SystemExit:
        return 2

    ledgers = [Path(p) for p in args.ledger] if args.ledger else _default_ledgers()
    if not ledgers:
        print("usage error: no ledgers found (pass --ledger or populate "
              "corpus_friction/)", file=sys.stderr)
        return 2

    report = build_report(ledgers, args.min_witnesses)

    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                  encoding="utf-8")

    if not args.check:
        print(json.dumps(report, indent=2, ensure_ascii=False))

    return 1 if report["recurrence_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
