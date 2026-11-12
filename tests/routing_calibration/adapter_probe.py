"""Run the two decisions through the MIT System One adapter, on a local provider.

Run it with the SCRATCH VENV's interpreter, never the laplace runtime --- the adapter
and its pydantic are installed under /tmp and nothing is installed into laplace:

    /tmp/jev-routing/venv/bin/python tests/routing_calibration/adapter_probe.py \
        --labels /tmp/jev-routing/labels.json --out /tmp/jev-routing/adapter \
        --d1 15 --d4 40 --seed 20261002

`laplace/__init__.py` imports `yaml`, which the scratch venv does not have, so
`src/laplace/core/grammar.py` is loaded standalone by path.  It is the same bytes the
worktree installs, and the option sets still come from `grammar.VERB_CONCEPTS` and
`grammar.Refusal.KINDS`; this file writes no list of verbs, concepts or kinds.

The criteria descriptions are generated too: the verb glosses are parsed out of
`src/laplace/core/grammar.py`'s own gate block and the script exits non-zero if it does
not recover all nine verbs, so a gloss cannot drift from the module.

One state per request carries up to `--batch` request states and one question per
state, which is the vendor's documented parallel-questions shape (one document, many
independent questions, evaluated in a single pass).  Every provider call's latency,
tokens and cost is recorded.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import random
import re
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TREE = HERE.parents[1]
sys.path.insert(0, str(HERE))


def load_grammar():
    path = TREE / "src" / "laplace" / "core" / "grammar.py"
    spec = importlib.util.spec_from_file_location("grammar_only", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["grammar_only"] = module
    spec.loader.exec_module(module)
    return module


def verb_glosses(path: Path) -> dict[str, str]:
    """The nine gates, parsed from the module's own comment block, never retyped."""
    text = path.read_text(encoding="utf-8")
    found = {}
    for match in re.finditer(r"^#\s{3}(\w+)\s+gate:\s*(.+?)\s*$", text, re.M):
        found.setdefault(match.group(1), match.group(2))
    return found


