"""What the pre-call advisor would have said, step by step, on the 2026-10-01 arrival.

A true held-out replay of the one sequence the campaign measures acceptance against:
the head is fitted on every labelled row EXCEPT the arrival ones, and then asked, for
each arrival step in order, which `(verb, concept)` pair that request is.  Nothing is
executed --- the advisor returns a `grammar.Request` or abstains --- so this is what a
caller would have been handed before each call, beside what the step actually was.

    scripts/laplace-python tests/routing_calibration/demo_arrival.py --out <dir>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys

HERE = Path(__file__).resolve().parent
TREE = HERE.parents[1]
sys.path.insert(0, str(TREE / "src"))
sys.path.insert(0, str(HERE))

from laplace.native import routing  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", default="/tmp/jev-routing/labels.json")
    parser.add_argument("--out", required=True)
    # NO DEFAULT THRESHOLD.  Round 2's judge of the jev lane showed that 0.64 was swept
    # over the same pooled test rows whose precision was then reported, and that it does not
    # transfer: the lane's own acceptance rule (wrong routes cost less than one turn) fails
    # on every other split at that tau.  So the demo now CHOOSES tau on rows the arrival is
    # not in -- a calibrate slice of the non-arrival training rows, by the same cost rule
    # `calibrate.threshold_sweep` applies -- and `--threshold` is left as an override for a
    # reader who wants to see a particular point.
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--costs", default=None)
    args = parser.parse_args()

    data = json.loads(Path(args.labels).read_text())
    train = [r for r in data["d1"] if r["source"] != "arrival"]
    test = sorted((r for r in data["d1"] if r["source"] == "arrival"), key=lambda r: r["id"])
    head = routing.PriorDecider(name="prior/homes").fit(
        [(routing.features(routing.RouteState(**r["state"])), r["label"]) for r in train])
    calib = routing.fit_calibration(
        [(routing.route(routing.RouteState(**r["state"]), decider=head,
                        threshold=0.0).raw_probability,
          routing.route(routing.RouteState(**r["state"]), decider=head,
                        threshold=0.0).choice == r["label"])
         for r in train[::3]],
        fitted_on="every third non-arrival row (%d)" % len(train[::3]))

    # ---- the threshold, chosen on rows the arrival is not in -------------------
    import calibrate as _cal                                   # same directory
    costs = _cal.contract_chars(Path(args.costs) if args.costs else None)

    def _contract(row: dict) -> int:
        operation = str(row.get("operation") or "")
        return costs.get(operation.split()[0] if operation else "",
                         routing.CONTRACT_CHARS_MEDIAN)

    tau_block = [r for i, r in enumerate(train) if i % 3 == 1]   # disjoint from train[::3]
    tau_rows = []
    for row in tau_block:
        decision = routing.route(routing.RouteState(**row["state"]), decider=head,
                                 calibration=calib, threshold=0.0)
        tau_rows.append({"p": decision.probability,
                         "correct": decision.choice == row["label"],
                         "contract_chars": _contract(row)})
    tau_held_out = _cal._tau_on_calibrate(tau_rows)
    threshold = tau_held_out if args.threshold is None else float(args.threshold)

    rows = []
    for row in test:
        advice = routing.advise(routing.RouteState(**row["state"]), decider=head,
                               calibration=calib, threshold=threshold, by="demo")
        rows.append({"id": row["id"], "operation": row["operation"], "was": row["label"],
                     "advised": None if advice.request is None else "%s %s" % (
                         advice.request.verb, advice.request.concept),
                     "abstained": advice.abstained,
                     "p": round(advice.decision.probability, 3),
                     "confidence": round(advice.decision.confidence, 3),
                     "correct": (not advice.abstained)
                                and advice.decision.choice == row["label"],
                     "would_have_been_right": advice.decision.choice == row["label"],
                     "state_chars": advice.decision.state_chars,
                     "latency_ms": round(advice.decision.latency_ms, 3),
                     "contract_chars": _contract(row),
                     "bounded_delivery_chars": routing.bounded_delivery(_contract(row)),
                     "said": advice.said})
    acted = [r for r in rows if not r["abstained"]]
    summary = {"trained_on": len(train), "arrival_rows": len(rows),
               "threshold": threshold,
               "threshold_source": ("chosen on %d non-arrival rows the arrival is not in, by "
                                    "the cost rule" % len(tau_block)) if args.threshold is None
                                   else "given on the command line",
               "threshold_held_out": tau_held_out,
               "acted": len(acted), "abstained": len(rows) - len(acted),
               "right_when_acting": sum(1 for r in acted if r["correct"]),
               "precision_when_acting": round(
                   sum(1 for r in acted if r["correct"]) / len(acted), 4) if acted else None,
               "accuracy_if_never_abstaining": round(
                   sum(1 for r in rows if r["would_have_been_right"]) / len(rows), 4),
               "empty_payload_rows": sum(1 for r in test if not r["state"]["payload"]
                                         or list(r["state"]["payload"]) == ["project"]),
               "median_state_chars": int(statistics.median(r["state_chars"] for r in rows)),
               "median_latency_ms": round(statistics.median(r["latency_ms"] for r in rows), 4),
               "today_chars_to_decide_one_step": routing.TURN_CHARS,
               # THE BEFORE/AFTER THE PACKET ASKS FOR, as characters, per decision and
               # summed over the sequence.  `before` is what the live path delivers to the
               # caller to decide ONE of these steps: the operation's exact contract, bounded
               # the way `failure_response` bounds it (writing_tools.py:1260).  `after` is
               # what the advisor is handed to decide the same step: the state text it reads,
               # which is the whole of its input.  Neither number is a saving on its own: a
               # saving needs the caller to stop reading the contract, which only happens on
               # a step the advisor acts on AND is right about, which is why
               # `after_chars_total` adds the before-price back for every abstention and
               # every wrong route.
               "before_chars_per_step_median": int(statistics.median(
                   r["bounded_delivery_chars"] for r in rows)),
               "before_chars_total": sum(r["bounded_delivery_chars"] for r in rows),
               "after_chars_per_step_median": int(statistics.median(
                   r["state_chars"] for r in rows)),
               "after_chars_total": (
                   sum(r["state_chars"] for r in rows)
                   + sum(r["bounded_delivery_chars"] for r in rows if r["abstained"])
                   + sum(r["contract_chars"] for r in rows
                         if not r["abstained"] and not r["correct"])),
               "after_chars_note": ("advisor state for every step, plus the bounded contract "
                                    "for every abstention, plus the FULL contract for every "
                                    "wrong route (curing a wrong route means the exact help "
                                    "call, which is not truncated)")}
    summary["saved_chars_total"] = summary["before_chars_total"] - summary["after_chars_total"]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "arrival_advice.json").write_text(json.dumps(
        {"summary": summary, "rows": rows}, indent=1, sort_keys=True))
    print(json.dumps(summary, indent=1, sort_keys=True))
    for row in rows[:16]:
        print("  %-44s was %-30s advised %-30s p=%.2f%s"
              % (row["id"][:44], row["was"], row["advised"] or "(abstained)", row["p"],
                 "" if row["correct"] or row["abstained"] else "   WRONG"))
    print("written", out / "arrival_advice.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
