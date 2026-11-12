"""summary.py - recompute every served number from the rows, and exit nonzero on disagreement.

The ``bench_summary.py`` law, ported into the atlas: a summary is not a record of what the runner
believed, it is a recomputation from the rows that ASSERTS agreement with what the runner banked.
If the two split, the recomputation is wrong or the bank is wrong, and either way the number
must not be served. ``SummaryDisagreement`` is the refusal; ``python -m atlas.bench.summary``
exits 1 on it.

Order is law, not preference. CORRECTNESS FIRST: the per-class x arm correctness table is
computed, printed and written before any cost number exists in the output, and every cost
aggregate is taken over CORRECT tasks only. An arm that answers nothing has no cost worth
comparing.

PHASE 3 ADDS FOUR BLOCKS, each of them an inheritance from a Phase 2 verdict row:

  ``served_ranks``        the rank-aware table beside correctness. Additive - it reads the two new
                          row columns and changes no verdict - and it exists because the planted
                          control proved the correctness metric blind to order.
  ``bootstrap``           a seeded task-level CI on every arm's total, and the pairwise
                          differences. Per-class cells carry ``n=3, not separable`` instead of a
                          number pretending to be one.
  ``stop_condition``      the pre-registered Phase 3 stop, EVALUATED mechanically from the rows
                          and printed whichever way it goes. The registration is on disk with a
                          timestamp before the run; this is the arithmetic that reads it.
  ``external_reference``  the ``incumbent-live`` row: the deployed system measured as-is, on a
                          different universe, printed BESIDE the fair table and never inside it.

Two blocks travel with every summary:

  ``surfaces_to_correct``   which numbers on the author's live surfaces a run INHERITS and which
                            it REPLACES. Loaded from ``atlas/bench/surfaces/`` as data - the deck
                            numbers are record, and record does not live in source. It also
                            carries the staleness flag on the deck slide that says no competitor
                            benchmarks were measured, because the day a comparator number lands
                            that sentence stops being true.
  ``prediction_vs_outcome`` the pre-registered prediction table beside what happened, per class.
                            Registered before the scored run and hashed with the bundle; printed
                            whether it was right or wrong, which is the only version of a
                            prediction table that is worth anything.

Surface corrections are the author's under the two-ends law. This module states what changed; it
never edits a surface.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ..errors import SummaryDisagreement
from ..ids import chash
from ..store import read_jsonl, write_atomic
from .cost import median, percentile
from .runner import _deterministic_rows
from .stats import PER_CLASS_ANNOTATION, bootstrap_totals

SURFACES_DIR = Path(__file__).resolve().parents[3] / "atlas" / "bench" / "surfaces"   # the container's bench data (R2)
DEFAULT_SURFACES = SURFACES_DIR / "deck_surfaces_2026-07-30.json"


# ---------------------------------------------------------------------------
# recomputation
# ---------------------------------------------------------------------------

def load_rows(run_dir: Path) -> list[dict[str, Any]]:
    return list(read_jsonl(Path(run_dir) / "rows.jsonl"))


def load_manifest(run_dir: Path) -> dict[str, Any]:
    return json.loads((Path(run_dir) / "manifest.json").read_text(encoding="utf-8"))


def assert_rows_are_the_judged_rows(rows: list[dict[str, Any]],
                                    manifest: dict[str, Any]) -> None:
    """Refuse rows that are not the rows the manifest was written over.

    THE HOLE THIS CLOSES, found by the Phase 2 judge with scratch mutations. The per-arm cost
    assertions catch a tampered COST number, but a mutation that leaves every per-arm aggregate
    intact walks straight through them: relabel one row's ``class`` and the correctness table
    moves while nothing it asserts changes; edit ``tokens_context``, which no aggregate reads,
    and nothing notices at all. The runner already hashes the rows minus latency into
    ``rows_digest``; recomputing that hash here is the check that covers EVERY field of EVERY row
    rather than the handful the aggregates happen to touch.

    Cheap, total, and it is the same function the determinism gate compares - so a summary and a
    determinism re-run cannot disagree about what "the same rows" means.
    """
    declared = manifest.get("rows_digest")
    if not declared:
        raise SummaryDisagreement(
            "the run manifest carries no rows_digest, so the rows cannot be bound to it",
            run_label=manifest.get("run_label"),
        )
    computed = chash(_deterministic_rows(rows))
    if computed != declared:
        raise SummaryDisagreement(
            "rows.jsonl is not the rows this manifest was written over - some row field moved "
            "after the run (the digest covers every field except latency_ms)",
            declared=declared, computed=computed, rows=len(rows),
        )


def arms_of(rows: list[dict[str, Any]]) -> list[str]:
    seen: list[str] = []
    for r in rows:
        if r["arm"] not in seen:
            seen.append(r["arm"])
    return seen


def classes_of(rows: list[dict[str, Any]]) -> list[str]:
    seen: list[str] = []
    for r in rows:
        if r["class"] not in seen:
            seen.append(r["class"])
    return seen


def correctness(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The correctness table. Computed first, and nothing in it is a cost."""
    arms, classes = arms_of(rows), classes_of(rows)
    per_class = {
        cl: {arm: {
            "correct": sum(1 for r in rows if r["arm"] == arm and r["class"] == cl and r["correct"]),
            "total": sum(1 for r in rows if r["arm"] == arm and r["class"] == cl),
        } for arm in arms}
        for cl in classes
    }
    totals = {arm: {"correct": sum(1 for r in rows if r["arm"] == arm and r["correct"]),
                    "total": sum(1 for r in rows if r["arm"] == arm)} for arm in arms}
    return {"arms": arms, "classes": classes, "per_class": per_class, "totals": totals}


