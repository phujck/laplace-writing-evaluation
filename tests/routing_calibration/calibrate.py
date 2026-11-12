"""Calibrate and measure the two decisions on the recorded corpus.

Run it from the worktree:

    scripts/laplace-python tests/routing_calibration/calibrate.py \
        --labels <labels.json> --out <dir> [--seed 20261002] [--folds 5]

Three splits, not two.  A head fitted on rows and then calibrated on the same rows
reports its own confidence back to itself, which is how an uncalibrated system comes
to look calibrated.  So each fold is: **train** (fit the head), **calibrate** (fit the
monotone map on held-out scores), **test** (everything reported).  Only test rows
appear in any accuracy, any reliability bin, any abstain rate.

What is reported, all of it with counts:

* accuracy on the test rows, per feature set, against two baselines --- the majority
  label, and a `tie` head that spreads mass evenly (which is what "the alphabet is
  closed but nothing is known" looks like);
* the reliability table: predicted probability against observed correctness, per
  bin, with n per bin, plus the expected calibration error;
* the abstain rate at the threshold that keeps the realised wrong-route cost under
  one turn, where a wrong route's price is that operation's exact contract
  (`src/laplace/writing_contracts.py:501`) and a turn is the operating brief
  (`src/laplace/writing_provider.py:738-745`);
* latency per decision;
* the characters delivered to decide, against what the system delivers today.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
from pathlib import Path
import random
import statistics
import sys
import time

HERE = Path(__file__).resolve().parent
TREE = HERE.parents[1]
sys.path.insert(0, str(TREE / "src"))

from laplace.native import routing  # noqa: E402


def contract_chars(path: Path | None = None) -> dict[str, int]:
    """Per-operation exact-contract size: the price of recovering a wrong route."""
    if path and path.exists():
        return {k: int(v) for k, v in json.loads(path.read_text())["contract_chars"].items()}
    from laplace.native import contracts as writing_contracts
    from laplace.writing import reads
    out = {}
    for op in sorted(reads.READS | reads.WRITES):
        try:
            out[op] = len(json.dumps(writing_contracts.exact_contract(op, permitted=True),
                                     ensure_ascii=False, default=str))
        except Exception:  # noqa: BLE001
            out[op] = routing.CONTRACT_CHARS_MEDIAN
    return out


class TieDecider:
    """The floor: every option equally likely.  No information, a closed alphabet."""

    name = "tie"

    def ask(self, state_text, options, instructions, feature_hint=()):  # noqa: ANN001,D102
        share = 1.0 / max(len(options), 1)
        return {o: share for o in options}


class MajorityDecider:
    name = "majority"

    def __init__(self, label: str) -> None:
        self.label = label

    def ask(self, state_text, options, instructions, feature_hint=()):  # noqa: ANN001,D102
        return {o: (1.0 if o == self.label else 0.0) for o in options}


def three_way(rows: list, seed: int, fold: int, folds: int) -> tuple[list, list, list]:
    """A deterministic train / calibrate / test split: 60 / 20 / 20 by fold rotation."""
    order = list(range(len(rows)))
    random.Random(seed).shuffle(order)
    blocks = [[] for _ in range(folds)]
    for position, index in enumerate(order):
        blocks[position % folds].append(rows[index])
    test = blocks[fold % folds]
    calib = blocks[(fold + 1) % folds]
    train = [r for i, b in enumerate(blocks) if i not in ((fold % folds), ((fold + 1) % folds))
             for r in b]
    return train, calib, test


def d1_features(row: dict, feature_set: str) -> tuple[str, ...]:
    state = routing.RouteState(**row["state"])
    return routing.features(state, feature_set)


def run_d1(rows: list[dict], *, seed: int, folds: int, feature_set: str,
           costs: dict[str, int]) -> dict:
    per_fold = []
    pooled: list[dict] = []
    for fold in range(folds):
        train, calib, test = three_way(rows, seed, fold, folds)
        head = routing.PriorDecider(name="prior/" + feature_set).fit(
            [(d1_features(r, feature_set), r["label"]) for r in train])
        options = [tuple(p) for p in routing.ROUTE_OPTIONS]
        calib_pairs = []
        for row in calib:
            decision = routing.route(routing.RouteState(**row["state"]), decider=head,
                                     feature_set=feature_set, options=options, threshold=0.0)
            calib_pairs.append((decision.raw_probability, decision.choice == row["label"]))
        mapping = routing.fit_calibration(calib_pairs, fitted_on="fold %d, %d rows" % (fold, len(calib)))
        # THE THRESHOLD IS CHOSEN HERE, ON THE CALIBRATE BLOCK, NEVER ON THE TEST BLOCK.
        # Round 2's judge measured the consequence of the other choice: a tau swept over the
        # same pooled test rows whose precision was then reported gave 0.986 in sample and
        # 0.914-0.947 when transferred, with the realised cost four to six times over one
        # turn -- so the lane's own acceptance rule failed out of sample at the tau the lane
        # shipped.  `three_way` already holds a block out for exactly this; nothing in the
        # split needed changing, only which block the sweep is allowed to see.
        fold_tau = _tau_on_calibrate(
            [{"p": _calibrated(routing.route(routing.RouteState(**row["state"]), decider=head,
                                             calibration=mapping, feature_set=feature_set,
                                             options=options, threshold=0.0)),
              "correct": routing.route(routing.RouteState(**row["state"]), decider=head,
                                       calibration=mapping, feature_set=feature_set,
                                       options=options, threshold=0.0).choice == row["label"],
              "contract_chars": costs.get(str(row.get("operation") or "").split()[0]
                                          if row.get("operation") else "",
                                          routing.CONTRACT_CHARS_MEDIAN)}
             for row in calib])
        fold_rows = []
        for row in test:
            started = time.perf_counter()
            decision = routing.route(routing.RouteState(**row["state"]), decider=head,
                                     calibration=mapping, feature_set=feature_set,
                                     options=options, threshold=0.0)
            elapsed = (time.perf_counter() - started) * 1000.0
            operation = str(row.get("operation") or "")
            fold_rows.append({"id": row["id"], "label": row["label"], "choice": decision.choice,
                              "correct": decision.choice == row["label"],
                              "p": decision.probability, "raw": decision.raw_probability,
                              "confidence": decision.confidence,
                              "state_chars": decision.state_chars, "latency_ms": elapsed,
                              "contract_chars": costs.get(operation.split()[0] if operation else "",
                                                          routing.CONTRACT_CHARS_MEDIAN),
                              "fold": fold, "source": row["source"],
                              "fold_tau": fold_tau})
        per_fold.append({"fold": fold, "train": len(train), "calibrate": len(calib),
                         "test": len(test),
                         "accuracy": _acc(fold_rows), "vocabulary": len(head.vocabulary),
                         "calibration_knots": len(mapping.knots),
                         "tau_chosen_on_calibrate": fold_tau})
        pooled.extend(fold_rows)
    return {"feature_set": feature_set, "folds": per_fold, "rows": pooled,
            "accuracy": _acc(pooled), "n": len(pooled)}


def run_d4(rows: list[dict], *, seed: int, folds: int, costs: dict[str, int]) -> dict:
    per_fold = []
    pooled: list[dict] = []
    for fold in range(folds):
        train, calib, test = three_way(rows, seed, fold, folds)
        head = routing.PriorDecider(name="prior/refusal").fit(
            [(routing.refusal_features(r["error"]), r["label"]) for r in train])
        calib_pairs = []
        for row in calib:
            decision = routing.classify(row["error"], decider=head, threshold=0.0)
            calib_pairs.append((decision.raw_probability, decision.choice == row["label"]))
        mapping = routing.fit_calibration(calib_pairs, fitted_on="fold %d, %d rows" % (fold, len(calib)))
        fold_tau = _tau_on_calibrate(
            [{"p": _calibrated(routing.classify(row["error"], decider=head,
                                                calibration=mapping, threshold=0.0)),
              "correct": routing.classify(row["error"], decider=head, calibration=mapping,
                                          threshold=0.0).choice == row["label"],
              "contract_chars": costs.get(str(row.get("operation") or "").split()[0]
                                          if row.get("operation") else "",
                                          routing.CONTRACT_CHARS_MEDIAN)}
             for row in calib])
        fold_rows = []
        for row in test:
            started = time.perf_counter()
            decision = routing.classify(row["error"], decider=head, calibration=mapping,
                                        threshold=0.0)
            elapsed = (time.perf_counter() - started) * 1000.0
            operation = str(row.get("operation") or "")
            fold_rows.append({"id": row["id"], "label": row["label"], "choice": decision.choice,
                              "correct": decision.choice == row["label"],
                              "p": decision.probability, "raw": decision.raw_probability,
                              "confidence": decision.confidence,
                              "state_chars": decision.state_chars, "latency_ms": elapsed,
                              "contract_chars": costs.get(operation.split()[0] if operation else "",
                                                          routing.CONTRACT_CHARS_MEDIAN),
                              "fold": fold, "source": row["source"],
                              "error_class": row.get("error_class"),
                              "live_substring_says": live_substring(row["error"]),
                              "fold_tau": fold_tau})
        per_fold.append({"fold": fold, "train": len(train), "calibrate": len(calib),
                         "test": len(test), "accuracy": _acc(fold_rows),
                         "vocabulary": len(head.vocabulary),
                         "tau_chosen_on_calibrate": fold_tau})
        pooled.extend(fold_rows)
    return {"folds": per_fold, "rows": pooled, "accuracy": _acc(pooled), "n": len(pooled)}


_LIVE_WORDS = ("changed", "stale", "conflict", "consumed")


def live_substring(text: str) -> str:
    """What the live decision at `src/laplace/writing_tools.py:1383` decides.

    It is a four-word substring test over the lower-cased message, and its only two
    answers are 'recover the turn context' and nothing.  Rendered here into the
    grammar's vocabulary so the two readings of one string can be scored on the same
    labels: a hit means it treated the refusal as identity-stale, a miss means it
    offered no kind at all.
    """
    low = (text or "").lower()
    return "identity-stale" if any(w in low for w in _LIVE_WORDS) else "<no kind>"


def _acc(rows: list[dict]) -> dict:
    if not rows:
        return {"n": 0}
    right = sum(1 for r in rows if r["correct"])
    return {"n": len(rows), "correct": right, "accuracy": round(right / len(rows), 4)}


def reliability(rows: list[dict], width: float = 0.1) -> dict:
    pairs = [(r["p"], r["correct"]) for r in rows]
    return routing.expected_calibration_error(pairs, width)


def threshold_sweep(rows: list[dict], turn_chars: int) -> dict:
    """The abstain curve, with two cost rules, because one rule does not fit both decisions.

    `realised_cost_chars` is the price of the wrong decisions a threshold let through:
    for D1 that is the contract the caller must then read, and the packet's rule --- keep
    it under one turn --- is the right rule there.

    `total_cost_chars` is the price of the WHOLE policy: an abstention is not free, it
    falls back to what the system does today, which is to embed that operation's
    contract in the failure response with the nested schema dropped above 9,500
    characters (`src/laplace/writing_tools.py:1260`).  So total = (abstained rows'
    BOUNDED contracts) + (wrong acted rows' FULL contracts, because curing a wrong
    decision means the exact `help` call, which is not truncated), against
    `today_cost_chars` = every row's bounded contract, which
    `src/laplace/writing_tools.py:1157` delivers unconditionally.  For D4 no threshold gets the realised
    cost under one turn --- 286 refusals cost more than one turn however few are wrong ---
    so the total rule is the one that says anything there, and it is reported for both.
    """
    table = []
    chosen = None
    best_total = None
    today = sum(routing.bounded_delivery(r["contract_chars"]) for r in rows)
    for step in range(0, 101):
        tau = step / 100.0
        acted = [r for r in rows if r["p"] >= tau]
        wrong = [r for r in acted if not r["correct"]]
        abstained = [r for r in rows if r["p"] < tau]
        cost = routing.realised_cost([r["contract_chars"] for r in wrong])
        total = cost + sum(routing.bounded_delivery(r["contract_chars"]) for r in abstained)
        row = {"threshold": round(tau, 2), "acted": len(acted),
               "abstained": len(abstained),
               "abstain_rate": round(len(abstained) / len(rows), 4) if rows else 0.0,
               "wrong": len(wrong), "realised_cost_chars": cost,
               "total_cost_chars": total,
               "saved_against_today": today - total,
               "precision_when_acting": round((len(acted) - len(wrong)) / len(acted), 4) if acted else None}
        table.append(row)
        if chosen is None and cost < turn_chars:
            chosen = row
        if best_total is None or total < best_total["total_cost_chars"]:
            best_total = row
    return {"turn_chars": turn_chars, "today_cost_chars": today, "table": table,
            "chosen": chosen, "best_total": best_total}


def _calibrated(decision) -> float:               # noqa: ANN001 - routing.Decision
    return decision.probability


def _tau_on_calibrate(calib_rows: list[dict]) -> float:
    """The smallest threshold whose wrong routes cost less than one turn ON THESE ROWS.

    The same rule `threshold_sweep` applies, applied to the CALIBRATE block of one fold.
    When no tau on the block gets the realised cost under a turn (which is the normal case
    for D4 -- 286 refusals cost more than one turn however few are wrong) the rule has no
    answer and the policy abstains on everything in that fold, which is reported as tau 1.01
    rather than silently falling back to a tau that was never justified.
    """
    chosen = threshold_sweep(calib_rows, routing.TURN_CHARS)["chosen"]
    return 1.01 if chosen is None else float(chosen["threshold"])


def held_out_policy(rows: list[dict]) -> dict:
    """The abstain policy scored with each row's OWN fold threshold.

    Every number here is out of sample twice over: the head and the calibration map were
    fitted on the fold's train block, and the threshold on its calibrate block, while the
    row itself is in the test block.  This is the policy a consumer would actually get, so
    it is the one the report quotes; `threshold_sweep` over the pooled test rows stays
    beside it as the in-sample CURVE, labelled as such, because the shape of the curve is
    what tells a reader whether the chosen point is on a cliff.
    """
    if not rows:
        return {"n": 0}
    taus = sorted({r["fold_tau"] for r in rows})
    acted = [r for r in rows if r["p"] >= r["fold_tau"]]
    wrong = [r for r in acted if not r["correct"]]
    abstained = [r for r in rows if r["p"] < r["fold_tau"]]
    cost = routing.realised_cost([r["contract_chars"] for r in wrong])
    total = cost + sum(routing.bounded_delivery(r["contract_chars"]) for r in abstained)
    today = sum(routing.bounded_delivery(r["contract_chars"]) for r in rows)
    return {"n": len(rows), "taus_by_fold": taus,
            "tau_median": statistics.median([r["fold_tau"] for r in rows]),
            "acted": len(acted), "abstained": len(abstained),
            "abstain_rate": round(len(abstained) / len(rows), 4),
            "wrong": len(wrong),
            "precision_when_acting": (round((len(acted) - len(wrong)) / len(acted), 4)
                                      if acted else None),
            "realised_cost_chars": cost, "turn_chars": routing.TURN_CHARS,
            "realised_cost_under_one_turn": cost < routing.TURN_CHARS,
            "total_cost_chars": total, "today_cost_chars": today,
            "saved_against_today": today - total}


def mcnemar(a_rows: list[dict], b_rows: list[dict], a_name: str, b_name: str) -> dict:
    """A paired comparison of two feature sets on the same rows, with its own counts.

    Seventeen rows of difference on 540 is not a win unless the pairing says so, so
    the exact two-sided McNemar binomial is printed beside the two accuracies rather
    than left for a reader to assume.
    """
    a = {r["id"]: r["correct"] for r in a_rows}
    b = {r["id"]: r["correct"] for r in b_rows}
    shared = sorted(set(a) & set(b))
    only_a = sum(1 for i in shared if a[i] and not b[i])
    only_b = sum(1 for i in shared if b[i] and not a[i])
    n = only_a + only_b
    if n == 0:
        return {"a": a_name, "b": b_name, "n_paired": len(shared), "discordant": 0, "p": 1.0}
    high = max(only_a, only_b)
    tail = sum(math.comb(n, k) for k in range(high, n + 1))
    p = min(1.0, 2.0 * tail / (2 ** n))
    return {"a": a_name, "b": b_name, "n_paired": len(shared),
            "a_only_right": only_a, "b_only_right": only_b, "discordant": n,
            "p_two_sided_exact": round(p, 5)}


def per_class(rows: list[dict]) -> list[dict]:
    out = []
    labels = collections.Counter(r["label"] for r in rows)
    for label, n in labels.most_common():
        mine = [r for r in rows if r["label"] == label]
        right = sum(1 for r in mine if r["correct"])
        out.append({"label": label, "n": n, "correct": right,
                    "recall": round(right / n, 4),
                    "mean_p": round(statistics.fmean(r["p"] for r in mine), 4)})
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", default=str(HERE / "labels.json"))
    parser.add_argument("--out", default="/tmp/jev-routing/calibration")
    parser.add_argument("--costs", default="/tmp/jev-routing/costs.json")
    parser.add_argument("--seed", type=int, default=20261002)
    parser.add_argument("--folds", type=int, default=5)
    args = parser.parse_args()

    data = json.loads(Path(args.labels).read_text())
    costs = contract_chars(Path(args.costs))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report: dict = {"seed": args.seed, "folds": args.folds,
                    "declared_pairs": len(routing.ROUTE_OPTIONS),
                    "refusal_kinds": list(routing.RESOLVER_OPTIONS),
                    "options_fit_one_choice": routing.options_fit_one_choice(),
                    "turn_chars": routing.TURN_CHARS}

    # --- D1 -----------------------------------------------------------------
    d1_rows = data["d1"]
    report["d1"] = {"n_labelled": len(d1_rows), "n_excluded": len(data["d1_excluded"]),
                    "distinct_labels": len({r["label"] for r in d1_rows}),
                    "by_feature_set": {}}
    best = None
    all_rows: dict[str, list[dict]] = {}
    for feature_set in routing.FEATURE_SETS:
        result = run_d1(d1_rows, seed=args.seed, folds=args.folds,
                        feature_set=feature_set, costs=costs)
        all_rows[feature_set] = result["rows"]
        summary = {"accuracy": result["accuracy"],
                   "reliability": reliability(result["rows"]),
                   "sweep_in_sample": threshold_sweep(result["rows"], routing.TURN_CHARS),
                   "sweep_held_out": held_out_policy(result["rows"]),
                   "folds": result["folds"],
                   "latency_ms": _latency(result["rows"]),
                   "state_chars": _chars(result["rows"])}
        report["d1"]["by_feature_set"][feature_set] = summary
        (out / ("d1_rows_%s.jsonl" % feature_set)).write_text(
            "\n".join(json.dumps(r, sort_keys=True) for r in result["rows"]) + "\n")
        if best is None or summary["accuracy"]["accuracy"] > best[1]["accuracy"]["accuracy"]:
            best = (feature_set, summary, result)
    report["d1"]["best_feature_set"] = best[0]
    report["d1"]["per_class"] = per_class(best[2]["rows"])
    report["d1"]["paired"] = [
        mcnemar(all_rows["homes"], all_rows["names"], "homes", "names"),
        mcnemar(all_rows["homes"], all_rows["noguard"], "homes", "noguard"),
        mcnemar(all_rows["homes"], all_rows["homes+shapes"], "homes", "homes+shapes"),
    ]
    majority = collections.Counter(r["label"] for r in d1_rows).most_common(1)[0]
    report["d1"]["baselines"] = {
        "majority_label": majority[0], "majority_n": majority[1],
        "majority_accuracy": round(majority[1] / len(d1_rows), 4),
        "tie_probability_per_option": round(1.0 / len(routing.ROUTE_OPTIONS), 6)}

    # --- D4 -----------------------------------------------------------------
    d4_rows = data["d4"]
    result = run_d4(d4_rows, seed=args.seed, folds=args.folds, costs=costs)
    live_right = sum(1 for r in result["rows"] if r["live_substring_says"] == r["label"])
    live_silent = sum(1 for r in result["rows"] if r["live_substring_says"] == "<no kind>")
    majority4 = collections.Counter(r["label"] for r in d4_rows).most_common(1)[0]
    report["d4"] = {
        "n_labelled": len(d4_rows), "n_excluded": len(data["d4_excluded"]),
        "excluded_classes": dict(collections.Counter(
            r.get("error_class") or "(none)" for r in data["d4_excluded"])),
        "accuracy": result["accuracy"], "folds": result["folds"],
        "reliability": reliability(result["rows"]),
        "sweep_in_sample": threshold_sweep(result["rows"], routing.TURN_CHARS),
        "sweep_held_out": held_out_policy(result["rows"]),
        "per_class": per_class(result["rows"]),
        "latency_ms": _latency(result["rows"]), "state_chars": _chars(result["rows"]),
        "baselines": {"majority_label": majority4[0],
                      "majority_accuracy": round(majority4[1] / len(d4_rows), 4),
                      "live_substring_accuracy": round(live_right / len(result["rows"]), 4),
                      "live_substring_correct": live_right,
                      "live_substring_no_kind": live_silent,
                      "live_substring_n": len(result["rows"])}}
    (out / "d4_rows.jsonl").write_text(
        "\n".join(json.dumps(r, sort_keys=True) for r in result["rows"]) + "\n")

    # --- what the system delivers today, to decide the same thing -----------
    report["today"] = {
        "operating_brief_chars": routing.TURN_CHARS,
        "contract_chars_total": sum(costs.values()),
        "contract_chars_median": int(statistics.median(costs.values())),
        "contract_chars_max": max(costs.values()),
        "contract_chars_max_operation": max(costs, key=lambda k: costs[k]),
        "operations": len(costs)}
    (out / "report.json").write_text(json.dumps(report, indent=1, sort_keys=True))
    _print(report)
    print("written", out / "report.json")
    return 0


def _latency(rows: list[dict]) -> dict:
    values = sorted(r["latency_ms"] for r in rows)
    return {"n": len(values), "median_ms": round(statistics.median(values), 4),
            "mean_ms": round(statistics.fmean(values), 4),
            "p95_ms": round(values[int(0.95 * (len(values) - 1))], 4),
            "max_ms": round(values[-1], 4)}


def _chars(rows: list[dict]) -> dict:
    values = sorted(r["state_chars"] for r in rows)
    return {"median": int(statistics.median(values)), "mean": int(statistics.fmean(values)),
            "p95": values[int(0.95 * (len(values) - 1))], "max": values[-1]}


def _print(report: dict) -> None:
    print("D1 route --- %d labelled rows, %d excluded, %d distinct labels of %d declared pairs"
          % (report["d1"]["n_labelled"], report["d1"]["n_excluded"],
             report["d1"]["distinct_labels"], report["declared_pairs"]))
    for name, summary in report["d1"]["by_feature_set"].items():
        acc = summary["accuracy"]
        chosen = summary["sweep_in_sample"]["chosen"]
        held = summary["sweep_held_out"]
        print("  %-8s accuracy %s (%d/%d)  ECE %s  median %s ms  state %d chars"
              % (name, acc["accuracy"], acc["correct"], acc["n"],
                 summary["reliability"]["ece"], summary["latency_ms"]["median_ms"],
                 summary["state_chars"]["median"]))
        print("           HELD OUT (tau per fold from its calibrate block %s): acts on %d, "
              "abstains %.1f%%, %d wrong, precision %s, %d chars paid, under one turn %s"
              % (held["taus_by_fold"], held["acted"], 100 * held["abstain_rate"],
                 held["wrong"], held["precision_when_acting"],
                 held["realised_cost_chars"], held["realised_cost_under_one_turn"]))
        if chosen:
            print("           in-sample curve only, NOT a policy: cost<one-turn first at "
                  "p>=%.2f on the pooled test rows (acts %d, abstains %.1f%%, %d wrong, "
                  "%d chars)"
                  % (chosen["threshold"], chosen["acted"], 100 * chosen["abstain_rate"],
                     chosen["wrong"], chosen["realised_cost_chars"]))
    print("  baselines:", report["d1"]["baselines"])
    for pair in report["d1"]["paired"]:
        print("  paired %s vs %s: %d vs %d discordant of %d, exact two-sided p=%s"
              % (pair["a"], pair["b"], pair.get("a_only_right", 0), pair.get("b_only_right", 0),
                 pair["n_paired"], pair.get("p_two_sided_exact")))
    print("D4 classify --- %d labelled rows, %d excluded %s"
          % (report["d4"]["n_labelled"], report["d4"]["n_excluded"],
             report["d4"]["excluded_classes"]))
    print("  accuracy", report["d4"]["accuracy"], "ECE", report["d4"]["reliability"]["ece"])
    print("  baselines:", report["d4"]["baselines"])
    held = report["d4"]["sweep_held_out"]
    print("  HELD OUT (tau per fold from its calibrate block %s): acts on %d, abstains "
          "%.1f%%, %d wrong, precision %s, %d chars paid, under one turn %s"
          % (held["taus_by_fold"], held["acted"], 100 * held["abstain_rate"], held["wrong"],
             held["precision_when_acting"], held["realised_cost_chars"],
             held["realised_cost_under_one_turn"]))
    chosen = report["d4"]["sweep_in_sample"]["chosen"]
    if chosen:
        print("  in-sample curve only, NOT a policy: cost<one-turn first at p>=%.2f (acts "
              "%d, abstains %.1f%%, %d wrong, %d chars)"
              % (chosen["threshold"], chosen["acted"], 100 * chosen["abstain_rate"],
                 chosen["wrong"], chosen["realised_cost_chars"]))
    else:
        print("  NO threshold keeps the realised cost under one turn: 286 refusals cost "
              "more than one turn however few are wrong, so the total rule is the one "
              "that measures anything here.")
    best = report["d4"]["sweep_in_sample"]["best_total"]
    print("  cheapest point on the in-sample curve at p>=%.2f: total %d chars against %d the "
          "live path pays unconditionally (saves %d), acts on %d, abstains %.1f%%, %d wrong"
          % (best["threshold"], best["total_cost_chars"],
             report["d4"]["sweep_in_sample"]["today_cost_chars"], best["saved_against_today"],
             best["acted"], 100 * best["abstain_rate"], best["wrong"]))
    print("  held-out whole-policy cost: total %d chars against %d today (saves %d)"
          % (held["total_cost_chars"], held["today_cost_chars"], held["saved_against_today"]))
    print("today, to decide the same thing:", report["today"])


if __name__ == "__main__":
    raise SystemExit(main())
