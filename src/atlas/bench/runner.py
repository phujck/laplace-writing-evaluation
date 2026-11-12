"""runner.py - arms x tasks over ONE frozen bundle. Deterministic, counted, UNJUDGED until judged.

What a run is: one task bundle, one view, a list of arms, and a row per (task, arm). Nothing
else varies. The bundle names its snapshot and its segmentation, the view names its universe, and
every arm names its protocol - so the manifest of a run is a complete statement of what was
measured, and two runs of the same statement produce the same rows.

Determinism, and what is exempt from it. Every row field is a function of the bundle and the
arms, with three exceptions that are wall-clock by nature and are listed here rather than
discovered later: ``latency_ms``, the fold's ``wall_seconds``, and the manifest timestamps. The
determinism gate compares two runs modulo exactly those fields.

Three mechanical checks fire per row, before any number is written:

  * the COUNTED query model calls equal the arm's DECLARED count (``ProtocolViolation``);
  * every byte that reached the context passed the counting reader, whose caps are the arm's own
    declared read protocol;
  * the arm's answer is scored by the ported v1 scorer and by nothing else.

THE JUDGE BOUNDARY (seam J9). A run manifest is written with ``"verdict": "UNJUDGED"`` and every
printed summary says so, until a verdict row exists in the engine's judged-verdict store and is
named here. atlas never writes that store: self-certification is what the bar law forbids, and a
benchmark grading its own build is the purest form of it.

THE RANK COLUMNS (Phase 3), AND WHY THEY ARE STRICTLY ADDITIVE. Both Phase 2 verdict rows carry
the same inheritance: *a rank-aware/first-hit criterion (additive columns, frozen correctness
definition unchanged) before the comparative table is read as a ranking*. The reason is measured,
not stylistic - the planted-bad control put a wrong answer at RANK 1 on six of six retrieval cells
and moved no verdict at all, because correctness-by-atom-presence measures presence and is blind
to order. Two columns are added, and ``correct`` is computed by exactly the same ported scorer
over exactly the same context as before:

  ``ground_truth_rank``  the rank of the FIRST retrieved span that carries any of the task's
                         atoms - "how far down the list the evidence first appears".
  ``first_hit_rank``     the smallest prefix length whose spans JOINTLY satisfy the frozen scorer -
                         "how much of the list you had to accept before the answer completed".
                         It is the rank analogue of ``first_hit_offset``, which is a character
                         offset into the assembled context and cannot distinguish rank 1 from
                         rank 10 when the spans are short.

Both are ``null`` for an arm that ranks nothing - the flat reads and the grep arm return an empty
``retrieved``, and a fixed read set HAS no rank. Null is the statement, never zero.

The rank pass reads span text from the VIEW and never through the ``SpanReader``. That is
deliberate and it is a cost-integrity property: these columns are scoring-side instrumentation,
so charging their bytes to the arm would change ``tokens_touched`` and every cost number derived
from it. The determinism re-run against the banked Phase 2 rows is what proves it did not.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..errors import ProtocolViolation
from ..ids import chash
from ..store import write_atomic, write_jsonl
from . import BENCH_VERSION
from .cost import ArmCost, FoldCost, ModelCounter, SpanReader, median, percentile, tokens_of
from .freeze import verify_bundle
from .scoring import SCORING_VERSION, atom_members, normalize, score
from .task import BenchTask, BenchTaskBundle
from .universe import PlantedSpan, SnapshotView, with_planted

UNJUDGED = "UNJUDGED"


@dataclass
class RunResult:
    """Everything one run produced, in memory, before it is written anywhere."""

    rows: list[dict[str, Any]] = field(default_factory=list)
    costs: dict[str, ArmCost] = field(default_factory=dict)
    folds: dict[str, FoldCost] = field(default_factory=dict)
    planted_rows: list[dict[str, Any]] = field(default_factory=list)
    manifest: dict[str, Any] = field(default_factory=dict)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rank_columns(view: SnapshotView, task: BenchTask, retrieved: list[str],
                 retrieved_texts: list[str] | None = None) -> tuple[int | None, int | None]:
    """``(ground_truth_rank, first_hit_rank)`` for one ranked answer. Additive; scores nothing.

    Returns ``(None, None)`` for an arm that retrieved nothing - a fixed read set has no ranking,
    and reporting 0 or 1 for it would invent an ordering the arm never produced.

    ``first_hit_rank`` re-uses the FROZEN scorer on growing prefixes rather than re-implementing
    "answered": whatever ``score`` counts as correct at full length is what it counts as correct
    at a prefix, so the two columns cannot drift apart from the correctness definition they sit
    beside. A span the view no longer holds is skipped rather than fatal - the planted control
    injects ids into a copied view, and an id that does not resolve contributes no evidence.

    ``retrieved_texts``, when the arm supplies it, is authoritative: an arm that ranks something
    other than leaf spans (a RAPTOR cluster summary, a whole node) is the only thing that can say
    what it actually put at rank 3.
    """
    if not retrieved:
        return None, None
    supplied = list(retrieved_texts or [])
    texts: list[str] = []
    ground_truth_rank: int | None = None
    first_hit_rank: int | None = None
    for rank, span_id in enumerate(retrieved, start=1):
        if rank <= len(supplied):
            text = supplied[rank - 1]
        else:
            span = view.span_by_id(span_id)
            text = view.span_text(span) if span is not None else ""
        texts.append(text)
        if ground_truth_rank is None and any(
            normalize(member) in normalize(text)
            for atom in task.atoms for member in atom_members(atom)
        ):
            ground_truth_rank = rank
        if first_hit_rank is None:
            complete, _ = score("\n".join(texts), task.atoms, task.window)
            if complete:
                first_hit_rank = rank
    return ground_truth_rank, first_hit_rank


def run_bundle(bundle: BenchTaskBundle, view: SnapshotView, arms: list,
               segmentation_id: str = "", verify: bool = True,
               planted: list[PlantedSpan] | None = None,
               run_label: str = "") -> RunResult:
    """Run every arm over every task of one bundle. Correctness is computed before any cost."""
    started_ts = _now()
    if verify:
        # Verified against THIS view, whichever universe it is. The full-universe control is a
        # superset of the filtered view, so every anchor still resolves in it; if one did not,
        # that would mean an atom lived in a node the filter had excluded, and the control run
        # should refuse rather than quietly score a task the filtered run could not have passed.
        verify_bundle(bundle, view)

    result = RunResult()
    per_arm_latency: dict[str, list[float]] = {}
    per_arm_tokens: dict[str, list[int]] = {}
    per_arm_scan: dict[str, int] = {}
    per_arm_model_calls: dict[str, int] = {}
    per_arm_model_tokens: dict[str, int] = {}
    encoder_bill = {}

    # --- the fold, once per arm -------------------------------------------
    for arm in arms:
        # A shared meter counts vectorisers even when legacy model-call columns
        # classify them as mechanical. These counts overlap, and are never summed.
        encoder = getattr(arm, 'encoder', None)
        meter = {'calls': 0, 'vectors': 0}
        if encoder is not None:
            original_embed = encoder.embed
            def counted_embed(texts, _fn=original_embed, _meter=meter):
                _meter['calls'] += 1
                vectors = _fn(texts)
                _meter['vectors'] += len(vectors)
                return vectors
            encoder.embed = counted_embed
        try:
            fold = arm.fold(view, segmentation_id)
        finally:
            if encoder is not None:
                encoder.embed = original_embed
        encoder_bill[arm.protocol.full_id] = dict(fold_calls_this_run=meter['calls'],
                                                 fold_vectors_this_run=meter['vectors'],
                                                 query_calls=0)

        result.folds[arm.protocol.full_id] = fold
        if fold.model_calls != arm.protocol.fold_model_calls:
            raise ProtocolViolation("declared fold model calls disagree with the counted fold",
                                    arm=arm.protocol.full_id,
                                    declared=arm.protocol.fold_model_calls,
                                    counted=fold.model_calls)

    # --- the rows ---------------------------------------------------------
    for task in bundle.tasks:
        for arm in arms:
            arm_id = arm.protocol.full_id
            reader = SpanReader(view,
                                max_spans_read=arm.protocol.max_spans_read or None,
                                max_whole_file_reads=arm.protocol.max_whole_file_reads or None,
                                read_budget_bytes=arm.protocol.read_budget_bytes or None)
            models = ModelCounter(arm_id)
            t0 = time.perf_counter()
            encoder = getattr(arm, 'encoder', None)
            query_meter = {'calls': 0}
            if encoder is not None:
                original_query = encoder.query
                def counted_query(text, _fn=original_query, _meter=query_meter):
                    _meter['calls'] += 1
                    return _fn(text)
                encoder.query = counted_query
            try:
                answer = arm.answer(task, reader, models)
            finally:
                if encoder is not None:
                    encoder.query = original_query
            declared_encoder_calls = getattr(arm, 'query_encoder_calls', None)
            if declared_encoder_calls is not None and query_meter['calls'] != declared_encoder_calls:
                raise ProtocolViolation('ENCODER_CALL_DECLARATION_MISMATCH', arm=arm_id)
            encoder_bill[arm_id]['query_calls'] += query_meter['calls']
            latency_ms = (time.perf_counter() - t0) * 1000.0
            models.assert_declared(arm.protocol.query_model_calls)

            correct, offset = score(answer.context, task.atoms, task.window)
            gt_rank, hit_rank = rank_columns(view, task, answer.retrieved,
                                             answer.retrieved_texts)
            counters = reader.snapshot_counters()
            row = {
                "task": task.task_id,
                "class": task.task_class,
                "arm": arm_id,
                "correct": bool(correct),
                "rounds": answer.rounds,
                "tokens_context": tokens_of(answer.context),
                "tokens_touched": counters["tokens_touched"],
                "first_hit_offset": offset,
                "ground_truth_rank": gt_rank,
                "first_hit_rank": hit_rank,
                "latency_ms": round(latency_ms, 3),
                "cost": {
                    "spans_read": counters["spans_read"],
                    "whole_file_reads": counters["whole_file_reads"],
                    "bytes_served": counters["bytes_served"],
                    "scan_bytes_uncharged": counters["scan_bytes"],
                    "query_encoder_calls": query_meter["calls"],
                    "query_model_calls": models.calls,
                    "query_model_tokens": models.tokens,
                },
                "retrieved": answer.retrieved,
                "note": answer.note,
                "detail": answer.detail,
            }
            result.rows.append(row)
            per_arm_latency.setdefault(arm_id, []).append(latency_ms)
            per_arm_scan[arm_id] = per_arm_scan.get(arm_id, 0) + counters["scan_bytes"]
            per_arm_model_calls[arm_id] = per_arm_model_calls.get(arm_id, 0) + models.calls
            per_arm_model_tokens[arm_id] = per_arm_model_tokens.get(arm_id, 0) + models.tokens
            if correct:
                per_arm_tokens.setdefault(arm_id, []).append(counters["tokens_touched"])

    # --- the five cost dimensions, per arm, over CORRECT tasks only --------
    reference = len(bundle.tasks)
    for arm in arms:
        arm_id = arm.protocol.full_id
        touched = per_arm_tokens.get(arm_id, [])
        lat = per_arm_latency.get(arm_id, [])
        result.costs[arm_id] = ArmCost(
            arm_id=arm_id, fold=result.folds[arm_id], fold_reference_query_count=getattr(arm, "reference_queries", reference),
            query_model_calls=per_arm_model_calls.get(arm_id, 0),
            query_model_tokens=per_arm_model_tokens.get(arm_id, 0),
            tokens_touched_median=int(median(touched)) if touched else None,
            tokens_touched_total=sum(touched),
            scan_bytes_total=per_arm_scan.get(arm_id, 0),
            latency_median_ms=round(median(lat), 3) if lat else None,
            latency_p95_ms=round(percentile(lat, 0.95), 3) if lat else None,
        )

    # --- the planted-bad control ------------------------------------------
    if planted:
        result.planted_rows = run_planted(bundle, view, arms, planted, segmentation_id,
                                          unplanted_rows=result.rows)

    result.manifest = {
        "kind": "bench-run/2",
        "run_label": run_label,
        "verdict": UNJUDGED,
        "verdict_row": None,
        "bench_version": BENCH_VERSION,
        "scoring_version": SCORING_VERSION,
        "bundle_id": bundle.bundle_id,
        "bundle_frozen_ts": bundle.frozen_ts,
        "snapshot_id": bundle.snapshot_id,
        "segmentation_id": bundle.segmentation_id,
        "universe": view.universe.to_dict(),
        "view_stats": view.stats(),
        "arms": [arm.protocol.to_dict() for arm in arms],
        "arm_protocol_ids": {arm.protocol.full_id: arm.protocol.protocol_id for arm in arms},
        "fold": {k: v.to_dict() for k, v in result.folds.items()},
        "cost": {k: v.to_dict() for k, v in result.costs.items()},
        "encoder_bill": encoder_bill,
        "encoder_bill_note": "Common observed embedding API calls for every encoder arm; overlap with model-call columns, never sum. Fold calls this run only; historical bill remains in fold.",
        "task_count": len(bundle.tasks),
        "row_count": len(result.rows),
        "started_ts": started_ts,
        "finished_ts": _now(),
        "freeze_before_run": bundle.frozen_ts < started_ts,
        "rows_digest": chash(_deterministic_rows(result.rows)),
    }
    if not result.manifest["freeze_before_run"]:
        raise ProtocolViolation(
            "the task bundle was not frozen before this run started - pre-registration is an "
            "ordering claim and this run cannot make it",
            frozen_ts=bundle.frozen_ts, started_ts=started_ts,
        )
    return result


def run_planted(bundle: BenchTaskBundle, view: SnapshotView, arms: list,
                planted: list[PlantedSpan], segmentation_id: str = "",
                unplanted_rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """The planted-bad control: synthetic wrong-answer spans in a COPY of the view.

    A false positive is the planted span reaching rank <= k on the question it was built to
    match. For an arm that ranks nothing (the flat read), the analogous event is the planted
    text reaching the arm's context at all - reported under its own key so the two are never
    confused with each other.

    ``was_correct`` SITS BESIDE ``still_correct`` ON PURPOSE, and it is a repair. The first
    reading of this control claimed a plant had flipped an arm from correct to incorrect; the
    judge cross-tabulated the two columns and found zero differences anywhere - the arm had been
    incorrect on that task without any plant. A control that reports only the post-plant verdict
    invites exactly that misreading, because the reader has to go and find the baseline. With
    both columns present a flip IS a visible delta and its absence is equally visible, so the
    error class is structural rather than a matter of care.
    """
    planted_view = with_planted(view, planted)
    baseline = {(r["task"], r["arm"]): bool(r["correct"]) for r in (unplanted_rows or [])}
    rows: list[dict[str, Any]] = []
    for arm in arms:
        arm.fold(planted_view, segmentation_id)
        for p in planted:
            task = bundle.task(p.targets_task)
            if task is None:
                continue
            reader = SpanReader(planted_view,
                                max_spans_read=arm.protocol.max_spans_read or None,
                                max_whole_file_reads=arm.protocol.max_whole_file_reads or None,
                                read_budget_bytes=arm.protocol.read_budget_bytes or None)
            models = ModelCounter(arm.protocol.full_id)
            answer = arm.answer(task, reader, models)
            rank = (answer.retrieved.index(p.planted_id) + 1
                    if p.planted_id in answer.retrieved else None)
            in_context = any(w.casefold() in answer.context.casefold() for w in p.wrong_atoms)
            still_correct, _ = score(answer.context, task.atoms, task.window)
            was_correct = baseline.get((task.task_id, arm.protocol.full_id))
            rows.append({
                "arm": arm.protocol.full_id, "task": task.task_id,
                "planted_id": p.planted_id,
                "retrieved_rank": rank,
                "false_positive_at_k": bool(rank is not None and rank <= arm.protocol.k),
                "wrong_answer_in_context": bool(in_context),
                "was_correct": was_correct,
                "still_correct": bool(still_correct),
                "verdict_flipped": (None if was_correct is None
                                    else bool(was_correct != bool(still_correct))),
            })
    # Re-fold the arms back onto the real view: a planted index must never serve a scored run.
    for arm in arms:
        arm.fold(view, segmentation_id)
    return rows


def _deterministic_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rows minus the wall-clock fields. The determinism gate hashes exactly this."""
    out = []
    for row in rows:
        copy = dict(row)
        copy.pop("latency_ms", None)
        out.append(copy)
    return out


def write_run(result: RunResult, out_dir: Path) -> dict[str, Path]:
    """Bank a run: rows.jsonl, planted.jsonl (when present) and manifest.json."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {"rows": out_dir / "rows.jsonl", "manifest": out_dir / "manifest.json"}
    write_jsonl(paths["rows"], result.rows)
    if result.planted_rows:
        paths["planted"] = out_dir / "planted.jsonl"
        write_jsonl(paths["planted"], result.planted_rows)
    write_atomic(paths["manifest"],
                 (json.dumps(result.manifest, sort_keys=True, indent=2, ensure_ascii=False)
                  + "\n").encode("utf-8"))
    return paths