def cost(rows: list[dict[str, Any]], manifest: dict[str, Any]) -> dict[str, Any]:
    """Cost, recomputed over CORRECT tasks only, and asserted against the banked manifest."""
    out: dict[str, Any] = {}
    for arm in arms_of(rows):
        sub = [r for r in rows if r["arm"] == arm]
        ok = [r for r in sub if r["correct"]]
        touched = [r["tokens_touched"] for r in ok]
        lat = [r["latency_ms"] for r in sub]
        banked = manifest["cost"][arm]
        recomputed = {
            "correct": len(ok),
            "total_tasks": len(sub),
            "tokens_touched_median_correct": int(median(touched)) if touched else None,
            "tokens_touched_total_correct": sum(touched),
            "tokens_context_median_correct": (int(median([r["tokens_context"] for r in ok]))
                                              if ok else None),
            "scan_bytes_total_uncharged": sum(r["cost"]["scan_bytes_uncharged"] for r in sub),
            "query_model_calls": sum(r["cost"]["query_model_calls"] for r in sub),
            "latency_median_ms": round(median(lat), 3) if lat else None,
            "latency_p95_ms": round(percentile(lat, 0.95), 3) if lat else None,
            "fold": banked["fold"],
            "fold_amortized_per_query": banked["fold_amortized_per_query"],
        }
        for key, banked_key in (("tokens_touched_median_correct", ("tokens_touched", "median")),
                                ("tokens_touched_total_correct", ("tokens_touched", "total")),
                                ("scan_bytes_total_uncharged", ("scan_bytes_total_uncharged",)),
                                ("query_model_calls", ("query_model_calls",))):
            node: Any = banked
            for part in banked_key:
                node = node[part]
            if recomputed[key] != node:
                raise SummaryDisagreement(
                    "recomputed cost disagrees with the banked run manifest",
                    arm=arm, field=key, recomputed=recomputed[key], banked=node,
                )
        out[arm] = recomputed
    return out


