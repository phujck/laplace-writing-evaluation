"""Scoped receipt assurance over the public protocol owner, without execution.

Format/version/hash/reference validation belongs to receipts. This module owns
the three retained comparison CLIs' shared evidence preconditions and named
claims. Missing/truncated evidence is UNPROVED, not equality of empty defaults.
Answer, planner decision and exact occurrence claims remain separate; fresh
calibration/upstream occurrence differences need not change an answer. No timer
scrub, arbitrary comparison DSL, source lookup or verification cache exists.
"""
from __future__ import annotations

import math

from .receipts import inspect_dataset_run, verify_run, ReceiptProtocolError


class EvidenceUnproved(ValueError):
    """The requested comparison claim lacks complete retained evidence."""


def _required(value, key, where):
    if not isinstance(value, dict) or key not in value:
        raise EvidenceUnproved(where + ": missing " + key)
    return value[key]


def _count(value, where):
    if type(value) is not int or value < 0:
        raise EvidenceUnproved(where + ": nonnegative integer required")
    return value


def _text(value, where):
    if not isinstance(value, str) or not value:
        raise EvidenceUnproved(where + ": exact nonempty identity required")
    return value


def _digest(value, where):
    text = _text(value, where)
    bare = text.removeprefix("sha256:")
    if len(bare) != 64 or any(char not in "0123456789abcdef" for char in bare):
        raise EvidenceUnproved(where + ": exact SHA256 digest required")
    return "sha256:" + bare


def _stage(run, name):
    # The normalized owner view has already validated unique stage labels.
    found = [row for row in run["dataset"]["receipt"]["stages"] if row["stage"] == name]
    if len(found) != 1:
        raise EvidenceUnproved("Required " + name + " stage is absent")
    return found[0]


def _runs(root):
    verify_run(root)
    datasets = _required(root, "datasets", "root")
    if not isinstance(datasets, dict) or not datasets:
        raise EvidenceUnproved("Exact nonempty dataset coverage required")
    observed = {name: inspect_dataset_run(run) for name, run in datasets.items()}
    for view in observed.values():
        try:
            compiled = _required(_stage(view, "question")["payload"], "compiled", "question task")
            # The owner validates unique compiled/read qids. This is a bounded
            # semantic lookup over this detached observation, not a parser/cache.
            view["declared_tasks"] = {row["spec"]["qid"]: row["spec"] for row in compiled}
        except (EvidenceUnproved, KeyError, TypeError):
            view["declared_tasks"] = {}
    return observed


def _questions(run):
    rows = run["questions"]
    if not rows:
        raise EvidenceUnproved("Exact nonempty question coverage required")
    return {row["qid"]: row for row in rows}  # Owner already refuses duplicate qids.


def _handles(result, where, *, occurrence=False):
    identities = []
    for kind in ("row", "range"):
        rows = _required(result, kind + "_handles", where)
        total = _count(_required(result, kind + "_handles_total", where), where)
        if not isinstance(rows, list) or len(rows) != total:
            raise EvidenceUnproved(where + ": incomplete " + kind + " handle evidence")
        keys = (("row_id", "row_kind", "content_handle", "start", "end", "bytes")
                if kind == "row" else
                ("lens_hash", "component_address", "lo", "hi", "condition_digest", "verdict"))
        seen = set()
        for handle in rows:
            values = [_required(handle, key, where) for key in keys]
            for index, (key, value) in enumerate(zip(keys, values)):
                if key in {"start", "end", "bytes", "lo", "hi"}:
                    _count(value, where + "/" + key)
                else:
                    _text(value, where + "/" + key)
                    if key in {"row_id", "content_handle", "lens_hash", "component_address", "condition_digest"}:
                        values[index] = _digest(value, where + "/" + key)
            if kind == "row" and (handle["end"] < handle["start"]
                    or handle["bytes"] != handle["end"] - handle["start"]):
                raise EvidenceUnproved(where + ": contradictory content interval")
            if kind == "range" and handle["hi"] < handle["lo"]:
                raise EvidenceUnproved(where + ": contradictory rank interval")
            values = tuple(values)
            if occurrence:
                keys_local = ("global_ordinal",) if kind == "row" else ("component",)
                values += tuple(_count(_required(handle, key, where), where) for key in keys_local)
            if values in seen:
                raise EvidenceUnproved(where + ": duplicate represented handle")
            seen.add(values)
        identities.append(sorted(seen))
    return identities


