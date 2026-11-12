"""coverage_cli.py - run the F.23 instrument over the real benchmarks and write the measurement.

    scripts/laplace-python -m atlas.bench.coverage_cli --out <path.json>

Every number in this packet's report comes from this one command, RUN WITH NO OTHER ARGUMENT: the
defaults below ARE the sample the measurement was taken at (``SAMPLES``), so the command a report
states and the numbers it quotes are the same run. F.23 asks for an instrument that is "fully
deterministic and re-runnable"; that is checked here rather than asserted:

  * the report carries its own ``run`` block - the argv it was called with, the resolved sample
    sizes, the files it wrote and a ``measurement_digest`` over everything EXCEPT that block, so
    two runs of the stated command produce the same digest and a banked measurement names the
    command that produced it (``--verify-digest <file>`` recomputes it);
  * the per-(question, read, budget) rows are DEPOSITED beside the summaries, one file per
    benchmark, each row carrying its supplied fingerprint and its missing-span list, so which
    question failed and on which gold span is in the repository and not only in this process;
  * ``--recompute-audit <rows file>`` rebuilds the identity audit from those deposited
    fingerprints alone, with no corpus and no re-scoring, which is the check that the audit in the
    report is a property of the deposit rather than of this run.

It:

  1. reproduces ``reconstruction/evaluation_scoring.evidence_scores``'s reach on MultiHop-RAG, to
     the digit, against the original function loaded from its own file, and re-counts the 6,084
     gold items and the 0 unmapped;
  2. reproduces ``qasper_benchmark.evidence_metrics``'s 'all' metric (the ``complete`` field) over
     the real 32- and 256-question gold banks, against the function's own source text lifted out of
     the file and hashed, and shows the span-containment predicate agreeing with it row by row;
  3. exhibits the named fix - a context row with no ``document_ids`` now RAISES;
  4. re-derives the 360 burnt question ids and shows a claim on them refused;
  5. scores a GRADED read and a FLAT read (and the summary-shaped control) on the same questions of
     both benchmarks at the primary and secondary byte budgets, with the identity audit between
     every pair; and
  6. runs the two planted violations - fuzzy text-match standing in for containment, and an arm
     that is its control relabelled.

It calls no model, computes no embedding and touches no GPU. It writes the measurement and, beside
it, one rows file per benchmark - and nothing else.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import statistics
import sys
import time
from pathlib import Path

from . import evidence_coverage as ec
from . import gold_spans as gs
from . import reference_reads as rr

#: The sample this measurement is taken at. These are the CLI's defaults, which is the whole
#: point: a report that states ``coverage_cli --out <path>`` and quotes a number taken at some
#: other sample is not re-runnable, and F.23's instrument has to be. Like ``evidence_coverage
#: .DECLARED``, every one of them carries where it comes from; none is a bare literal in the code.
SAMPLES: dict[str, dict] = {
    "measurement.multihop_parity_sample": {
        "value": 500,
        "kind": "DECLARED",
        "provenance": "the MultiHop-RAG reproduction is exhaustive where it counts (all 6,084 gold "
        "items are re-counted and mapped) and randomized in the context rows it compares; 500 of "
        "the corpus' questions x 24 context rows = 12,000 (context row, gold item) comparisons "
        "against the original function, at ~25 s. It is the size of a comparison sample, not a "
        "measured quantity: raising it can only find more disagreements, never fewer.",
        "expiry": "none - it is stated here so a banked parity result names the sample it was "
        "observed at; raise it if a disagreement is ever found",
    },
    "measurement.longmem_questions": {
        "value": 60,
        "kind": "DERIVED",
        "provenance": "the same n the primary budget was derived over (DECLARED row "
        "coverage.primary_budget_bytes: 'measured max 3947 bytes over the 60 burnt non-abstention "
        "LongMemEval_s questions'), so the instrument is exercised at the sample size the budget "
        "was set from. At n = 60 the sizing floor ceil(0.10/0.75 * 60) = 8 exceeds the statistical "
        "floor 6, so the identity audit's binding floor is the derived one and not the constant.",
        "expiry": "replaced by F.20's 107-question development stratum the moment it is drawn at "
        "the preregistration; these questions are an instrument exercise, never the claim",
    },
    "measurement.qasper_read_questions": {
        "value": 32,
        "kind": "DERIVED",
        "provenance": "every question of the qasper_development_v2 bank (all 32 of them) - not a "
        "chosen sample size but the size of the bank, re-derived from its own queries.json",
        "expiry": "none",
    },
    "measurement.qasper_parity_k_grid": {
        "value": (1, 3, 5, 10, 20),
        "kind": "DECLARED",
        "provenance": "the k grid the established qasper_benchmark 'all' metric is reproduced at; "
        "it spans the selection sizes the prior work reported, so the reproduction is not tested "
        "at one convenient k",
        "expiry": "frozen with the preregistration",
    },
}


def sample(key: str):
    """The value of a declared sample size. The only way a sample count enters this module."""
    try:
        return SAMPLES[key]["value"]
    except KeyError:  # pragma: no cover - a typo in a key is a programming error
        raise KeyError(f"undeclared sample {key!r}: add a row to SAMPLES with provenance") from None


def _digests() -> dict:
    return {
        "evaluation_scoring.py": gs.file_digest(gs.RECONSTRUCTION / "evaluation_scoring.py"),
        "qasper_benchmark.py": gs.file_digest(gs.EXTENSION / "qasper_benchmark.py"),
        "qasper_data.py": gs.file_digest(gs.EXTENSION / "qasper_data.py"),
        "longmem_data.py": gs.file_digest(gs.EXTENSION / "longmem_data.py"),
        "longmem_split_manifest.json": gs.file_digest(gs.EXTENSION / "reviews" / "longmem_split_manifest.json"),
        "multihoprag/corpus.json": gs.file_digest(gs.MULTIHOP / "corpus.json"),
        "multihoprag/MultiHopRAG.json": gs.file_digest(gs.MULTIHOP / "MultiHopRAG.json"),
    }


def lift_evidence_metrics():
    """Lift ``evidence_metrics`` out of ``qasper_benchmark.py`` by its own source text.

    The file imports torch and the whole extension package at module scope, so importing it here
    would drag the GPU stack into an offline scorer. The function is pure and stdlib-only, so its
    source lines are extracted, hashed and executed in an isolated namespace: the reproduction is
    then against the FILE, not against a transcription of it.
    """
    path = gs.EXTENSION / "qasper_benchmark.py"
    lines = path.read_text().splitlines(keepends=True)
    start = next(i for i, line in enumerate(lines) if line.startswith("def evidence_metrics("))
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("def "))
    source = "".join(lines[start:end])
    namespace: dict = {}
    exec(compile(source, str(path), "exec"), namespace)
    return namespace["evidence_metrics"], {
        "file": str(path.relative_to(gs.REPO_ROOT)),
        "lines": f"{start + 1}-{end}",
        "source_sha256": "sha256:" + hashlib.sha256(source.encode()).hexdigest(),
    }


# --------------------------------------------------------------------------------------------
# (1) MultiHop-RAG reach
# --------------------------------------------------------------------------------------------


def multihop_reach(sample: int) -> dict:
    original = gs._load_prior_module(gs.RECONSTRUCTION / "evaluation_scoring.py", "_prior_evaluation_scoring")
    corpus, questions = gs.load_multihop()
    documents = gs.multihop_documents(corpus)
    index = gs.multihop_corpus_index(corpus)

    gold_items = sum(len(q["evidence_list"]) for q in questions)
    unmapped = sum(
        1
        for q in questions
        for item in q["evidence_list"]
        if not (index.get(("url", item.get("url"))) or index.get(("title", item.get("title"))))
    )

    disagreements = []
    compared = 0
    for position, question in enumerate(questions[:sample]):
        rotation = int(hashlib.sha256(question["query"].encode()).hexdigest(), 16) % len(corpus)
        contexts = []
        for j in range(24):
            doc_id = (rotation + j * 7) % len(corpus)
            contexts.append({"document_ids": [doc_id], "text": corpus[doc_id]["body"][:400]})
        mine = ec.reach_scores(contexts, question["evidence_list"], documents)
        theirs = original.evidence_scores(contexts, question["evidence_list"], documents)
        compared += 1
        if mine != theirs:
            disagreements.append({"position": position, "mine": mine, "theirs": theirs})

    empty_mine = ec.reach_scores([], [], documents)
    empty_theirs = original.evidence_scores([], [], documents)

    raised = None
    try:
        ec.reach_scores([{"text": "no sources declared"}], questions[0]["evidence_list"], documents)
    except ec.MissingDocumentIds as error:
        raised = str(error)
    silent = original.evidence_scores(
        [{"text": "no sources declared"}], questions[0]["evidence_list"], documents
    )

    return {
        "questions": len(questions),
        "corpus_documents": len(corpus),
        "gold_items": gold_items,
        "unmapped_gold_items": unmapped,
        "all_gold_items_map_to_a_corpus_document": unmapped == 0,
        "parity_questions_compared": compared,
        "parity_disagreements": disagreements,
        "parity_exact": not disagreements,
        "empty_evidence_agrees": empty_mine == empty_theirs,
        "named_fix_evaluation_scoring_py_59": {
            "original_silently_returns": silent,
            "lifted_scorer_raises": raised,
            "fix_active": raised is not None,
        },
    }


# --------------------------------------------------------------------------------------------
# (2) QASPER 'all' metric, in id space and in span space
# --------------------------------------------------------------------------------------------


def _qasper_papers_for(bank_question_ids: set[str]) -> dict[str, tuple[str, dict]]:
    """Map each wanted question id to (paper_id, paper), over all three raw splits."""
    found: dict[str, tuple[str, dict]] = {}
    for split in ("train", "dev", "test"):
        raw = gs.load_qasper_split(split)
        for paper_id, paper in raw.items():
            for question in paper["qas"]:
                if question["question_id"] in bank_question_ids:
                    found[question["question_id"]] = (paper_id, paper)
    return found


def qasper_parity(bank_dirs: list[Path], k_grid: tuple[int, ...]) -> dict:
    original, lift = lift_evidence_metrics()
    banks = {}
    for bank in bank_dirs:
        banks[bank.name] = json.loads((bank / "gold.json").read_text())
    wanted = {qid for gold in banks.values() for qid in gold}
    papers = _qasper_papers_for(wanted)
    missing = sorted(wanted - set(papers))
    if missing:
        raise ec.CoverageError(f"{len(missing)} bank question ids are in no raw split: {missing[:3]}")

    images: dict[str, gs.ContainerImage] = {}
    rows = []
    disagreements = []
    repair = {"legacy_unresolved": 0, "repaired_unresolved": 0, "requirements": 0, "rescued": 0}
    for bank_name, gold_bank in banks.items():
        for qid in sorted(gold_bank):
            paper_id, paper = papers[qid]
            if paper_id not in images:
                images[paper_id] = gs.qasper_paper_image(paper_id, paper)
            image = images[paper_id]
            legacy = gs.qasper_gold(paper_id, paper, image, [qid], repaired=False)[qid]
            repaired = gs.qasper_gold(paper_id, paper, image, [qid], repaired=True)[qid]
            for alternative in legacy.alternatives:
                repair["requirements"] += len(alternative.requirements)
                repair["legacy_unresolved"] += sum(not r.resolved for r in alternative.requirements)
            for alternative in repaired.alternatives:
                repair["repaired_unresolved"] += sum(not r.resolved for r in alternative.requirements)

            unit_ids = [u.unit_id for u in image.units if u.kind != "section_header"]
            by_id = image.by_unit_id
            rotation = int(hashlib.sha256(qid.encode()).hexdigest(), 16) % max(1, len(unit_ids))
            ordered = unit_ids[rotation:] + unit_ids[:rotation]
            unbounded = image.nbytes + len(unit_ids) * rr.SEPARATOR_COST + 1
            for k in k_grid:
                selected = ordered[:k]
                units = tuple(
                    ec.SuppliedUnit(
                        unit_id=uid,
                        grade=0,
                        opened=True,
                        spans=(by_id[uid].span,),
                        bytes_charged=by_id[uid].span.nbytes + rr.SEPARATOR_COST,
                    )
                    for uid in selected
                )
                theirs = original(selected, json.loads(json.dumps(gold_bank[qid]["annotations"])))
                mine_id_space = ec.qasper_all_metric(selected, gold_bank[qid]["annotations"])
                mine_span = ec.complete_evidence(legacy, units, unbounded)
                their_complete = theirs.get("complete")
                span_complete = mine_span.complete if mine_span.eligible else None
                agree = (their_complete == span_complete) and (
                    mine_id_space.get("complete") == their_complete
                )
                rows.append(
                    {
                        "bank": bank_name,
                        "question_id": qid,
                        "k": k,
                        "eligible": theirs["eligible"],
                        "established_all": their_complete,
                        "span_containment_all": span_complete,
                        "agree": agree,
                    }
                )
                if not agree:
                    disagreements.append(rows[-1])
    repair["rescued"] = repair["legacy_unresolved"] - repair["repaired_unresolved"]
    scored = [r for r in rows if r["eligible"]]
    return {
        "lifted_from": lift,
        "banks": {name: len(gold) for name, gold in banks.items()},
        "k_grid": list(k_grid),
        "rows_compared": len(rows),
        "eligible_rows": len(scored),
        "disagreements": disagreements,
        "all_metric_reproduced_to_the_digit": not disagreements,
        "established_all_mean": (
            statistics.mean(r["established_all"] for r in scored) if scored else None
        ),
        "span_containment_all_mean": (
            statistics.mean(r["span_containment_all"] for r in scored) if scored else None
        ),
        "gold_map_repair": repair,
        "parity_budget": "unbounded - the established metric has no byte budget; F.23's budget is "
        "applied only where F.23's own number is reported",
    }


# --------------------------------------------------------------------------------------------
# (4) the burnt split
# --------------------------------------------------------------------------------------------


def burnt_split(bank_dirs: dict[str, Path]) -> ec.BurntSplit:
    """Re-derive the 288 QASPER ids with the recorded salt; take the 72 LongMem ids from the manifest."""
    provenance: dict = {}
    qasper_ids: set[str] = set()
    raw_by_split = {split: gs.load_qasper_split(split) for split in ("train", "dev", "test")}
    ids_by_split = {
        split: [q["question_id"] for p in raw.values() for q in p["qas"]]
        for split, raw in raw_by_split.items()
    }
    for bank_name, bank in bank_dirs.items():
        banked = [q["id"] for q in json.loads((bank / "queries.json").read_text())["questions"]]
        limit = len(banked)
        best = None
        for split in ("train", "dev", "test"):
            derived = ec.qasper_burnt_ids(ids_by_split, {split: limit})
            if set(derived) == set(banked):
                best = (split, derived)
                break
        if best is None:
            raise ec.CoverageError(
                f"{bank_name}: the recorded salt reproduces no split's first {limit} ids - the "
                "burnt set cannot be re-derived and must not be guessed"
            )
        split, derived = best
        qasper_ids.update(derived)
        provenance[bank_name] = {
            "n": limit,
            "raw_split": split,
            "rule": "sorted by sha256('skein-extension:qasper:' + question_id), first n",
            "reproduced": True,
        }
    manifest = gs.longmem_split_manifest()
    longmem_ids = set(manifest["development_ids"]) | set(manifest["final_ids"])
    dataset_sha = (
        "sha256:" + hashlib.sha256(gs.LONGMEM_DATASET.read_bytes()).hexdigest()
        if gs.LONGMEM_DATASET.exists()
        else None
    )
    provenance["longmemeval_s"] = {
        "n": len(longmem_ids),
        "salt": manifest["selection_salt"],
        "manifest_dataset_sha256": manifest["dataset_sha256"],
        "dataset_on_disk_sha256": dataset_sha,
        "dataset_matches_manifest": dataset_sha == "sha256:" + manifest["dataset_sha256"],
    }
    return ec.BurntSplit(frozenset(qasper_ids), frozenset(longmem_ids), provenance)


# --------------------------------------------------------------------------------------------
# (5) graded vs flat, on both benchmarks
# --------------------------------------------------------------------------------------------


def _score_container(question_text, image, gold, budgets, read_ids):
    """Run each read AT each budget, then score it at that same budget.

    A read is given the budget: which node it can afford to open is part of what it decides, so
    running once at the largest budget and truncating afterwards would score a different arm. The
    scorer's own prefix-stop truncation then removes nothing, which is the check that the arm
    respected the budget it was given.
    """
    out: dict[str, tuple[rr.ReadResult, dict]] = {}
    for read_id in read_ids:
        per_budget = {}
        primary_result = None
        for budget in budgets:
            result = rr.READS[read_id](question_text, image, budget)
            if primary_result is None:
                primary_result = result
            per_budget[budget] = ec.complete_evidence(gold, result.units, budget)
        out[read_id] = (primary_result, per_budget)
    return out


def _summarise(rows, budget):
    eligible = [r for r in rows if r.eligible]
    return {
        "n_questions": len(rows),
        "n_eligible": len(eligible),
        "complete_evidence_coverage": (
            statistics.mean(r.complete for r in eligible) if eligible else None
        ),
        "n_covered": sum(int(r.complete == 1.0) for r in eligible),
        "n_supplied_nothing": sum(int(r.n_units == 0) for r in eligible),
        "evidence_recall": statistics.mean(r.recall for r in eligible) if eligible else None,
        "mean_bytes_used": statistics.mean(r.bytes_used for r in eligible) if eligible else None,
        "mean_units": statistics.mean(r.n_units for r in eligible) if eligible else None,
        "mean_units_closed": statistics.mean(r.n_units_closed for r in eligible) if eligible else None,
        "grades_supplied": sorted({g for r in eligible for g in r.grades_supplied}),
        "budget_bytes": budget,
    }


def measure_qasper(
    limit: int, budgets: tuple[int, ...], bank_dirs: dict[str, Path]
) -> tuple[dict, dict]:
    """Score every read at every budget on the development bank; return (summary block, rows)."""
    gold_bank = json.loads((bank_dirs["qasper_development_v2"] / "gold.json").read_text())
    queries = json.loads((bank_dirs["qasper_development_v2"] / "queries.json").read_text())["questions"]
    question_text = {q["id"]: q["question"] for q in queries}
    wanted = set(list(question_text)[:limit])
    papers = _qasper_papers_for(wanted)
    images: dict[str, gs.ContainerImage] = {}
    per_read: dict[str, dict[int, list]] = {}
    work: dict[str, list[dict]] = {}
    refusals = []
    for qid in sorted(wanted):
        paper_id, paper = papers[qid]
        if paper_id not in images:
            images[paper_id] = gs.qasper_paper_image(paper_id, paper)
        image = images[paper_id]
        gold = gs.qasper_gold(paper_id, paper, image, [qid], repaired=True)[qid]
        try:
            scored = _score_container(question_text[qid], image, gold, budgets, ("flat", "graded", "summary"))
        except rr.NoCondition as error:
            refusals.append({"question_id": qid, "refusal": str(error)})
            continue
        for read_id, (result, per_budget) in scored.items():
            work.setdefault(read_id, []).append(result.work)
            for budget, row in per_budget.items():
                per_read.setdefault(read_id, {}).setdefault(budget, []).append(row)
    block = _assemble(per_read, work, budgets, refusals, dataset="qasper", burnt=True)
    return block, _rows_payload(per_read, budgets, dataset="qasper")


def measure_longmem(
    limit: int, budgets: tuple[int, ...], burnt: ec.BurntSplit
) -> tuple[dict, dict]:
    """Score every read at every budget on untouched questions; return (summary block, rows)."""
    pairs = gs.load_longmem(limit=None, verify=False)
    chosen = [(c, g) for c, g in pairs if c.jurisdiction_id not in burnt.longmem][:limit]
    per_read: dict[str, dict[int, list]] = {}
    work: dict[str, list[dict]] = {}
    refusals = []
    for case, record in chosen:
        image = gs.longmem_case_image(case)
        gold = gs.longmem_gold(record, image)
        try:
            scored = _score_container(case.query.question, image, gold, budgets, ("flat", "graded", "summary"))
        except rr.NoCondition as error:
            refusals.append({"question_id": case.jurisdiction_id, "refusal": str(error)})
            continue
        for read_id, (result, per_budget) in scored.items():
            work.setdefault(read_id, []).append(result.work)
            for budget, row in per_budget.items():
                per_read.setdefault(read_id, {}).setdefault(budget, []).append(row)
    block = _assemble(per_read, work, budgets, refusals, dataset="longmemeval_s", burnt=False)
    return block, _rows_payload(per_read, budgets, dataset="longmemeval_s")


ARM_READ = "graded"


def _rows_payload(per_read, budgets, *, dataset) -> dict:
    """The per-(question, read, budget) rows, in the form that gets deposited.

    F.23's implementation clause asks for "per (question, arm, budget) a boolean and the
    missing-span list; the missing-span list is what makes a failure diagnosable without a
    reader", and must_achieve (4) for the arm's supplied set per question. Aggregates cannot
    answer either: this is the file that says WHICH question failed and on WHAT span, and it
    carries the supplied fingerprint, so the identity audit is recomputable from the deposit
    alone (``--recompute-audit``).
    """
    rows = [
        {"read": read_id, **row.as_dict()}
        for read_id, by_budget in per_read.items()
        for _budget, scored in by_budget.items()
        for row in scored
    ]
    rows.sort(key=lambda r: (r["question_id"], r["read"], r["budget_bytes"]))
    reads = sorted(per_read)
    return {
        "schema": "atlas-evidence-coverage-rows/1",
        "scorer_version": ec.COVERAGE_SCORER_VERSION,
        "dataset": dataset,
        "budgets": list(budgets),
        "primary_budget_bytes": ec.declared("coverage.primary_budget_bytes"),
        "reads": reads,
        "arm": ARM_READ if ARM_READ in reads else None,
        "controls": [r for r in reads if r != ARM_READ],
        "row_fields": "evidence_coverage.CoverageRow.as_dict(), plus the 'read' that supplied it; "
        "rebuild one with evidence_coverage.CoverageRow.from_dict",
        "n_rows": len(rows),
        "rows": rows,
    }


def _assemble(per_read, work, budgets, refusals, *, dataset, burnt) -> dict:
    summaries = {
        read_id: {str(budget): _summarise(rows, budget) for budget, rows in by_budget.items()}
        for read_id, by_budget in per_read.items()
    }
    executed_work = {
        read_id: {
            key: statistics.mean(w[key] for w in entries)
            for key in ("units_scored", "faces_tested", "nodes_expanded", "objects_touched")
        }
        for read_id, entries in work.items()
    }
    primary = ec.declared("coverage.primary_budget_bytes")
    audits = {}
    if "graded" in per_read:
        arm_rows = {r.question_id: r for r in per_read["graded"][primary]}
        controls = {
            read_id: {r.question_id: r for r in by_budget[primary]}
            for read_id, by_budget in per_read.items()
            if read_id != "graded"
        }
        audits["graded_vs_controls"] = ec.identity_audit(arm_rows, controls).as_dict()
    return {
        "dataset": dataset,
        "questions_are_burnt": burnt,
        "budgets": list(budgets),
        "primary_budget_bytes": primary,
        "summaries": summaries,
        "mean_executed_work_per_question": executed_work,
        "read_refusals": refusals,
        "identity_audit": audits,
    }


# --------------------------------------------------------------------------------------------
# (6) the plants
# --------------------------------------------------------------------------------------------


def planted_violations(budgets: tuple[int, ...]) -> dict:
    """Both plants on one small real QASPER paper, with the refusal each one meets."""
    raw = gs.load_qasper_split("dev")
    paper_id = sorted(raw)[0]
    paper = raw[paper_id]
    image = gs.qasper_paper_image(paper_id, paper)
    question = paper["qas"][0]
    gold = gs.qasper_gold(paper_id, paper, image, [question["question_id"]], repaired=True)[
        question["question_id"]
    ]
    primary = ec.declared("coverage.primary_budget_bytes")

    # PLANT A: coverage by summary. Every coarse node that carries the gold is supplied CLOSED.
    nodes = [n for n in image.nodes if n.grade == 1]
    gold_addresses = [a for alt in gold.alternatives for r in alt.requirements for a in r.addresses]
    carrying = [
        n
        for n in nodes
        if any(n.span.start <= a.start and a.end <= n.span.end for a in gold_addresses)
    ]
    summary_units = tuple(
        ec.SuppliedUnit(
            unit_id=f"summary:{n.node_id}",
            grade=n.grade,
            opened=False,
            spans=(),
            bytes_charged=len(n.face_text.encode("utf-8")) + rr.SEPARATOR_COST,
            face_kind=n.kind,
        )
        for n in carrying
    )
    summary_row = ec.complete_evidence(gold, summary_units, max(primary, 1 + sum(u.bytes_charged for u in summary_units)))
    fuzzy_text = " ".join(n.face_text for n in carrying) + " " + " ".join(
        r.text for alt in gold.alternatives for r in alt.requirements
    )
    fuzzy_credit = ec.fuzzy_match_coverage(gold, fuzzy_text)

    # PLANT B: the arm is its control, relabelled.
    control = rr.flat_read(question["question"], image, primary)
    arm_units = ec.plant_identity_arm(control.units)
    qid = question["question_id"]
    arm_rows = {qid: ec.complete_evidence(gold, arm_units, primary)}
    control_rows = {"flat_control": {qid: ec.complete_evidence(gold, control.units, primary)}}
    audit = ec.identity_audit(arm_rows, control_rows)

    return {
        "plant_a_coverage_by_summary": {
            "paper": paper_id,
            "question_id": qid,
            "n_coarse_nodes_carrying_gold": len(carrying),
            "bytes_spent_on_summaries": sum(u.bytes_charged for u in summary_units),
            "fuzzy_text_match_credits": fuzzy_credit,
            "span_containment_predicate": summary_row.complete,
            "caught": fuzzy_credit == 1.0 and summary_row.complete == 0.0,
            "why": "the face of a node is a projection; the record never points up into one, so a "
            "summary covers no byte of the gold it coarsens. F.23's planted violation is exactly "
            "this fuzzy text-match standing in for containment.",
        },
        "plant_b_arm_equals_control": {
            "question_id": qid,
            "arm_fingerprint": arm_rows[qid].supplied_fingerprint,
            "control_fingerprint": control_rows["flat_control"][qid].supplied_fingerprint,
            "identical": arm_rows[qid].supplied_fingerprint
            == control_rows["flat_control"][qid].supplied_fingerprint,
            "audit": audit.as_dict(),
            "caught": audit.void,
            "why": "relabelled unit ids do not change the supplied byte addresses, which is what "
            "the fingerprint hashes; with every question identical the run has zero capacity for "
            "the discordant pairs F.23's pre-spend gate requires.",
        },
    }


# --------------------------------------------------------------------------------------------
# The deposit: rows on disk, the audit recomputed from them, and the run's own digest.
# --------------------------------------------------------------------------------------------


MEASUREMENT_DIGEST_RULE = (
    "sha256 over json.dumps(measurement without its 'run' block, indent=1, ensure_ascii=False, "
    "default=str). The run block holds the only fields that can differ between two runs of the "
    "same command - the argv, the paths written and the wall time - so two runs of the stated "
    "command produce the same digest, and a digest that differs is a real difference in the "
    "measurement. Recompute it with: coverage_cli --verify-digest <measurement.json>"
)


def _payload_digest(report: dict) -> str:
    body = {k: v for k, v in report.items() if k != "run"}
    text = json.dumps(body, indent=1, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def audit_from_rows(rows_path: Path, budget_bytes: int | None = None) -> dict:
    """Recompute the identity audit from a DEPOSITED rows file alone.

    No corpus, no gold, no re-scoring: the rows carry the supplied fingerprint per (question,
    read, budget), and the audit is a function of those fingerprints. This is what makes the audit
    in the report checkable against the deposit rather than against this process's memory.
    """
    payload = json.loads(Path(rows_path).read_text())
    if payload.get("schema") != "atlas-evidence-coverage-rows/1":
        raise ec.CoverageError(f"{rows_path} is not an atlas-evidence-coverage-rows/1 deposit")
    arm = payload["arm"]
    if arm is None:
        raise ec.CoverageError(f"{rows_path} deposits no arm read, so there is no audit to recompute")
    budget = payload["primary_budget_bytes"] if budget_bytes is None else budget_bytes
    by_read: dict[str, dict[str, ec.CoverageRow]] = {}
    for raw in payload["rows"]:
        if raw["budget_bytes"] != budget:
            continue
        row = ec.CoverageRow.from_dict(raw)
        by_read.setdefault(raw["read"], {})[row.question_id] = row
    if arm not in by_read:
        raise ec.CoverageError(f"{rows_path} deposits no {arm!r} row at budget {budget}")
    arm_rows = by_read.pop(arm)
    return {
        "rows_file": str(rows_path),
        "rows_file_sha256": _file_sha256(Path(rows_path)),
        "dataset": payload["dataset"],
        "arm": arm,
        "budget_bytes": budget,
        "recomputed_from": "the deposited supplied fingerprints only - no corpus, no gold, no "
        "re-scoring",
        "audit": ec.identity_audit(arm_rows, by_read).as_dict(),
    }


def verify_digest(path: Path) -> dict:
    """Recompute a banked measurement's own digest and say whether it still holds."""
    report = json.loads(Path(path).read_text())
    recorded = report.get("run", {}).get("measurement_digest")
    recomputed = _payload_digest(report)
    return {
        "file": str(path),
        "recorded": recorded,
        "recomputed": recomputed,
        "matches": recorded == recomputed,
        "rule": MEASUREMENT_DIGEST_RULE,
        "command_that_produced_it": report.get("run", {}).get("command"),
    }