def served_ranks(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The rank-aware table. Reads the additive columns only; asserts and changes nothing.

    THE SERVED LIST IS NOT ALWAYS ``k`` LONG, and the Phase 3 judge was right to flag that the
    first version of this table hid it. ``incumbent_arch`` runs TWO rounds (beam 8 then 16) and
    its served list is the UNION of both, so it declares ``k=10`` and serves a median of 14 items
    - a column headed "evidence in top-k" was therefore comparing a 14-list against the retrieval
    arms' 10-lists. The direction of that unevenness FLATTERS the incumbent (more slots, more
    chances to carry an atom) so the stop condition is unaffected, but the column was uneven and
    is now honest: it is headed "evidence in the served list" and the served-list length is
    printed beside it. Nothing about the scored rows changes - this is a display repair over the
    same banked data, and the rows_digest is unmoved.

    THREE STATES, not two, because an arm can rank without being rank-INSTRUMENTED:

      ``unranked``        the arm returns no ranking at all (the flat reads). Null, never zero.
      ``instrumented``    the arm ranks and the rank pass could resolve its items.
      ``uninstrumented``  the arm ranks but every rank came back null. On this run that is
                          ``grep_skilled``, and the reason is the instrument rather than the arm:
                          it ranks NODE ids and supplies no ``retrieved_texts``, so
                          ``rank_columns`` resolves each id against the view's SPANS, finds
                          nothing, and scores it against an empty string. Reporting that as "the
                          evidence never appeared" would be a measurement of the harness. It is
                          named instead, and it is owed a fix in Phase 4 - which cannot be made
                          here, because changing a rank column would move scored rows.
    """
    arms = arms_of(rows)
    out: dict[str, Any] = {}
    for arm in arms:
        sub = [r for r in rows if r["arm"] == arm]
        ranked = [r for r in sub if r.get("ground_truth_rank") is not None]
        completes = [r["first_hit_rank"] for r in sub if r.get("first_hit_rank") is not None]
        served = [len(r.get("retrieved") or []) for r in sub]
        returns_a_list = any(served)
        resolved = any(r.get("ground_truth_rank") is not None
                       or r.get("first_hit_rank") is not None for r in sub)
        state = ("unranked" if not returns_a_list
                 else "instrumented" if resolved else "uninstrumented")
        gt = [r["ground_truth_rank"] for r in ranked]
        out[arm] = {
            "ranks": returns_a_list,
            "rank_state": state,
            "tasks": len(sub),
            "served_len_median": int(median(served)) if served else 0,
            "served_len_min": min(served) if served else 0,
            "served_len_max": max(served) if served else 0,
            "declared_k": None,
            "gt_rank_median": int(median(gt)) if gt else None,
            "gt_at_1": sum(1 for v in gt if v == 1),
            "gt_hit_tasks": len(gt),
            "gt_never": (len(sub) - len(gt)) if state == "instrumented" else None,
            "hit_rank_median": int(median(completes)) if completes else None,
            "completed_in_list": len(completes),
            "correct": sum(1 for r in sub if r["correct"]),
        }
    return out


def evaluate_stop(rows: list[dict[str, Any]], manifest: dict[str, Any]) -> dict[str, Any] | None:
    """Evaluate the PRE-REGISTERED stop from the rows. Returns None when none was registered.

    The condition, registered before the run: *if ``incumbent_arch``'s correct-count is below
    ``dense_flat``'s at comparable tokens_touched (medians within 2x), the engine's measured
    advantage is a WAKE advantage, not a retrieval advantage.*

    Evaluated here rather than read off by eye, and reported whichever way it falls - "either
    outcome is a deliverable" is only true if both outcomes are computed by the same code.
    """
    stop = manifest.get("stop_condition")
    if not stop:
        return None
    challenger = stop.get("challenger", "incumbent_arch")
    baseline = stop.get("baseline", "dense_flat")
    ratio_cap = float(stop.get("comparable_token_ratio", 2.0))
    present = set(arms_of(rows))
    if challenger not in present or baseline not in present:
        return {**stop, "evaluated": False,
                "reason": f"one of the two arms is absent from this run "
                          f"({challenger in present=}, {baseline in present=})"}

    def stats(arm: str) -> tuple[int, int | None]:
        sub = [r for r in rows if r["arm"] == arm]
        ok = [r["tokens_touched"] for r in sub if r["correct"]]
        return sum(1 for r in sub if r["correct"]), (int(median(ok)) if ok else None)

    c_correct, c_tokens = stats(challenger)
    b_correct, b_tokens = stats(baseline)
    if c_tokens and b_tokens:
        ratio = max(c_tokens, b_tokens) / min(c_tokens, b_tokens)
    else:
        ratio = None
    comparable = bool(ratio is not None and ratio <= ratio_cap)
    fired = bool(c_correct < b_correct and comparable)
    return {
        **stop,
        "evaluated": True,
        "challenger": challenger, "baseline": baseline,
        "challenger_correct": c_correct, "baseline_correct": b_correct,
        "challenger_tokens_median": c_tokens, "baseline_tokens_median": b_tokens,
        "token_ratio": (round(ratio, 3) if ratio is not None else None),
        "comparable_token_ratio": ratio_cap,
        "tokens_comparable": comparable,
        "fired": fired,
        "verdict": ("FIRED - the engine's measured advantage is a WAKE advantage, not retrieval"
                    if fired else
                    "NOT FIRED - the condition's antecedent does not hold on these rows"),
    }


def external_reference(reference_dir: Path | None) -> dict[str, Any] | None:
    """Load the ``incumbent-live`` reference: the deployed system, measured on its own universe.

    A DECLARED EXTERNAL REFERENCE and never a table row. Its provenance is different in the one
    way that matters most - the live tree includes sealed-derived stores no arm in the fair table
    can see, and its corpus is the working tree rather than the frozen snapshot - so ranking it
    beside arms that were denied those things would be the comparison the study exists to avoid
    making. It is loaded, printed beside, and labelled.
    """
    if reference_dir is None:
        return None
    reference_dir = Path(reference_dir)
    manifest_path = reference_dir / "manifest.json"
    rows_path = reference_dir / "rows.jsonl"
    if not manifest_path.is_file() or not rows_path.is_file():
        raise SummaryDisagreement(
            "an external reference directory was named but does not carry manifest.json and "
            "rows.jsonl - a reference that cannot be recomputed is a quotation",
            path=str(reference_dir))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = list(read_jsonl(rows_path))
    correct = sum(1 for r in rows if r.get("correct"))
    touched = [r["tokens_touched"] for r in rows if r.get("correct")]
    seconds = [r.get("seconds", 0.0) for r in rows]
    return {
        "kind": "external-reference/1",
        "label": manifest.get("label", "incumbent-live"),
        "ranked_in_fair_table": False,
        "provenance": manifest.get("provenance", ""),
        "universe": manifest.get("universe", "live working tree (NOT the frozen snapshot)"),
        "correct": correct,
        "total_tasks": len(rows),
        "tokens_touched_median_correct": int(median(touched)) if touched else None,
        "tokens_touched_total_correct": sum(touched),
        "latency_median_s": round(median(seconds), 3) if seconds else None,
        "manifest": manifest,
    }


def prediction_vs_outcome(rows: list[dict[str, Any]],
                          predictions: dict[str, Any]) -> list[dict[str, Any]]:
    """The registered prediction beside what happened, per class. Printed right or wrong."""
    table = correctness(rows)
    out: list[dict[str, Any]] = []
    for cl in table["classes"]:
        pred = predictions.get("per_class", {}).get(cl, {})
        scores = {arm: table["per_class"][cl][arm]["correct"] for arm in table["arms"]}
        best = max(scores.values()) if scores else 0
        winners = sorted(a for a, s in scores.items() if s == best and best > 0)
        predicted = pred.get("predicted_winner")
        if predicted == "none":
            hit = best == 0
        elif predicted:
            hit = predicted in winners
        else:
            hit = None
        out.append({
            "class": cl,
            "predicted_winner": predicted,
            "reason": pred.get("reason", ""),
            "observed_winners": winners,
            "observed_scores": scores,
            "prediction_held": hit,
        })
    return out


def surfaces_to_correct(rows: list[dict[str, Any]],
                        surfaces_path: Path = DEFAULT_SURFACES) -> dict[str, Any]:
    """Which live-surface numbers this run inherits and which it replaces. Loaded as data."""
    if not Path(surfaces_path).is_file():
        raise SummaryDisagreement("the surfaces record is missing; a summary cannot state what "
                                  "it inherits without it", path=str(surfaces_path))
    record = json.loads(Path(surfaces_path).read_text(encoding="utf-8"))
    comparator_measured = bool(rows)
    block = dict(record)
    block["comparator_number_measured_this_run"] = comparator_measured
    for flag in block.get("staleness_flags", []):
        flag["fires_now"] = bool(comparator_measured and flag.get("fires_on_first_comparator"))
    return block


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def _markdown_table(header: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(header) + " |",
           "|" + "|".join("---" for _ in header) + "|"]
    for r in rows:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)


def render(run_dir: Path, predictions: dict[str, Any] | None = None,
           surfaces_path: Path = DEFAULT_SURFACES,
           reference_dir: Path | None = None) -> str:
    """The whole summary as markdown. Correctness first, cost after, prediction table last."""
    rows = load_rows(run_dir)
    manifest = load_manifest(run_dir)
    assert_rows_are_the_judged_rows(rows, manifest)
    table = correctness(rows)
    costs = cost(rows, manifest)
    ranks = served_ranks(rows)
    ci = bootstrap_totals(rows)
    stop = evaluate_stop(rows, manifest)
    reference = external_reference(reference_dir)

    lines: list[str] = []
    lines.append(f"# bench v2 run - {manifest.get('run_label') or Path(run_dir).name}")
    lines.append("")
    lines.append(f"- verdict: **{manifest['verdict']}**"
                 + (f" ({manifest['verdict_row']})" if manifest.get("verdict_row") else ""))
    lines.append(f"- bundle_id: `{manifest['bundle_id']}`")
    lines.append(f"- snapshot_id: `{manifest['snapshot_id']}`")
    lines.append(f"- segmentation_id: `{manifest['segmentation_id']}`")
    lines.append(f"- universe: `{manifest['universe']['name']}` "
                 f"({manifest['view_stats']['nodes_included']} nodes, "
                 f"{manifest['view_stats']['leaf_spans_included']} leaf spans)")
    lines.append(f"- frozen {manifest['bundle_frozen_ts']} < run started "
                 f"{manifest['started_ts']}: **{manifest['freeze_before_run']}**")
    lines.append(f"- rows_digest: `{manifest['rows_digest']}`")
    lines.append("")

    lines.append("## correctness (before any cost number)")
    lines.append("")
    header = ["class"] + table["arms"]
    body = []
    for cl in table["classes"]:
        row = [cl]
        for arm in table["arms"]:
            cell = table["per_class"][cl][arm]
            row.append(f"{cell['correct']}/{cell['total']}")
        body.append(row)
    body.append(["**total**"] + [f"**{table['totals'][a]['correct']}/{table['totals'][a]['total']}**"
                                 for a in table["arms"]])
    lines.append(_markdown_table(header, body))
    lines.append("")
    lines.append(f"Every per-class cell above is **{PER_CLASS_ANNOTATION}**: three tasks admit "
                 f"only 0, 1/3, 2/3 or 1, and no interval over four possible values separates "
                 f"2/3 from 1/3. Class cells are readable as direction, never as ranking. The "
                 f"bootstrap below applies to the TOTALS, where n=21.")
    lines.append("")

    lines.append("## totals with a seeded bootstrap CI")
    lines.append("")
    lines.append(_markdown_table(
        ["arm", "correct", "95% CI", "rate", "rate CI"],
        [[arm, f"{ci['per_arm'][arm]['observed_correct']}/{ci['per_arm'][arm]['total_tasks']}",
          f"[{ci['per_arm'][arm]['ci_low']}, {ci['per_arm'][arm]['ci_high']}]",
          f"{ci['per_arm'][arm]['rate']:.3f}",
          f"[{ci['per_arm'][arm]['rate_ci_low']:.3f}, {ci['per_arm'][arm]['rate_ci_high']:.3f}]"]
         for arm in table["arms"]]))
    lines.append("")
    lines.append(f"Paired task-level percentile bootstrap, **{ci['resamples']:,} resamples, seed "
                 f"{ci['seed']}**, one resampled task-index set per replicate applied to every "
                 f"arm. The intervals are wide because n=21; that is the measurement, not a "
                 f"presentation problem.")
    lines.append("")
    separating = [p for p in ci["pairwise"] if p["excludes_zero"]]
    lines.append(f"Pairwise differences whose 95% interval **excludes zero**: "
                 f"**{len(separating)} of {len(ci['pairwise'])}**."
                 + (" None - at this task count no arm separates from any other."
                    if not separating else ""))
    if separating:
        lines.append("")
        lines.append(_markdown_table(
            ["arm A", "arm B", "A - B", "95% CI"],
            [[p["arm_a"], p["arm_b"], str(p["observed_difference"]),
              f"[{p['ci_low']}, {p['ci_high']}]"] for p in separating]))
    lines.append("")
    lines.append("An interval excluding zero is NOT a significance claim and is not offered as "
                 "one; it is the weakest honest statement the resample supports.")
    lines.append("")

    lines.append("## served rank (additive - the frozen correctness definition is unchanged)")
    lines.append("")

    def _rank_cells(arm: str) -> list[str]:
        cell = ranks[arm]
        served = (f"{cell['served_len_median']}"
                  + (f" ({cell['served_len_min']}-{cell['served_len_max']})"
                     if cell["served_len_min"] != cell["served_len_max"] else ""))
        if cell["rank_state"] == "unranked":
            return [arm, "**no** (fixed read set)", "0", "-", "-", "-", "-", "-"]
        if cell["rank_state"] == "uninstrumented":
            return [arm, "yes", served, "*not instrumented*", "*not instrumented*",
                    "*not instrumented*", "*not instrumented*", "*not instrumented*"]
        return [arm, "yes", served,
                str(cell["gt_rank_median"]),
                f"{cell['gt_at_1']}/{cell['tasks']}",
                f"{cell['gt_hit_tasks']}/{cell['tasks']}",
                f"{cell['gt_never']}/{cell['tasks']}",
                str(cell["hit_rank_median"])]

    lines.append(_markdown_table(
        ["arm", "ranks?", "served list length (median)", "evidence rank (median)",
         "evidence at rank 1", "evidence in the served list", "evidence never served",
         "answer completed at rank (median)"],
        [_rank_cells(arm) for arm in table["arms"]]))
    lines.append("")
    lines.append("**Read the served-list length column before the ones beside it.** The counts "
                 "are per-arm denominators, not a shared one: an arm that serves more items has "
                 "more chances to carry an atom. `incumbent_arch` declares `k=10` but runs two "
                 "rounds (beam 8 then 16) and serves the UNION, so its list is longer than the "
                 "single-round arms' - which flatters it on this table, not the reverse.")
    lines.append("")
    lines.append("`ground_truth_rank` is the rank of the first served item carrying any task "
                 "atom; `first_hit_rank` is the shortest prefix that satisfies the frozen scorer. "
                 "Both are null - never zero - for an arm with a fixed read set, because a fixed "
                 "read set has no ranking. This table is why the correctness column above is not "
                 "a ranking on its own: the planted control put a WRONG answer at rank 1 on six "
                 "of six retrieval cells and moved no verdict at all.")
    uninstrumented = [a for a in table["arms"] if ranks[a]["rank_state"] == "uninstrumented"]
    if uninstrumented:
        lines.append("")
        lines.append(f"**`{'`, `'.join(uninstrumented)}` rank(s) but is NOT rank-instrumented** "
                     f"and its cells say so rather than showing zeros. It ranks NODE ids and "
                     f"supplies no `retrieved_texts`, so the rank pass resolves each id against "
                     f"the view's SPANS, finds nothing, and would score it against an empty "
                     f"string. Printing that as \"the evidence never appeared\" would report a "
                     f"property of the harness as a property of the arm. Owed a fix in Phase 4: "
                     f"it cannot be made here, because changing a rank column moves scored rows.")
    lines.append("")

    if stop is not None:
        lines.append("## the pre-registered stop")
        lines.append("")
        lines.append(f"> {stop.get('condition', '(no condition text)')}")
        lines.append("")
        if not stop.get("evaluated"):
            lines.append(f"**NOT EVALUABLE** - {stop.get('reason')}")
        else:
            lines.append(_markdown_table(
                ["", "correct", "tokens_touched median (correct)"],
                [[stop["challenger"], str(stop["challenger_correct"]),
                  str(stop["challenger_tokens_median"])],
                 [stop["baseline"], str(stop["baseline_correct"]),
                  str(stop["baseline_tokens_median"])]]))
            lines.append("")
            lines.append(f"- token ratio **{stop['token_ratio']}x** against a comparability "
                         f"cap of {stop['comparable_token_ratio']}x -> "
                         f"**{'comparable' if stop['tokens_comparable'] else 'NOT comparable'}**")
            lines.append(f"- correct-count: {stop['challenger']} "
                         f"{stop['challenger_correct']} vs {stop['baseline']} "
                         f"{stop['baseline_correct']}")
            lines.append("")
            lines.append(f"### **{stop['verdict']}**")
        lines.append("")
        lines.append(f"Registered {stop.get('registered_ts')} "
                     f"(`{str(stop.get('sha256'))[:23]}...`), before the run started "
                     f"{manifest.get('started_ts')}: "
                     f"**{manifest.get('stop_condition_before_run')}**.")
        lines.append("")

    lines.append("## cost (five dimensions, never summed; over CORRECT tasks only)")
    lines.append("")
    cost_header = ["arm", "correct", "tokens_touched median", "tokens_touched total",
                   "**fold model calls**", "**fold model tokens**", "query model calls",
                   "fold bill (s)", "fold this call (s)", "fold vectors",
                   "fold/query (s)", "latency median ms", "latency p95 ms",
                   "scan bytes (uncharged)"]
    cost_body = []
    for arm in table["arms"]:
        c = costs[arm]
        cost_body.append([
            arm, f"{c['correct']}/{c['total_tasks']}",
            str(c["tokens_touched_median_correct"]), str(c["tokens_touched_total_correct"]),
            f"**{c['fold']['model_calls']}**", f"**{c['fold']['model_tokens']:,}**",
            str(c["query_model_calls"]), f"{c['fold']['wall_seconds']:.2f}",
            f"{c['fold']['wall_seconds_this_call']:.2f}"
            + (" (cached)" if c["fold"]["cached"] else ""),
            str(c["fold"]["vectors_built"]),
            f"{c['fold_amortized_per_query']['wall_seconds_per_query']:.4f}",
            str(c["latency_median_ms"]), str(c["latency_p95_ms"]),
            str(c["scan_bytes_total_uncharged"]),
        ])
    lines.append(_markdown_table(cost_header, cost_body))
    lines.append("")
    lines.append(f"Fold cost is amortized over a stated reference count of "
                 f"{list(costs.values())[0]['fold_amortized_per_query']['reference_query_count']} "
                 f"queries. The five dimensions are never added together.")
    lines.append("")
    paying = [a for a in table["arms"] if costs[a]["fold"]["model_calls"]]
    lines.append(
        "**The fold model bill is the column that separates the arms.** "
        + (f"{', '.join(paying)} pays it; every other arm's is a counted zero, and "
           f"every arm's QUERY model calls are a counted zero. That is the shape the standing "
           f"ruling names - intelligence paid once at fold time, structure queried mechanically "
           f"(RW-20260801-intelligence-paid-at-authoring-time)."
           if paying else
           "No arm in this run pays one; every fold and query model call is a counted zero."))
    lines.append("")

    if predictions:
        lines.append("## pre-registered prediction vs outcome")
        lines.append("")
        pvo = prediction_vs_outcome(rows, predictions)
        lines.append(_markdown_table(
            ["class", "predicted winner", "observed winner(s)", "held?", "reason"],
            [[p["class"], str(p["predicted_winner"]), ", ".join(p["observed_winners"]) or "none",
              {True: "yes", False: "NO", None: "-"}[p["prediction_held"]],
              p["reason"][:160]] for p in pvo]))
        held = sum(1 for p in pvo if p["prediction_held"])
        lines.append("")
        lines.append(f"Predictions held: **{held}/{len(pvo)}**.")
        lines.append("")

    planted_path = Path(run_dir) / "planted.jsonl"
    if planted_path.is_file():
        planted = list(read_jsonl(planted_path))
        lines.append("## planted-bad control (false positives)")
        lines.append("")
        # ``was correct`` sits beside ``still correct`` so a flip is a DELTA a reader can see,
        # not a baseline they have to go and look up. The first reading of this table claimed a
        # flip that had not happened; the two columns make that error class structural.
        lines.append(_markdown_table(
            ["arm", "task", "planted rank", "false positive at k", "wrong answer in context",
             "was correct", "still correct", "verdict flipped"],
            [[p["arm"], p["task"], str(p["retrieved_rank"]),
              "YES" if p["false_positive_at_k"] else "no",
              "YES" if p["wrong_answer_in_context"] else "no",
              {True: "yes", False: "no", None: "-"}[p.get("was_correct")],
              "yes" if p["still_correct"] else "no",
              {True: "**YES**", False: "no", None: "-"}[p.get("verdict_flipped")]]
             for p in planted]))
        flips = sum(1 for p in planted if p.get("verdict_flipped"))
        lines.append("")
        lines.append(f"Verdict flips caused by the plants: **{flips}/{len(planted)}**. A false "
                     f"positive at rank 1 that flips no verdict is a failure the scoring metric "
                     f"cannot see - which is a finding about the metric, not a clean bill.")
        lines.append("")

    if reference is not None:
        lines.append("## external reference - NOT a row of the fair table")
        lines.append("")
        lines.append(_markdown_table(
            ["reference", "correct", "tokens_touched median (correct)", "latency median (s)",
             "ranked?"],
            [[reference["label"], f"{reference['correct']}/{reference['total_tasks']}",
              str(reference["tokens_touched_median_correct"]),
              str(reference["latency_median_s"]), "**no**"]]))
        lines.append("")
        lines.append(f"- universe: {reference['universe']}")
        lines.append(f"- provenance: {reference['provenance']}")
        lines.append("")
        lines.append("This row is the deployed system measured **as it actually runs** - the live "
                     "concept tree, which includes sealed-derived stores no arm in the fair table "
                     "is allowed to see, over the working tree rather than the frozen snapshot. "
                     "It is printed beside the table and is never ranked in it: a number obtained "
                     "with access the other arms were denied is not a comparison, and presenting "
                     "it as one is the exact move this study exists to avoid.")
        lines.append("")

    surfaces = surfaces_to_correct(rows, surfaces_path)
    lines.append("## surfaces_to_correct")
    lines.append("")
    lines.append(_markdown_table(
        ["surface number", "what it is", "this run"],
        [[s["number"], s["what"], s["disposition"]] for s in surfaces["numbers"]]))
    lines.append("")
    for flag in surfaces.get("staleness_flags", []):
        state = "FIRES NOW" if flag.get("fires_now") else "not fired"
        lines.append(f"- **{state}**: {flag['surface']} - {flag['claim']}")
    lines.append("")
    lines.append("Surface corrections are the author's (the two-ends law). This summary states "
                 "what moved; it edits nothing.")
    lines.append("")
    return "\n".join(lines)


def figure_input(run_dir: Path, predictions: dict[str, Any] | None = None,
                 reference_dir: Path | None = None) -> dict[str, Any]:
    """The recomputed numbers the figures draw. Figures never recompute anything themselves."""
    rows = load_rows(run_dir)
    manifest = load_manifest(run_dir)
    assert_rows_are_the_judged_rows(rows, manifest)
    return {
        "run_label": manifest.get("run_label"),
        "bundle_id": manifest["bundle_id"],
        "universe": manifest["universe"]["name"],
        "correctness": correctness(rows),
        "cost": cost(rows, manifest),
        "served_ranks": served_ranks(rows),
        "bootstrap": bootstrap_totals(rows),
        "stop_condition": evaluate_stop(rows, manifest),
        "external_reference": external_reference(reference_dir),
        "prediction_vs_outcome": prediction_vs_outcome(rows, predictions or {}),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="recompute and assert a bench run's numbers")
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--predictions", type=Path, default=None)
    ap.add_argument("--surfaces", type=Path, default=DEFAULT_SURFACES)
    ap.add_argument("--reference", type=Path, default=None,
                    help="an incumbent-live reference directory, printed BESIDE the fair table")
    ap.add_argument("--write", action="store_true", help="write table.md and figure_input.json")
    args = ap.parse_args(argv)

    predictions = (json.loads(args.predictions.read_text(encoding="utf-8"))
                   if args.predictions else None)
    try:
        text = render(args.run_dir, predictions, args.surfaces, args.reference)
        figures = figure_input(args.run_dir, predictions, args.reference)
    except SummaryDisagreement as exc:
        print(f"REFUSED {exc}", file=sys.stderr)
        return 1
    print(text)
    if args.write:
        write_atomic(args.run_dir / "table.md", text.encode("utf-8"))
        write_atomic(args.run_dir / "figure_input.json",
                     (json.dumps(figures, sort_keys=True, indent=2) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