def oracle_agreement_of_question(question):
    """Producer's conditional oracle contract; None means NOT ASSERTED."""
    known = _required(question, "known_answer", question.get("qid", "question"))
    if known is None:
        if question.get("answer_equals_the_known_answer") is not None:
            raise EvidenceUnproved("Oracle agreement asserted without a known answer")
        return None
    agreement = _required(question, "answer_equals_the_known_answer", question["qid"])
    if type(agreement) is not bool:
        raise EvidenceUnproved(question["qid"] + ": present oracle requires an observed boolean agreement")
    return agreement


def _answers(q):
    values = []
    for supply in ("partial", "whole"):
        result = _required(q, supply, q["qid"])
        values.append({key: _required(result, key, q["qid"] + "/" + supply)
                       for key in ("answer", "certificate", "refusal")})
    flat = _required(q, "answer_equals_the_flat_control", q["qid"])
    if flat is not None and type(flat) is not bool:
        raise EvidenceUnproved(q["qid"] + ": invalid flat-control agreement")
    values.extend((flat, oracle_agreement_of_question(q)))
    return values


def _counts(q):
    return [_count(_required(_required(q, supply, q["qid"])["executed"], "rows_admitted",
                             q["qid"] + "/" + supply), q["qid"])
            for supply in ("partial", "whole")]


def _planner(run, q):
    model = run["planner_cost"]
    if model is None:
        raise EvidenceUnproved("Read-consumed planner model is unavailable")
    return {"model": model, "plan": _required(q, "plan", q["qid"])}


def _task_basis(run, q):
    spec = run["declared_tasks"].get(q["qid"])
    if not isinstance(spec, dict):
        raise EvidenceUnproved(q["qid"] + ": exact declared task basis unavailable")
    dataset_id = run["dataset"]["dataset_id"]
    for key in ("dataset_id", "text", "row_kind", "conditions", "operator", "byte_budget"):
        _required(spec, key, "declared task")
    _count(spec["byte_budget"], "declared task byte budget")
    if not isinstance(spec["conditions"], list) or any(not isinstance(c, dict) for c in spec["conditions"]):
        raise EvidenceUnproved(q["qid"] + ": declared condition meaning unavailable")
    _text(_required(spec["operator"], "name", "declared operator"), "operator name")
    if spec["dataset_id"] != dataset_id or _required(q, "text", q["qid"]) != spec["text"]:
        raise EvidenceUnproved(q["qid"] + ": declared/read task identity contradicts")
    # Exact authored task meaning, never record-local encoded/tensor coordinates.
    return {"dataset_id": dataset_id,
            "spec": {key: value for key, value in spec.items()
                     if key not in {"known_answer", "known_answer_source"}}}


def _oracle(run, q):
    # Fixture oracle labels are separate evidence, not the requested task.
    return {key: _required(q, key, q["qid"]) for key in
            ("known_answer", "known_answer_source")}


def _tolerance(run, q):
    values = []
    for supply in ("partial", "whole"):
        value = _required(_required(q, supply, q["qid"]), "tolerance", q["qid"])
        _text(_required(value, "name", "read tolerance"), "tolerance name")
        _text(_required(value, "derivation", "read tolerance"), "tolerance recipe meaning")
        tau = _required(value, "tau", "read tolerance")
        if type(tau) not in (int, float) or (type(tau) is float and math.isnan(tau)) or tau < 0:
            raise EvidenceUnproved(q["qid"] + ": numeric tolerance is unavailable/malformed")
        values.append(value)
    return values


def _occurrence(run, q):
    ingest = _stage(run, "ingest")["payload"]
    digests = _required(ingest, "content_digests", "ingest")
    record = _digest(_required(digests, "record", "content digests"), "record digest")
    primary = run["primary_tree"]
    if primary is None:
        raise EvidenceUnproved("Primary tree basis is unavailable")
    manifest = _digest(_required(primary, "manifest_digest", "primary tree"), "manifest digest")
    return {"dataset_id": run["dataset"]["dataset_id"], "record_digest": record,
            "manifest_digest": manifest,
            "handles": [_handles(_required(q, supply, q["qid"]), q["qid"], occurrence=True)
                        for supply in ("partial", "whole")]}