# --------------------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """The command's own interface. Its defaults ARE ``SAMPLES``, so ``--out <path>`` alone
    reproduces the banked measurement; nothing here is a bare literal."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out")
    parser.add_argument(
        "--recompute-audit",
        help="a deposited rows file; rebuild the identity audit from its fingerprints and print it",
    )
    parser.add_argument(
        "--verify-digest",
        help="a banked measurement; recompute its measurement_digest and print whether it holds",
    )
    parser.add_argument(
        "--qasper-parity-k",
        default=",".join(str(k) for k in sample("measurement.qasper_parity_k_grid")),
    )
    parser.add_argument(
        "--qasper-read-questions", type=int, default=sample("measurement.qasper_read_questions")
    )
    parser.add_argument(
        "--longmem-questions", type=int, default=sample("measurement.longmem_questions")
    )
    parser.add_argument(
        "--multihop-parity-sample", type=int, default=sample("measurement.multihop_parity_sample")
    )
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.recompute_audit:
        print(json.dumps(audit_from_rows(Path(args.recompute_audit)), indent=1))
        return 0
    if args.verify_digest:
        result = verify_digest(Path(args.verify_digest))
        print(json.dumps(result, indent=1))
        return 0 if result["matches"] else 1
    if not args.out:
        parser.error("--out is required (or use --recompute-audit / --verify-digest)")

    started = time.perf_counter()
    budgets = (
        ec.declared("coverage.primary_budget_bytes"),
        *ec.declared("coverage.secondary_budget_bytes"),
    )
    bank_dirs = {
        "qasper_development_v2": gs.EXTENSION / "cache" / "qasper_development_v2",
        "qasper_final_v2": gs.EXTENSION / "cache" / "qasper_final_v2",
    }

    def _flatten(table: dict) -> dict:
        return {
            k: {**v, "value": list(v["value"]) if isinstance(v["value"], tuple) else v["value"]}
            for k, v in table.items()
        }

    report: dict = {
        "schema": "atlas-evidence-coverage-measurement/2",
        "scorer_version": ec.COVERAGE_SCORER_VERSION,
        "declared_parameters": _flatten(ec.DECLARED),
        "declared_samples": _flatten(SAMPLES),
        "input_digests": _digests(),
        "budgets": list(budgets),
    }

    report["multihop_reach"] = multihop_reach(args.multihop_parity_sample)
    report["qasper_all_metric"] = qasper_parity(
        list(bank_dirs.values()), tuple(int(k) for k in args.qasper_parity_k.split(","))
    )

    burnt = burnt_split(bank_dirs)
    refusal = None
    try:
        burnt.refuse_claim(sorted(burnt.qasper)[:5])
    except ec.BurntQuestionRefused as error:
        refusal = str(error)
    report["burnt_split"] = {
        **burnt.as_dict(),
        "claim_on_burnt_questions_refused": refusal,
        "refusal_active": refusal is not None,
    }

    report["qasper_reads"], qasper_rows = measure_qasper(
        args.qasper_read_questions, budgets, bank_dirs
    )
    report["qasper_reads"]["claim_admissible"] = False
    report["qasper_reads"]["claim_admissible_why"] = (
        "every question of the development bank is one of the 288 burnt QASPER ids; these rows are "
        "an instrument exercise and no claim is computed from them"
    )
    report["longmem_reads"], longmem_rows = measure_longmem(args.longmem_questions, budgets, burnt)
    report["longmem_reads"]["claim_admissible"] = True
    report["longmem_reads"]["claim_admissible_why"] = (
        "the questions are disjoint from the 72 burnt LongMemEval ids; they are NOT F.20's "
        "107-question development stratum, which is drawn at the preregistration, so these numbers "
        "are the instrument's, not the campaign's"
    )
    report["planted_violations"] = planted_violations(budgets)

    # The rows go down BESIDE the measurement, and the measurement records what they hash to, so a
    # later reader can tell that the aggregates above and the rows on disk are one run.
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    deposits = {}
    written_rows = {}
    for payload in (qasper_rows, longmem_rows):
        name = f"coverage_rows_{payload['dataset']}.json"
        path = out.parent / name
        path.write_text(json.dumps(payload, indent=1, ensure_ascii=False, default=str))
        written_rows[name] = str(path)
        deposits[name] = {
            "dataset": payload["dataset"],
            "n_rows": payload["n_rows"],
            "reads": payload["reads"],
            "budgets": payload["budgets"],
            "sha256": _file_sha256(path),
            "carries": "per (question, read, budget): F.23's complete/eligible verdict, the "
            "supplied fingerprint, the bytes and unit counts, and the missing-span list with the "
            "(content_handle, start, end) address of every gold span that was not supplied",
            "recompute_audit_command": (
                "scripts/laplace-python -m atlas.bench.coverage_cli --recompute-audit "
                f"<dir>/{name}"
            ),
        }
    report["rows_deposit"] = {
        "law": "F.23's implementation clause: 'per (question, arm, budget) a boolean and the "
        "missing-span list; the missing-span list is what makes a failure diagnosable without a "
        "reader'. The aggregates in this file are means over exactly these rows.",
        "files": deposits,
        "identity_audit_is_recomputable_from_them": True,
    }

    argv_used = [str(a) for a in (argv if argv is not None else sys.argv[1:])]
    report["run"] = {
        "argv": argv_used,
        "command": "scripts/laplace-python -m atlas.bench.coverage_cli "
        + shlex.join(argv_used),
        "defaults_are_the_measurement_sample": (
            args.multihop_parity_sample == sample("measurement.multihop_parity_sample")
            and args.longmem_questions == sample("measurement.longmem_questions")
            and args.qasper_read_questions == sample("measurement.qasper_read_questions")
            and tuple(int(k) for k in args.qasper_parity_k.split(","))
            == tuple(sample("measurement.qasper_parity_k_grid"))
        ),
        "effective_arguments": {
            "out": str(out),
            "qasper_parity_k": args.qasper_parity_k,
            "qasper_read_questions": args.qasper_read_questions,
            "longmem_questions": args.longmem_questions,
            "multihop_parity_sample": args.multihop_parity_sample,
        },
        "files_written": {"measurement": str(out), **written_rows},
        "wall_seconds": round(time.perf_counter() - started, 3),
        "digest_rule": MEASUREMENT_DIGEST_RULE,
    }
    report["run"]["measurement_digest"] = _payload_digest(report)

    out.write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str))
    print(f"wrote {out} in {report['run']['wall_seconds']}s")
    print(f"measurement_digest {report['run']['measurement_digest']}")
    for name, path in written_rows.items():
        print(f"rows {path} {deposits[name]['n_rows']} rows {deposits[name]['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
