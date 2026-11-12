"""Every figure the synth-dispatch-jev report quotes, printed from the banked file.

    scripts/laplace-python tools/writing_verbs/synth_figures.py

Beside each number, the expression that derives it, so a reader can check the report
against the deposit without trusting the prose -- the discipline HARNESS.md's
`report_figures.py` sets for the oracle's own numbers.
"""
from __future__ import annotations

import json
from pathlib import Path

E = Path("/home/phujck/VScodeProjects/laplace/evidence/WRITING_RECONCILIATION_2026-10-02/"
         "wave1/synth-dispatch-jev")
J = Path("/home/phujck/VScodeProjects/laplace/evidence/WRITING_RECONCILIATION_2026-10-02/"
         "wave1/jev-routing")


def show(expression: str, value) -> None:
    print("  %-72s %s" % (expression, value))


def main() -> int:
    print("PARITY")
    for name in ("parity-shipped", "parity-shipped-run2", "parity-shipped-run3"):
        path = E / name / "parity.json"
        if not path.exists():
            continue
        p = json.loads(path.read_text())
        print(" ", name)
        for key in ("new", "old", "rows", "parity", "rows_unallowed",
                    "rows_with_any_difference", "difference_by_kind", "seconds",
                    "by_door", "by_source", "bytes_divergent_paths_total",
                    "bytes_divergent_paths", "outcome_classes_old",
                    "recorded_outcome_agreement", "skipped_operations", "netcache_mode"):
            if key in p:
                show("%s['%s']" % (name, key), p[key])
        show("%s['payload_less_skipped']['by_source']" % name,
             (p.get("payload_less_skipped") or {}).get("by_source"))

    print("ALPHABET")
    a = json.loads((E / "alphabet.json").read_text())
    for key in ("routes", "routes_door_both", "routes_door_shim", "pairs_in_routes",
                "pairs_door_both", "pairs_shim_only", "advisor_options",
                "grammar_declared_pairs", "mapping_pairs", "mapping_rows",
                "all_three_equal", "advisor_minus_dispatch", "dispatch_minus_advisor",
                "dispatch_minus_grammar", "grammar_minus_dispatch", "alphabet_source"):
        show("alphabet.json['%s']" % key, a[key])

    print("CALIBRATION, merged alphabet")
    c = json.loads((E / "calibration" / "report.json").read_text())
    show("report['declared_pairs']", c["declared_pairs"])
    show("report['d1']['n_labelled'] / n_excluded", (c["d1"]["n_labelled"],
                                                     c["d1"]["n_excluded"]))
    show("report['d1']['best_feature_set']", c["d1"]["best_feature_set"])
    for name, summary in c["d1"]["by_feature_set"].items():
        show("d1[%s] accuracy" % name, summary["accuracy"])
        show("d1[%s] ECE" % name, summary["reliability"]["ece"])
        held = summary["sweep_held_out"]
        show("d1[%s] sweep_held_out" % name,
             {k: held[k] for k in ("taus_by_fold", "acted", "abstained", "abstain_rate",
                                   "wrong", "precision_when_acting", "realised_cost_chars",
                                   "realised_cost_under_one_turn", "total_cost_chars",
                                   "today_cost_chars", "saved_against_today")})
        chosen = summary["sweep_in_sample"]["chosen"]
        show("d1[%s] sweep_in_sample['chosen']" % name,
             None if chosen is None else {k: chosen[k] for k in
                                          ("threshold", "acted", "abstain_rate", "wrong",
                                           "precision_when_acting", "realised_cost_chars")})
    for pair in c["d1"]["paired"]:
        show("d1 paired %s vs %s" % (pair["a"], pair["b"]),
             {k: pair.get(k) for k in ("a_only_right", "b_only_right", "n_paired",
                                       "p_two_sided_exact")})
    show("d1 baselines", c["d1"]["baselines"])
    show("d4 accuracy", c["d4"]["accuracy"])
    show("d4 baselines", c["d4"]["baselines"])
    held4 = c["d4"]["sweep_held_out"]
    show("d4 sweep_held_out", {k: held4[k] for k in
                               ("taus_by_fold", "acted", "abstained", "abstain_rate", "wrong",
                                "precision_when_acting", "realised_cost_chars",
                                "realised_cost_under_one_turn", "total_cost_chars",
                                "today_cost_chars", "saved_against_today")})
    show("routing.TURN_CHARS (report['turn_chars'])", c["turn_chars"])

    print("THE ADVISOR ON THE ARRIVAL")
    d = json.loads((E / "arrival-advice" / "arrival_advice.json").read_text())["summary"]
    for key in sorted(d):
        if key != "after_chars_note":
            show("arrival_advice.json['summary']['%s']" % key, d[key])
    old = json.loads((J / "arrival_advice.json").read_text())["summary"]
    show("jev lane's banked run: threshold / acted / right", (old["threshold"], old["acted"],
                                                             old["right_when_acting"]))

    print("THE ARRIVAL ACCEPTANCE (the oracle's own script)")
    s = json.loads((E / "arrival.json").read_text())["score"]
    for key in ("refusals", "help_calls", "help_chars", "out_of_band_facts",
                "door_calls_steady", "chars_sent_steady", "chars_received_steady",
                "chars_total_steady", "owner_code_reads"):
        show("arrival.json['score']['%s']" % key, s.get(key))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