def _clause(left, right, projection):
    issues = []
    differences = []
    for name in sorted(left):
        try:
            a, b = _questions(left[name]), _questions(right[name])
            if set(a) != set(b):
                raise EvidenceUnproved(name + ": question coverage differs")
            for qid in sorted(a):
                try:
                    av = projection(left[name], a[qid])
                    bv = projection(right[name], b[qid])
                    if av != bv:
                        differences.append(name + "/" + qid)
                except (ReceiptProtocolError, EvidenceUnproved, KeyError, TypeError, AttributeError) as error:
                    issues.append(name + "/" + qid + ": " + str(error))
        except (ReceiptProtocolError, EvidenceUnproved, KeyError, TypeError, AttributeError) as error:
            issues.append(name + ": " + str(error))
    return {"status": "UNPROVED" if issues else "DIFFERENT" if differences else "EQUIVALENT",
            "issues": issues, "differences": differences}


def _join(clauses):
    return ("UNPROVED" if any(c["status"] == "UNPROVED" for c in clauses)
            else "DIFFERENT" if any(c["status"] == "DIFFERENT" for c in clauses)
            else "EQUIVALENT")


def compare_observations(left, right):
    """Retained answer/count/represented-identity claim; other clauses separate."""
    try:
        a, b = _runs(left), _runs(right)
        if set(a) != set(b):
            raise EvidenceUnproved("Dataset coverage differs")
    except (ReceiptProtocolError, EvidenceUnproved, KeyError, TypeError, AttributeError) as error:
        return {"record": "atlas.front-comparison/1", "status": "UNPROVED",
                "issues": [str(error)], "clauses": {}}
    return _compare_normalized(a, b)


def _compare_normalized(a, b):
    try:
        coverage = {}
        for name in sorted(a):
            left, right = _questions(a[name]), _questions(b[name])
            if set(left) != set(right):
                raise EvidenceUnproved(name + ": question coverage differs")
            coverage[name] = sorted(left)
    except (ReceiptProtocolError, EvidenceUnproved, KeyError, TypeError, AttributeError) as error:
        return {"record": "atlas.front-comparison/1", "status": "UNPROVED",
                "issues": [str(error)], "clauses": {}}
    clauses = {
        "task_basis": _clause(a, b, _task_basis),
        "oracle_basis": _clause(a, b, _oracle),
        "tolerance_meaning": _clause(a, b, _tolerance),
        "answers_and_controls": _clause(a, b, lambda _r, q: _answers(q)),
        "admitted_counts": _clause(a, b, lambda _r, q: _counts(q)),
        "represented_identity": _clause(a, b, lambda _r, q:
            [_handles(_required(q, supply, q["qid"]), q["qid"])
             for supply in ("partial", "whole")]),
        "planner_decisions": _clause(a, b, _planner),
        "exact_occurrence": _clause(a, b, _occurrence),
    }
    clauses["oracle_basis"]["not_asserted"] = {
        arm: {name: [qid for qid, question in _questions(view).items()
                     if "known_answer" in question and question["known_answer"] is None]
              for name, view in observations.items()}
        for arm, observations in (("left", a), ("right", b))}
    clauses["oracle_basis"]["scope"] = "Retained oracle labels; identical NOT_ASSERTED states are not successful scientific oracle checks."
    status = _join([clauses[key] for key in
        ("answers_and_controls", "admitted_counts", "represented_identity")])
    if clauses["task_basis"]["status"] != "EQUIVALENT":
        status = "UNPROVED"
    return {"record": "atlas.front-comparison/1", "status": status,
            "issues": [] if clauses["task_basis"]["status"] == "EQUIVALENT" else
                ["Task/scope basis is unavailable or differs; equal outputs do not prove a same-task comparison."],
            "claim": "same-task retained outputs, admitted counts and complete represented handle identity",
            "coverage": coverage,
            "clauses": clauses,
            "limits": "Planner-decision and exact-occurrence results are independent clauses; represented ranges do not prove every underlying row identity or scientific validity."}


