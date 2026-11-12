#!/usr/bin/env python3
"""N38 — the audit-effect meter: does the wire/jury audit measurably reduce false
geometric associations? Mechanical only — no LLM calls, no model spend.

The blind Sonnet verdict (2026-06-11, banked in OPEN_STACK.md's N38 row) named this the
"undeniable" publishable result: a self-audit loop measurably reducing false geometric
associations, attributable to the wire/jury mechanism. This script computes what the
BANKED DATA actually supports, and — per the same row's own honesty bar — names what it
does NOT, rather than approximating past the ledger's real shape.

Ledgers read (repo root, gitignored, both append-only jsonl):
  .wire_proposals.jsonl  (embed_router.PROPOSALS_FILE) — the CURRENT unjudged frontier:
                          {query, id, cos, heat, via}. Appended on every ``route()`` fire
                          for a geometric-only find (embed_router.py ~L383); never checked
                          against past verdicts before appending.
  .wire_verdicts.jsonl   (embed_router.VERDICTS_FILE) — every judgment ever banked:
                          {query, id, verdict, method, cos, why}. verdict in
                          {wire, grit, noise}; method in {mechanical, jury}. Written only by
                          embed_router.bank_verdicts, in "a" (append) mode — never rewritten,
                          so line order IS temporal order, oldest first.

Load-bearing fact, checked against the live schema in embed_router.py, not assumed:
BOTH files now carry a `ts` field (UTC ISO-8601, seconds) on every freshly-banked record —
route()'s proposal append and bank_verdicts' verdict append each stamp one (embed_router.py
~L470, ~L617; proposal_pairs carries the EARLIEST ts per (query,id) pair through the dedupe,
~L533). Records banked before that fix landed carry no `ts` at all (dict.get access only,
never a strict schema) — so any given ledger is, in general, a ts-less PREFIX followed by a
ts-covered SUFFIX, and this script reports both honestly rather than assuming full coverage.
"LATEST verdict per (query,id) wins" is still the engine's own convention for current state
(see rebuild_learned_keywords's docstring) — duplicate entries for the same pair are
re-judgments, and the ledger's append order remains the fallback chronology for the ts-less
prefix.

What this meter computes, and what it explicitly refuses to approximate:

  (a) SUPPORTED — pre-audit false-association rate: noise / (wire+grit+noise) among distinct
      judged pairs (latest verdict wins). This is the raw geometry's error rate as measured
      by the audit itself — every "noise" verdict is a case the bare embedding cosine got
      wrong that a human/jury or the calibrated mechanical gate caught.

  (b) PARTIALLY SUPPORTED — the ask's literal post-audit measure ("of WIRE-approved
      associations, how many were later re-proposed/contradicted") is answered via two
      ledger-native signals, both recoverable without any new instrumentation:
        - reversed: a pair's FIRST banked verdict was 'wire', a LATER banked verdict for the
          SAME (query, id) differs — a recorded contradiction.
        - recurred: a pair with ANY banked verdict that is ALSO sitting in the CURRENT
          proposals frontier — cosine re-surfaced it after judgment. For 'wire' pairs this
          should not happen (a wire teaches embed_router.bank_verdicts' learned-keywords
          index, so a later fire should see the pair as lexically explained, not
          geometric-only, and never re-propose it); for 'noise' pairs it CAN, because
          rejection is never taught back into the geometry — there is no negative-teaching
          path today. Both are counted and reported separately, not conflated.
      NOT SUPPORTED: the ask's exact literal design (re-fire the SAME exploratory queries,
      count re-banked false associations strictly pre vs post a controlled point) needs a
      paired before/after run this ledger does not timestamp or session-tag. It cannot be
      disentangled from the reversal/recurrence proxy above without that instrumentation.

  (c) SUPPORTED as calendar time, for the ts-covered SUFFIX only — bank_verdicts and route()
      now write a `ts` field (verified against embed_router.py's actual write calls, not
      inferred). When a sufficient fraction of a ledger's verdict rows carry `ts`
      (>= CALENDAR_MIN_FRACTION, currently 0.5), this script bins those rows by calendar day
      (`ts[:10]`) and reports them under per_period.calendar_bins, with
      per_period.supported_as_calendar_time = True and the exact coverage fraction named. The
      ts-LESS prefix (records banked before the fix, or a ledger too thin on ts to trust) has
      no calendar signal recoverable from it; those rows still fall back to ledger
      APPEND-ORDER bins (chronological by line position, explicitly NOT calendar time) under
      per_period.order_bins, and supported_as_calendar_time is honestly False when the ts
      coverage never crosses the threshold (e.g. an all-legacy ledger).

  (d) NOT SUPPORTED via jury_bench.py — that module's gold set (archive/self_record/_weld)
      scores a DIFFERENT judgment task (trait accept/refuse adjudication on soul-record
      atoms), not wire/grit/noise geometric-proposal judging; no independent gold labels
      exist for THIS task beyond the banked verdicts themselves. What IS computed instead:
      agreement between 'mechanical' and 'jury' verdicts on any (query, id) pair banked under
      BOTH methods (a re-grade) — the only gold-free, same-domain precision proxy this
      ledger supports.

Usage:
  python scripts/audit_effect_meter.py                    # JSON report to stdout
  python scripts/audit_effect_meter.py --table             # + a compact human table
  python scripts/audit_effect_meter.py --out report.json   # also write JSON to a file
  python scripts/audit_effect_meter.py --root PATH         # repo root (default: this repo)
  python scripts/audit_effect_meter.py --periods 4         # number of order-bins (default 4)
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from laplace.representation import embed_router as er  # noqa: E402

VERDICT_LABELS = ("wire", "grit", "noise")
# a ledger must have at least this fraction of its verdict rows carrying `ts` before the
# calendar-day bins are reported as SUPPORTED — below this the ts-covered suffix is real but
# too thin to trust as the ledger's calendar-time story (module docstring, fact (c)).
CALENDAR_MIN_FRACTION = 0.5


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out


def load_verdict_history(repo_root: Path) -> list[dict]:
    """Full raw history in ledger (append) order — the only recoverable chronology; no `ts`
    field exists on these records (see module docstring, fact (c))."""
    rows = _read_jsonl(Path(repo_root) / er.VERDICTS_FILE)
    for i, r in enumerate(rows):
        r["_seq"] = i
    return rows


def latest_per_pair(history: list[dict]) -> dict[tuple[str, str], dict]:
    """LATEST verdict per (query, id) wins — mirrors embed_router.rebuild_learned_keywords's
    own convention, so 'current state' here matches what the engine itself treats as true."""
    out: dict[tuple[str, str], dict] = {}
    for r in history:
        key = (r.get("query", ""), r.get("id", ""))
        if not key[1]:
            continue
        out[key] = r
    return out


def ever_wire_pairs(history: list[dict]) -> set[tuple[str, str]]:
    """Distinct pairs that were verdicted 'wire' at ANY point in the history — the honest
    denominator for a reversal rate (a pair reversed away from wire no longer shows as wire
    in the latest-per-pair view, so that view alone would undercount the denominator)."""
    return {(r.get("query", ""), r.get("id", ""))
            for r in history if r.get("verdict") == "wire" and r.get("id")}


def reversed_wires(history: list[dict]) -> list[dict]:
    """Pairs whose FIRST banked verdict was 'wire' and a LATER banked verdict for the same
    pair differs — a recorded contradiction, recoverable purely from ledger order."""
    first: dict[tuple[str, str], str] = {}
    out = []
    for r in history:
        key = (r.get("query", ""), r.get("id", ""))
        if not key[1]:
            continue
        v = r.get("verdict")
        if v not in VERDICT_LABELS:
            continue
        if key not in first:
            first[key] = v
            continue
        if first[key] == "wire" and v != "wire":
            out.append({"query": key[0], "id": key[1], "first_verdict": "wire",
                        "later_verdict": v, "later_why": r.get("why")})
        first[key] = v  # count the first flip only; further churn on the same pair isn't re-added
    return out


def recurred_after_verdict(repo_root: Path,
                           latest: dict[tuple[str, str], dict]) -> dict[str, list[dict]]:
    """Pairs with a banked verdict that ALSO sit in the CURRENT proposals frontier — cosine
    re-surfaced something already judged. See module docstring (b) for the asymmetry between
    'wire' (should self-heal via learned_keywords) and 'noise' (has no negative-teaching path)."""
    pairs = er.proposal_pairs(repo_root)
    frontier_keys = {(p["query"], p["id"]) for p in pairs}
    recurred: dict[str, list[dict]] = {"wire": [], "grit": [], "noise": []}
    for key, r in latest.items():
        if key in frontier_keys:
            v = r.get("verdict")
            if v in recurred:
                recurred[v].append({"query": key[0], "id": key[1]})
    return recurred


def ts_less_prefix(history: list[dict]) -> list[dict]:
    """Rows carrying no `ts` at all — the ledger's untimestamped legacy prefix (records banked
    before embed_router's write paths stamped one). order_bins runs on exactly this subset;
    the ts-covered rows get the real calendar_bins instead (module docstring, fact (c))."""
    return [r for r in history if not r.get("ts")]


def calendar_ts_coverage(history: list[dict]) -> float:
    """Fraction of the raw verdict history that carries a `ts` — the honesty gate for whether
    the calendar-day bins below are reported as SUPPORTED (>= CALENDAR_MIN_FRACTION) or not."""
    if not history:
        return 0.0
    return sum(1 for r in history if r.get("ts")) / len(history)


def order_bins(history: list[dict], n_bins: int) -> list[dict]:
    """Bin (a subset of) the verdict ledger by APPEND ORDER (not calendar time). The fallback
    for whatever slice has no `ts` to bin by calendar day instead — normally the ts-less
    prefix (see ts_less_prefix), passed in by build_report."""
    if not history:
        return []
    n_bins = max(1, min(n_bins, len(history)))
    size = -(-len(history) // n_bins)  # ceil division
    bins = []
    for i in range(0, len(history), size):
        chunk = history[i:i + size]
        c = Counter(r.get("verdict") for r in chunk)
        total = sum(c.get(v, 0) for v in VERDICT_LABELS)
        bins.append({
            "bin": len(bins),
            "n": len(chunk),
            "seq_range": [chunk[0]["_seq"], chunk[-1]["_seq"]],
            "wire": c.get("wire", 0), "grit": c.get("grit", 0), "noise": c.get("noise", 0),
            "noise_rate": round(c.get("noise", 0) / total, 4) if total else None,
        })
    return bins


def calendar_bins(history: list[dict]) -> list[dict]:
    """Bin the ts-covered rows by calendar DAY (`ts[:10]`, ISO date) — the real calendar-time
    view, available for whatever suffix of the ledger was banked after the `ts` write-path
    landed (module docstring, fact (c)). Rows with no `ts` are excluded, not zero-filled."""
    by_day: dict[str, list[dict]] = defaultdict(list)
    for r in history:
        ts = r.get("ts")
        if ts:
            by_day[str(ts)[:10]].append(r)
    bins = []
    for day in sorted(by_day):
        chunk = by_day[day]
        c = Counter(r.get("verdict") for r in chunk)
        total = sum(c.get(v, 0) for v in VERDICT_LABELS)
        bins.append({
            "day": day,
            "n": len(chunk),
            "wire": c.get("wire", 0), "grit": c.get("grit", 0), "noise": c.get("noise", 0),
            "noise_rate": round(c.get("noise", 0) / total, 4) if total else None,
        })
    return bins


def method_agreement(history: list[dict]) -> dict:
    """Jury-precision PROXY: pairs banked under BOTH 'mechanical' and 'jury' methods (a
    re-grade) — agreement between the two is the only gold-free, same-domain check this
    ledger supports (see module docstring (d) for why jury_bench.py's fixtures don't apply)."""
    by_pair: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)
    for r in history:
        key = (r.get("query", ""), r.get("id", ""))
        m, v = r.get("method"), r.get("verdict")
        if key[1] and m and v in VERDICT_LABELS:
            by_pair[key][m] = v
    both = {k: v for k, v in by_pair.items() if "mechanical" in v and "jury" in v}
    agree = sum(1 for v in both.values() if v["mechanical"] == v["jury"])
    return {
        "n_pairs_regraded_both_methods": len(both),
        "agree": agree,
        "agreement_rate": round(agree / len(both), 4) if both else None,
        "note": (None if both else
                 "no pair in this ledger has been judged under BOTH methods yet — N=0, "
                 "not a computed rate of 0"),
    }


def _per_period(history: list[dict], n_bins: int) -> dict:
    """The per-period section: an honest SPLIT, not a single verdict on the whole ledger. The
    ts-covered suffix gets real calendar-day bins; the ts-less prefix (if any) falls back to
    append-order bins; supported_as_calendar_time reports whether the ts-covered portion is
    thick enough (>= CALENDAR_MIN_FRACTION of all rows) to trust as the ledger's calendar-time
    story, not just present at all (module docstring, fact (c))."""
    coverage = calendar_ts_coverage(history)
    supported = coverage >= CALENDAR_MIN_FRACTION
    cal_bins = calendar_bins(history)
    prefix = ts_less_prefix(history)
    if supported:
        reason = (
            f"{coverage:.0%} of banked verdict rows carry `ts` (>= "
            f"{CALENDAR_MIN_FRACTION:.0%} threshold) — the ts-covered suffix is binned by "
            "calendar day below (calendar_bins); any remaining ts-less prefix still falls "
            "back to append-order bins (order_bins).")
        what_would_be_needed = (
            "nothing further for the ts-covered portion — embed_router's route() and "
            "bank_verdicts write paths already stamp `ts` on every freshly-banked record "
            "(and proposal_pairs carries the earliest ts through the dedupe); coverage only "
            "grows as more verdicts are banked going forward.")
    else:
        reason = (
            f"only {coverage:.0%} of banked verdict rows carry `ts` (< "
            f"{CALENDAR_MIN_FRACTION:.0%} threshold) — embed_router.py's route() and "
            "bank_verdicts write paths DO stamp `ts` on every freshly-banked record, but this "
            "ledger is still mostly (or entirely) the untimestamped legacy prefix banked "
            "before that fix landed, so a calendar month/day breakdown is not yet trustworthy "
            "here.")
        what_would_be_needed = (
            "more verdicts banked after the `ts` write-path landed — the field already "
            "exists (see embed_router.py's route() ~L470 and bank_verdicts ~L617); this "
            "ledger just hasn't accumulated enough ts-covered rows yet.")
    return {
        "supported_as_calendar_time": supported,
        "calendar_ts_coverage_fraction": round(coverage, 4),
        "reason": reason,
        "proxy": ("ledger APPEND-ORDER bins (chronological by line order, NOT calendar time) "
                 "— the fallback for whatever slice of the ledger has no `ts` to bin by "
                 "calendar day instead."),
        "calendar_bins": cal_bins,
        "order_bins": order_bins(prefix, n_bins),
        "what_would_be_needed": what_would_be_needed,
    }


def build_report(repo_root: Path | str, n_bins: int = 4) -> dict:
    repo_root = Path(repo_root)
    history = load_verdict_history(repo_root)
    latest = latest_per_pair(history)
    counts = Counter(r.get("verdict") for r in latest.values())
    total_judged = sum(counts.get(v, 0) for v in VERDICT_LABELS)
    frontier = er.proposal_pairs(repo_root)
    frontier_keys = {(p["query"], p["id"]) for p in frontier}
    never_judged = frontier_keys - set(latest.keys())

    reversals = reversed_wires(history)
    n_ever_wire = len(ever_wire_pairs(history))
    recurred = recurred_after_verdict(repo_root, latest)

    return {
        "meter": "N38 audit-effect meter",
        "repo_root": str(repo_root),
        "ledgers": {"proposals_file": er.PROPOSALS_FILE, "verdicts_file": er.VERDICTS_FILE},
        "data_status": {
            "n_verdict_lines_raw": len(history),
            "n_distinct_pairs_judged": total_judged,
            "n_current_frontier": len(frontier),
            "context_note": (
                "the '118 welded Haiku verdicts' cited in OPEN_STACK.md's N27 row are "
                "archive/self_record/_weld's TRAIT accept/refuse weld (jury_bench.py's task), "
                "a DIFFERENT ledger and judgment domain from this script's wire/grit/noise "
                "geometric-proposal ledger. This section reports what is ACTUALLY banked in "
                f"{er.VERDICTS_FILE} in this checkout, not that figure.")
            if total_judged == 0 else None,
        },
        "headline": {
            "pre_audit_false_association_rate": (
                round(counts.get("noise", 0) / total_judged, 4) if total_judged else None),
            "n": total_judged,
            "definition": ("noise / (wire+grit+noise) among distinct judged pairs (latest "
                          "verdict wins) — the raw geometry's error rate as caught by the "
                          "audit."),
            "verdict_counts": {v: counts.get(v, 0) for v in VERDICT_LABELS},
        },
        "post_audit": {
            "n_ever_wire": n_ever_wire,
            "n_wire_reversed": len(reversals),
            "wire_reversal_rate": (round(len(reversals) / n_ever_wire, 4)
                                  if n_ever_wire else None),
            "reversals": reversals,
            "recurred_after_verdict_counts": {k: len(v) for k, v in recurred.items()},
            "recurred_after_verdict_detail": recurred,
            "supported_claim": (
                "of pairs the audit approved (wire) at any point, the fraction later "
                "CONTRADICTED by a subsequent banked verdict for the same (query, id); and, "
                "separately, the fraction of already-judged pairs (wire or noise) that "
                "RE-SURFACED unchanged in the live proposals frontier after judgment."),
            "unsupported_claim": (
                "the ask's literal design — re-fire the SAME exploratory queries and count "
                "re-banked false associations strictly pre vs post a controlled point — needs "
                "a paired before/after run this ledger does not timestamp or session-tag; it "
                "cannot be separated from the reversal/recurrence proxy above without that."),
        },
        "per_period": _per_period(history, n_bins),
        "jury_precision_proxy": {
            **method_agreement(history),
            "jury_bench_applicable": False,
            "jury_bench_reason": (
                "jury_bench.py's gold set (archive/self_record/_weld) judges TRAIT "
                "accept/refuse adjudication, a different task domain from wire/grit/noise "
                "geometric-proposal judging; no independent gold labels exist for THIS task "
                "beyond the banked verdicts themselves."),
        },
        "frontier": {
            "n_total": len(frontier),
            "n_never_judged": len(never_judged),
            "n_recurred_after_verdict": sum(len(v) for v in recurred.values()),
        },
        "method_breakdown": {
            m: dict(Counter(r.get("verdict") for r in latest.values() if r.get("method") == m))
            for m in sorted({r.get("method") for r in latest.values() if r.get("method")})
        },
    }


def render_table(report: dict) -> str:
    lines = []
    h = report["headline"]
    lines.append(f"N38 AUDIT-EFFECT METER  (repo: {report['repo_root']})")
    lines.append("-" * 60)
    lines.append(f"judged pairs (distinct, latest-wins): {h['n']}")
    vc = h["verdict_counts"]
    lines.append(f"  wire={vc['wire']}  grit={vc['grit']}  noise={vc['noise']}")
    pa = h["pre_audit_false_association_rate"]
    lines.append(f"pre-audit false-association rate: "
                 f"{'N/A (n=0)' if pa is None else f'{pa:.1%}'}  (N={h['n']})")
    pas = report["post_audit"]
    wr = pas["wire_reversal_rate"]
    lines.append(f"wire reversal rate: {'N/A (no wires yet)' if wr is None else f'{wr:.1%}'}"
                 f"  ({pas['n_wire_reversed']}/{pas['n_ever_wire']})")
    rec = pas["recurred_after_verdict_counts"]
    lines.append(f"recurred in live frontier after verdict: "
                 f"wire={rec['wire']} grit={rec['grit']} noise={rec['noise']}")
    pp = report["per_period"]
    lines.append("")
    cov = pp["calendar_ts_coverage_fraction"]
    if pp["supported_as_calendar_time"]:
        lines.append(f"per-period, CALENDAR-DAY bins (ts coverage {cov:.0%}, supported):")
        cbins = pp["calendar_bins"]
        if not cbins:
            lines.append("  (no ts-covered verdicts banked — nothing to bin)")
        else:
            lines.append(f"  {'day':>10} {'n':>4} {'wire':>5} {'grit':>5} {'noise':>6} "
                         f"{'noise%':>7}")
            for b in cbins:
                nr = "  N/A" if b["noise_rate"] is None else f"{b['noise_rate']:>6.1%}"
                lines.append(f"  {b['day']:>10} {b['n']:>4} {b['wire']:>5} {b['grit']:>5} "
                            f"{b['noise']:>6} {nr:>7}")
        lines.append("")
    lines.append(f"per-period (LEDGER-ORDER bins, not calendar time — ts coverage {cov:.0%}, "
                 f"{'below' if not pp['supported_as_calendar_time'] else 'prefix only'} "
                 f"threshold; see report for why):")
    bins = pp["order_bins"]
    if not bins:
        lines.append("  (no verdicts banked — nothing to bin)")
    else:
        lines.append(f"  {'bin':>3} {'n':>4} {'wire':>5} {'grit':>5} {'noise':>6} {'noise%':>7}")
        for b in bins:
            nr = "  N/A" if b["noise_rate"] is None else f"{b['noise_rate']:>6.1%}"
            lines.append(f"  {b['bin']:>3} {b['n']:>4} {b['wire']:>5} {b['grit']:>5} "
                        f"{b['noise']:>6} {nr:>7}")
    jp = report["jury_precision_proxy"]
    lines.append("")
    if jp["n_pairs_regraded_both_methods"]:
        lines.append(f"mechanical-vs-jury agreement (re-graded pairs only, N="
                     f"{jp['n_pairs_regraded_both_methods']}): {jp['agreement_rate']:.1%}")
    else:
        lines.append("mechanical-vs-jury agreement: N/A (no pair re-graded under both "
                     "methods yet)")
    lines.append("jury_bench.py fixtures: NOT APPLICABLE (different task domain — see report)")
    dstat = report["data_status"].get("context_note")
    if dstat:
        lines.append("")
        lines.append("NOTE: " + dstat)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=ROOT, help="repo root (default: this repo)")
    ap.add_argument("--out", type=Path, default=None, help="also write the JSON report here")
    ap.add_argument("--table", action="store_true", help="print a compact human table too")
    ap.add_argument("--periods", type=int, default=4,
                    help="number of ledger-order bins for the per-period proxy (default 4)")
    a = ap.parse_args(argv)

    report = build_report(a.root, n_bins=a.periods)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if a.out:
        a.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if a.table:
        print()
        print(render_table(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