def state_for(row: dict) -> dict:
    payload = dict(row["state"].get("payload") or {})
    for key in ("operation", "action", "kind", "view", "status", "op", "mode"):
        payload.pop(key, None)
    return {"door": row["state"]["door"], "mode": row["state"]["mode"],
            "target": row["state"]["target"], "payload": payload,
            "path": row["state"].get("path") or ""}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", default="/tmp/jev-routing/labels.json")
    parser.add_argument("--out", default="/tmp/jev-routing/adapter")
    parser.add_argument("--d1", type=int, default=15)
    parser.add_argument("--d4", type=int, default=40)
    parser.add_argument("--batch", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20261002)
    parser.add_argument("--model", default="haiku")
    parser.add_argument("--terse", action="store_true",
                        help="short criteria descriptions; the verbose ones cost "
                             "more characters than the whole operating brief")
    args = parser.parse_args()

    grammar = load_grammar()
    glosses = verb_glosses(TREE / "src" / "laplace" / "core" / "grammar.py")
    missing = [v for v in grammar.VERBS if v not in glosses]
    if missing:
        print("FAILED: no gate gloss parsed for %r; the glosses are generated from "
              "grammar.py's gate block and it has moved" % (missing,))
        return 2

    from system_one_adapter import SystemOneAdapterClient
    from typesafe_sdk import Choice
    from claude_cli_provider import ClaudeCliProvider

    route_labels = ["%s %s" % (v, c) for v, c in sorted(grammar.VERB_CONCEPTS)]
    verbose, terse = {}, {}
    for label in route_labels:
        verb, concept = label.split(" ", 1)
        obj, _, altitude = concept.partition("@")
        kind = grammar.HOME_KINDS[obj]
        verbose[label] = ("%s --- gate: %s. The home acted on is %s (recipe %s) at "
                          "altitude %s." % (verb, glosses[verb], obj, kind.recipe, altitude))
        terse[label] = "%s the %s home, at the %s grain" % (verb, obj, altitude)
    route_criteria = terse if args.terse else verbose
    # The price of enumerating the option set is part of the comparison, because a
    # `choice`'s criteria travel in EVERY request: the vendor's parallel-questions
    # pattern shares the state, not the criteria.
    criteria_cost = {"verbose_chars": sum(len(k) + len(v) for k, v in verbose.items()),
                     "terse_chars": sum(len(k) + len(v) for k, v in terse.items()),
                     "using": "terse" if args.terse else "verbose"}
    resolver_criteria = {
        "identity-stale": "a home the caller named has moved; the cure is its current token",
        "unknown-home": "the home the request addresses is not there at all",
        "state-not-reached": "a third home is not yet in the state this act requires; no fresher "
                             "token can cure it",
        "shape": "the request's own shape is wrong: a missing, unknown or wrongly typed field",
    }

    data = json.loads(Path(args.labels).read_text())
    rng = random.Random(args.seed)
    d1 = data["d1"][:]
    d4 = data["d4"][:]
    rng.shuffle(d1)
    rng.shuffle(d4)
    d1 = d1[: args.d1]
    d4 = d4[: args.d4]

    provider = ClaudeCliProvider(model_name=args.model)
    client = SystemOneAdapterClient(structured_outputs=False,
                                    llm_answer_mode="probabilities",
                                    normalize_probabilities=True,
                                    n_retry_malformed_structure=1)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    results = {"model": args.model, "adapter": "system-one-adapter (MIT), scratch venv /tmp",
               "vendor_key_present": False, "d1": [], "d4": [],
               "n_route_options": len(route_labels),
               "criteria_cost": criteria_cost,
               "n_resolver_options": len(resolver_criteria)}

    def run_batch(rows, criteria, instructions, state_of, question_prefix):
        answers_out = []
        for start in range(0, len(rows), args.batch):
            chunk = rows[start:start + args.batch]
            state = {"requests": [dict(state_of(r), id="r%d" % (i + 1))
                                  for i, r in enumerate(chunk)]}
            questions = {}
            for i, _row in enumerate(chunk):
                questions["%s%d" % (question_prefix, i + 1)] = Choice(
                    instructions=instructions + (" Answer for the request whose id is 'r%d' "
                                                 "in the state, and for no other." % (i + 1)),
                    criteria=criteria)
            started = time.perf_counter()
            try:
                response = client.system_one(state=state, questions=questions, model=provider)
            except Exception as exc:  # noqa: BLE001
                answers_out.extend({"id": r["id"], "label": r["label"], "error": "%s: %s"
                                    % (type(exc).__name__, str(exc)[:300])} for r in chunk)
                continue
            elapsed = (time.perf_counter() - started) * 1000.0
            for i, row in enumerate(chunk):
                answer = response.answers["%s%d" % (question_prefix, i + 1)]
                probabilities = dict(getattr(answer, "probabilities", {}) or {})
                choice = getattr(answer, "choice", None) or (
                    max(probabilities, key=lambda k: probabilities[k]) if probabilities else "")
                top = float(probabilities.get(choice, 0.0))
                answers_out.append({
                    "id": row["id"], "label": row["label"], "choice": choice,
                    "correct": choice == row["label"], "top_probability": round(top, 4),
                    "confidence": round(float(getattr(answer, "confidence", 0.0) or 0.0), 4),
                    "n_nonzero": sum(1 for v in probabilities.values() if v > 0),
                    "request_latency_ms": round(elapsed, 1),
                    "batch": start // args.batch})
        return answers_out

    results["d1"] = run_batch(d1, route_criteria, (
        "Choose the one grammar pair `<verb> <object>@<altitude>` this request is. The verb "
        "is the gate the act must pass before it happens; the object is the home kind being "
        "acted on and the altitude is the grain it is acted on at."), state_for, "route")
    results["d4"] = run_batch(d4, resolver_criteria, (
        "Choose the one refusal kind this refusal is."),
        lambda r: {"refusal": r["error"]}, "kind")

    results["provider_calls"] = provider.calls
    for key in ("d1", "d4"):
        rows = [r for r in results[key] if "choice" in r]
        errors = [r for r in results[key] if "error" in r]
        results[key + "_summary"] = {
            "n": len(results[key]), "answered": len(rows), "errors": len(errors),
            "correct": sum(1 for r in rows if r["correct"]),
            "accuracy": round(sum(1 for r in rows if r["correct"]) / len(rows), 4) if rows else None,
            "mean_top_probability": round(statistics.fmean(r["top_probability"] for r in rows), 4)
            if rows else None,
            "mean_reported_confidence": round(statistics.fmean(r["confidence"] for r in rows), 4)
            if rows else None,
            "first_error": errors[0]["error"] if errors else None}
    if provider.calls:
        latencies = [c["duration_api_ms"] or 0 for c in provider.calls]
        results["provider_summary"] = {
            "calls": len(provider.calls),
            "median_api_ms": statistics.median(latencies),
            "max_api_ms": max(latencies),
            "total_cost_usd": round(sum(c["cost_usd"] or 0 for c in provider.calls), 4),
            "median_prompt_chars": statistics.median(c["prompt_chars"] for c in provider.calls),
            "median_cache_creation_tokens": statistics.median(
                c["cache_creation_input_tokens"] or 0 for c in provider.calls)}
    (out / "adapter.json").write_text(json.dumps(results, indent=1, sort_keys=True))
    print(json.dumps({k: v for k, v in results.items()
                      if k.endswith("_summary") or k in ("model", "n_route_options",
                                                         "n_resolver_options",
                                                         "criteria_cost")},
                     indent=1, sort_keys=True))
    print("written", out / "adapter.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