def _record_digest(run, *, warm):
    payload = _stage(run, "ingest")["payload"]
    holder = _required(payload, "open_receipt", "warm ingest") if warm else payload
    digest = _required(holder, "digests" if warm else "content_digests", "record basis")
    return _digest(_required(digest, "record", "record digest"), "record digest")


def compare_cold_warm(left, right):
    """The retained J4 claim includes planner decisions, not fresh occurrence IDs."""
    result = compare_observations(left, right)
    if result["clauses"]:
        result["status"] = _join([result["clauses"][key] for key in
            ("answers_and_controls", "admitted_counts", "represented_identity", "planner_decisions", "tolerance_meaning")])
        if result["clauses"]["task_basis"]["status"] != "EQUIVALENT":
            result["status"] = "UNPROVED"
        result["claim"] = "same-task retained answers/counts/represented identity and planner/tolerance-decision equivalence"
    return result


def compare_ablation(on, off, on_warm, off_warm):
    """P1's explicit four-arm claim; incomplete identity/digest evidence refuses."""
    try:
        arms = [_runs(root) for root in (on, off, on_warm, off_warm)]
        if any(set(arm) != set(arms[0]) for arm in arms[1:]):
            raise EvidenceUnproved("Four-arm dataset coverage differs")
        # These are actual coverage/declaration preconditions, not optional prose.
        for name in arms[0]:
            qids = [set(_questions(arm[name])) for arm in arms]
            if any(ids != qids[0] for ids in qids[1:]):
                raise EvidenceUnproved(name + ": four-arm question coverage differs")
            for arm in arms:
                _digest(_required(_stage(arm[name], "declare")["payload"],
                                "declaration_hash", "declare"), "declaration hash")
        source_basis = {name: {
            "declaration_hashes": [_digest(_stage(arm[name], "declare")["payload"]["declaration_hash"], "declaration hash") for arm in arms],
            "record_digests": [_record_digest(arm[name], warm=index >= 2) for index, arm in enumerate(arms)]}
            for name in arms[0]}
        digests = {name: {"on": row["record_digests"][0] == row["record_digests"][2],
                         "off": row["record_digests"][1] == row["record_digests"][3]}
                   for name, row in source_basis.items()}
        ingest_counts = {name: {
            field: [_count(_required(_stage(arm[name], "ingest")["executed"], field, "ingest"), "ingest/" + field) for arm in arms]
            for field in ("rows", "relations")}
            for name in arms[0]}
    except (ReceiptProtocolError, EvidenceUnproved, KeyError, TypeError, AttributeError) as error:
        return {"record": "atlas.p1.ablation/2", "status": "UNPROVED", "issues": [str(error)]}
    # Each dataset was normalized once above; pair claims reuse only that
    # detached per-call semantic snapshot, never a persistent verification cache.
    pairs = {"cold_on_off": _compare_normalized(arms[0], arms[1]),
             "warm_on_off": _compare_normalized(arms[2], arms[3]),
             "on_warm_cold": _compare_normalized(arms[0], arms[2]),
             "off_warm_cold": _compare_normalized(arms[1], arms[3])}
    statuses = [{"status": item["status"]} for item in pairs.values()]
    statuses.append({"status": "EQUIVALENT" if all(all(row.values()) for row in digests.values()) else "DIFFERENT"})
    statuses.append({"status": "EQUIVALENT" if all(len(set(values)) == 1
        for row in ingest_counts.values() for values in row.values()) else "DIFFERENT"})
    return {"record": "atlas.p1.ablation/2", "status": _join(statuses),
            "claim": "four-arm retained answer/admission/ingest-count/represented-identity equivalence and within-arm cold/warm record digest consistency",
            "comparisons": pairs, "warm_equals_cold_record": digests,
            "source_basis": source_basis, "ingest_counts": ingest_counts,
            "limits": "Declaration hashes are required evidence, not equated across intentionally different declarations. This is not universal system or scientific equivalence."}
