"""reach.py - REACH AND COST PER CONDITION CLASS, with the content axis as a class of its own.

WHAT THE 19 OF 94 ACTUALLY IS. Packet E1 reported, on 100 LongMemEval haystacks, that 19 of 94
scored questions had a rung-(a)/(b) condition class that reached ALL their gold turns at a cost
below 1.0, and the class was ``anchor_resolved``. That number is not a method result and must
not be quoted as one: it is the size of the set of questions whose gold shares a CAPITALISED
NAME, A NUMBER OR A DATE with the question, because those are the only surfaces the extractor
roster mints and therefore the only things an anchor can resolve through (C.3: "an anchor is a
resolved typed row id, never a lexical occurrence at query time"). A question whose gold shares
only lowercase content words reached nothing, by construction, whatever the method.

So this module measures reach BY CAUSE: the same condition classes E1 measured, plus the class
the content axis makes possible, against the same gold and the same denominator.

  all                 the control: admit everything in jurisdiction. Reach 1.0 at cost 1.0, and
                      it isolates nothing - which is why reach is never reported without cost.
  anchor_resolved     E1's class, unchanged: the question's surfaces resolved through the anchor
                      index (``front/anchors.py``, the corrected instrument) and walked to the
                      DECLARED horizon.
  content_top_m       D.3's own acceptance measure, on the leaves this packet built: the top
                      m* = 49 leaves of the declared content axis, inside the question's
                      jurisdiction, mapped back to the carrier rows they observe. m* is FIXED BY
                      D.3 before any candidate is encoded and is not swept here.
  anchor_or_content   the union - what the system can reach once the leaf carries its content.

REACH IS MEANINGLESS WITHOUT COST and every class reports both, exactly as E1's instrument did.
A class isolates a question only where reach is 1.0 and cost is below 1.0.

AND AN ISOLATION COUNT IS MEANINGLESS WITHOUT ITS COST AND ITS JURISDICTION SIZE. Two classes
can both "isolate" a question while one admits 3% of the jurisdiction and the other 87% of it,
and the second is not a filter. Worse, a question whose jurisdiction |M| is at or below m* gets
its WHOLE mask back from the top-m* set - the typed condition did all the work, the encoder
contributed nothing, cost is exactly 1.0 - which is why D.3 declares its own check on a split
"where |M| >> m*". ``_summarise`` therefore counts those questions, reports the precondition met
only when there are none, reports each class's mean and median cost and its count of full-reach
questions at cost 1.0, and reports each class's isolation restricted to |M| > m* beside the
headline count. Added 2026-09-22 after an independent judge found a QASPER isolation count of
91 standing beside an unread mean cost of 0.84 and 62 questions whose jurisdiction IS the class.

LIFTED, NOT RE-AUTHORED: the gold joins and the reach/cost/isolation shape are
``src/atlas/record/measure.py`` as wave J2 deleted it (rung_a_reach :49-175, qasper_reach
:322-480, longmem_gold_rows :619-633, _paragraph_key :483-497), and the two symbols J2 kept -
``declared_walk_horizon`` and ``anchor_expansion`` - are IMPORTED from ``front/anchors.py``
rather than copied back, so there is one walk instrument and not two.

Complexity: O(T + G) host for the gold join; one [Q, N] matmul on the device for the content
class, with Q the questions and N the leaves - never an all-pairs object over rows.
"""

from __future__ import annotations

import json as _json
import time
from typing import Any, Mapping, Sequence

import numpy as np
import torch

from ..encoders.span_encoder import span_encoder
from ..record.content import axis_matrix
from ..record.device import require_device
from .anchors import anchor_expansion, declared_walk_horizon

__all__ = ["CLASSES", "M_STAR", "COVER_FLOOR", "longmem_reach", "qasper_reach"]

#: D.3, verbatim and before any candidate was encoded: "m* = 49 and cover_floor = 0.885". Both
#: are fixed by that clause and neither is swept here. They are read, not chosen.
M_STAR = 49
COVER_FLOOR = 0.885

CLASSES = ("all", "anchor_resolved", "content_top_m", "anchor_or_content")


def _mean(values: Sequence[float]) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 0.0


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    middle = len(ordered) // 2
    return (float(ordered[middle]) if len(ordered) % 2
            else (ordered[middle - 1] + ordered[middle]) / 2)


def _question_text(ingestion: Any, table: Any, position: int, column: str) -> str:
    """The question's own text, read from the RECORD at its declared span - not from the gold."""
    span_ord = int(table.column(column)[position])
    handle, start, end = ingestion.spans.address(span_ord)
    return str(_json.loads(ingestion.blobs.read(handle, start, end).decode("utf-8")))


def _resolved_anchor_rows(ingestion: Any, question_text: str) -> torch.Tensor:
    """Row ids the question's surfaces resolve to in the anchor index. LIFTED from measure.py."""
    anchors = ingestion.anchors
    device = require_device(ingestion.store.device)
    if anchors is None:
        return torch.empty(0, dtype=torch.int64, device=device)
    from ..record.extract import proper_nouns

    located = [item.surface for item in proper_nouns(question_text)]  # loop-ok: the located runs
    candidates = [question_text] + question_text.split() + located
    return anchors.resolve([text for text in candidates if text])  # loop-ok: the offered surfaces


class _ContentLens:
    """The declared content axis as a candidate proposer, and nothing more (D.1(i), D.3).

    It holds the leaves' STORED rows dequantised (D.7: the certificate is recomputed under the
    stored form, so the score is too), their carrier's local ordinal in the carrier table, and
    one batched query encode. It ranks candidates and stops; every typed condition, every
    operator and the answer itself stay with the rows.
    """

    __slots__ = ("vectors", "carrier_local", "encoder", "axis", "device", "seconds")

    def __init__(self, ingestion: Any, carrier_kind: str, device: torch.device) -> None:
        declaration = ingestion.declaration
        self.axis = declaration.content_axes[0]
        table = ingestion.content
        rows = axis_matrix(table, self.axis)
        kinds = [spec.kind for spec in declaration.row_kinds]  # loop-ok: the declared row kinds
        keep = np.flatnonzero(table.carrier_kind == kinds.index(carrier_kind))
        local_of = ingestion.store.local_of_global(carrier_kind)
        self.device = device
        self.vectors = torch.from_numpy(np.ascontiguousarray(rows[keep])).to(device)
        self.vectors = self.vectors / self.vectors.norm(dim=1, keepdim=True).clamp(min=1e-12)
        carrier = torch.from_numpy(np.ascontiguousarray(table.carrier_row[keep])).to(device)
        self.carrier_local = local_of.index_select(0, carrier)
        self.encoder = span_encoder(self.axis.encoder_id)
        self.seconds = 0.0

    def queries(self, texts: Sequence[str]) -> torch.Tensor:
        """ONE batched encode for every question of the dataset. O(total query tokens)."""
        started = time.perf_counter()
        matrix = self.encoder.embed(list(texts), role="query")
        self.seconds += time.perf_counter() - started
        return torch.from_numpy(np.ascontiguousarray(matrix)).to(self.device)

    def carriers_of_top_m(self, query: torch.Tensor, jurisdiction: torch.Tensor,
                          m_star: int = M_STAR) -> torch.Tensor:
        """The carrier rows of the top ``m_star`` leaves inside a mask. One matvec, one topk.

        ``jurisdiction`` is a boolean mask over the CARRIER table: D.3's measure is the top-m* of
        the MASKED candidate list, so the typed condition runs first and the vector ranks what
        survives it. Complexity: O(n d) device, no host transfer but the final gather.
        """
        live = jurisdiction.index_select(0, self.carrier_local.clamp(min=0))
        live &= self.carrier_local >= 0
        if not bool(live.any()):
            return torch.empty(0, dtype=torch.int64, device=self.device)
        scores = torch.where(live, self.vectors @ query,
                             torch.full((self.vectors.shape[0],), -float("inf"),
                                        device=self.device))
        take = int(min(m_star, int(live.sum())))
        chosen = torch.topk(scores, take).indices
        return torch.unique(self.carrier_local.index_select(0, chosen))


def _summarise(per_question: list[dict[str, Any]], classes: Sequence[str],
               extra: Mapping[str, Any]) -> dict[str, Any]:
    """Reach, cost, bytes and isolation per class, over the scored questions. O(Q * classes).

    D.3'S OWN PRECONDITION IS MEASURED HERE, not assumed. D.3 declares its check on a split
    "where |M| >> m*": the top-m* set is a proposal only where the question's jurisdiction M is
    much larger than m*. A question whose |M| <= m* gets the WHOLE mask back - the typed
    condition did all the work and the encoder contributed nothing - so its cost is exactly 1.0
    and it can neither isolate nor demonstrate anything about the axis. Those questions are
    counted (``jurisdiction.questions_at_or_below_m_star``), the precondition is reported met
    only when there are none of them, and every class additionally reports its isolation over
    the sub-population where |M| > m*, which is the quantity D.3 actually defines.
    """
    summary = {}
    isolation = {}
    isolation_above = {}
    cover = {}
    sizes = [int(row["jurisdiction_rows"]) for row in per_question]  # loop-ok: the scored questions
    above = [row for row in per_question
             if int(row["jurisdiction_rows"]) > M_STAR]  # loop-ok: the scored questions
    for name in classes:  # loop-ok: the declared condition classes
        reaches = [row[name]["reach"] for row in per_question]  # loop-ok: the scored questions
        costs = [row[name]["cost"] for row in per_question]  # loop-ok: the scored questions
        byte_counts = [row[name]["admitted_bytes"]
                       for row in per_question]  # loop-ok: the scored questions
        full = [row for row in per_question
                if row[name]["reach"] == 1.0]  # loop-ok: the scored questions
        full_costs = [row[name]["cost"] for row in full]  # loop-ok: the full-reach questions
        summary[name] = {"mean_reach": _mean(reaches), "mean_cost": _mean(costs),
                         "median_cost": _median(costs),
                         "mean_cost_of_full_reach_questions": _mean(full_costs),
                         "median_admitted_bytes": _median(byte_counts),
                         "questions_with_full_reach": len(full),
                         "questions_at_cost_1": len([row for row in full
                                                     if row[name]["cost"] >= 1.0])}  # loop-ok: the full-reach questions
        isolation[name] = len([row for row in full
                               if row[name]["cost"] < 1.0])  # loop-ok: the full-reach questions
        isolation_above[name] = len([row for row in above
                                     if row[name]["reach"] == 1.0
                                     and row[name]["cost"] < 1.0])  # loop-ok: the same questions
        cover[name] = len(full) / len(per_question) if per_question else 0.0
    at_or_below = len([size for size in sizes if size <= M_STAR])  # loop-ok: the scored questions
    out = {
        "questions": len(per_question),
        "m_star_D3": M_STAR, "cover_floor_D3": COVER_FLOOR,
        "by_condition_class": summary,
        "isolation": isolation,
        "isolation_where_jurisdiction_exceeds_m_star": isolation_above,
        "jurisdiction": {
            "rows_mean": _mean([float(size) for size in sizes]),  # loop-ok: the scored questions
            "rows_median": _median([float(size) for size in sizes]),  # loop-ok: as above
            "rows_min": min(sizes) if sizes else 0, "rows_max": max(sizes) if sizes else 0,
            "questions_at_or_below_m_star": at_or_below,
            "questions_above_m_star": len(above)},
        "d3_precondition": {
            "clause": ("D.3, quoted: 'the check is declared to run on the held-out benchmark "
                       "split where |M| >> m*'"),
            "m_star": M_STAR,
            "questions_at_or_below_m_star": at_or_below,
            "met": at_or_below == 0,
            "why": ("a question whose jurisdiction is at or below m* gets its whole mask back "
                    "from the top-m* set: cost 1.0, no isolation, and the CLASS IS THE MASK "
                    "rather than the encoder. Where any such question is scored the headline "
                    "isolation count must be read beside "
                    "'isolation_where_jurisdiction_exceeds_m_star'.")},
        "complete_evidence_cover": cover,
        "note": ("reach is meaningless without cost: 'all' reaches every gold row at cost 1.0 "
                 "and isolates nothing. A class isolates only where reach is 1.0 and cost is "
                 "below 1.0, and a cost just under 1.0 is a weak isolation - read every "
                 "isolation count beside its class's mean_cost. 'complete_evidence_cover' is "
                 "D.3's measure - the fraction of questions whose WHOLE gold set is inside the "
                 "class, WITHOUT a cost condition - against its own floor."),
        "_per_question": per_question,
    }
    out.update(extra)
    return out


def longmem_reach(opened: Any, gold: Any) -> dict[str, Any]:
    """Reach and cost per condition class on an ingested LongMemEval record. O(T + G + Q n d)."""
    ingestion = opened.ingestion if hasattr(opened, "ingestion") else opened
    store = ingestion.store
    device = require_device(store.device)
    turns, questions = store.table("turn"), store.table("question")
    if not len(turns) or not len(questions):
        return {"questions": 0}

    turn_qid = turns.decode("question_id")
    turn_sess = turns.column("session_index").tolist()
    turn_ix = turns.column("turn_index").tolist()
    locate = {(turn_qid[i], turn_sess[i], turn_ix[i]): i
              for i in range(len(turns))}  # loop-ok: one dictionary store per turn ROW

    span_columns = ingestion.spans.columns
    content = turns.column("content_span").to(torch.int64)
    content_bytes = (span_columns[:, 2] - span_columns[:, 1]).index_select(0, content)
    qid_code_of_turn = turns.column("question_id").to(torch.int64)
    question_qid = questions.decode("question_id")
    horizon = declared_walk_horizon(ingestion.declaration, "turn")

    has_content = (bool(ingestion.declaration.content_axes) and ingestion.content is not None
                   and len(ingestion.content) > 0)
    lens = _ContentLens(ingestion, "turn", device) if has_content else None
    texts = [_question_text(ingestion, questions, position, "text_span")
             for position in range(len(question_qid))]  # loop-ok: one span read per QUESTION
    query_matrix = lens.queries(texts) if lens is not None else None

    per_question: list[dict[str, Any]] = []
    for position, qid in enumerate(question_qid):  # loop-ok: one step per scored QUESTION
        code = int(questions.column("question_id")[position])
        in_jurisdiction = qid_code_of_turn == code
        total = int(in_jurisdiction.sum())
        gold_local = [locate[(qid, s, t)] for s, t in gold.gold_turns.get(qid, ())
                      if (qid, s, t) in locate]  # loop-ok: this question's gold annotations
        if not total or not gold_local:
            continue
        gold_mask = torch.zeros(len(turns), dtype=torch.bool, device=device)
        gold_mask[torch.tensor(gold_local, dtype=torch.int64, device=device)] = True

        resolved = _resolved_anchor_rows(ingestion, texts[position])
        expansion = anchor_expansion(ingestion, resolved, "turn", horizon)
        anchor_mask = torch.zeros(len(turns), dtype=torch.bool, device=device)
        reached = expansion["carrier_local"]
        if reached.numel():
            anchor_mask[reached] = True
        anchor_mask &= in_jurisdiction

        content_mask = torch.zeros(len(turns), dtype=torch.bool, device=device)
        if lens is not None and query_matrix is not None:
            carriers = lens.carriers_of_top_m(query_matrix[position], in_jurisdiction)
            if carriers.numel():
                content_mask[carriers] = True

        classes = {"all": in_jurisdiction, "anchor_resolved": anchor_mask,
                   "content_top_m": content_mask,
                   "anchor_or_content": anchor_mask | content_mask}
        gold_total = int(gold_mask.sum())
        row: dict[str, Any] = {"question_id": qid, "gold_turns": gold_total,
                               "turns_in_jurisdiction": total,
                               "jurisdiction_rows": total,   # the uniform name _summarise reads
                               "resolved_anchors": int(resolved.numel())}
        for name, mask in classes.items():  # loop-ok: the declared condition classes
            admitted = int(mask.sum())
            row[name] = {"reach": int((mask & gold_mask).sum()) / gold_total,
                         "cost": admitted / total,
                         "admitted_bytes": int(content_bytes[mask].sum())}
        per_question.append(row)

    golds = [row["gold_turns"] for row in per_question]  # loop-ok: the scored questions
    sizes = [row["turns_in_jurisdiction"] for row in per_question]  # loop-ok: as above
    extra = {"gold_turns_total": sum(golds), "turns_total": sum(sizes),
             "declared_walk_horizon": horizon,
             "content_axis": (None if lens is None else
                              {"axis": lens.axis.axis, "encoder_id": lens.axis.encoder_id,
                               "leaves": int(lens.vectors.shape[0]),
                               "query_encode_seconds": lens.seconds})}
    return _summarise(per_question, CLASSES, extra)


def _paragraph_key(paper_id: str, unit_id: str | None) -> tuple[str, int, int] | None:
    """A gold unit id -> this store's (paper_id, section_index, paragraph_index), or None."""
    from ..record.ingest.qasper import ABSTRACT_SECTION_INDEX

    if unit_id is None:
        return None
    tail = unit_id[len(f"qasper:{paper_id}:"):] if unit_id.startswith(
        f"qasper:{paper_id}:") else ""
    if tail == "abstract":
        return (paper_id, ABSTRACT_SECTION_INDEX, 0)
    if tail.startswith("s") and ":p" in tail:
        section, paragraph = tail[1:].split(":p", 1)
        if section.isdigit() and paragraph.isdigit():
            return (paper_id, int(section), int(paragraph))
    return None


def _qasper_gold_rows(ingestion: Any, split: str, repaired: bool
                      ) -> tuple[dict[str, list[int]], dict[str, str]]:
    """question id -> the local paragraph ordinals its gold names. LIFTED from measure.py."""
    from ..bench import gold_spans

    paragraphs = ingestion.store.table("paragraph")
    questions = ingestion.store.table("question")
    keys = zip(paragraphs.decode("paper_id"), paragraphs.column("section_index").tolist(),
               paragraphs.column("paragraph_index").tolist())
    locate = {(pid, si, pi): local
              for local, (pid, si, pi) in enumerate(keys)}  # loop-ok: one store per paragraph ROW
    paper_of_question = dict(zip(questions.decode("question_id"),
                                 questions.decode("paper_id")))
    by_paper: dict[str, list[str]] = {}
    for qid, pid in paper_of_question.items():  # loop-ok: one step per QUESTION
        by_paper.setdefault(pid, []).append(qid)
    raw = gold_spans.load_qasper_split(split)
    out: dict[str, list[int]] = {}
    for paper_id, qids in by_paper.items():  # loop-ok: one step per PAPER of the draw
        paper = raw.get(paper_id)
        if paper is None:
            continue
        image = gold_spans.qasper_paper_image(paper_id, paper)
        unit_of_span = {unit.span: unit.unit_id
                        for unit in image.units}  # loop-ok: one paper's units
        gold = gold_spans.qasper_gold(paper_id, paper, image, qids, repaired=repaired)
        for qid, evidence in gold.items():  # loop-ok: this paper's questions
            found: set[int] = set()
            for alternative in evidence.alternatives:  # loop-ok: the gold alternatives
                for requirement in alternative.requirements:  # loop-ok: one alternative's units
                    for address in requirement.addresses:  # loop-ok: one requirement's addresses
                        key = _paragraph_key(paper_id, unit_of_span.get(address))
                        if key is not None and key in locate:
                            found.add(locate[key])
            if found:
                out[qid] = sorted(found)
    return out, {"gold_map": "repaired" if repaired else "legacy",
                 "gold_map_source": f"atlas.bench.gold_spans.qasper_gold(repaired={repaired})"}


def qasper_reach(opened: Any, split: str = "dev", *, repaired: bool = True) -> dict[str, Any]:
    """Reach and cost per condition class on an ingested QASPER record. O(P + G + Q n d)."""
    ingestion = opened.ingestion if hasattr(opened, "ingestion") else opened
    store = ingestion.store
    device = require_device(store.device)
    paragraphs, questions = store.table("paragraph"), store.table("question")
    if not len(paragraphs) or not len(questions):
        return {"questions": 0}

    gold_rows, provenance = _qasper_gold_rows(ingestion, split, repaired)
    span_columns = ingestion.spans.columns
    text = paragraphs.column("text_span").to(torch.int64)
    paragraph_bytes = (span_columns[:, 2] - span_columns[:, 1]).index_select(0, text)
    paragraph_pid = paragraphs.column("paper_id").to(torch.int64)
    question_qid = questions.decode("question_id")
    question_pid = questions.column("paper_id").to(torch.int64)
    horizon = declared_walk_horizon(ingestion.declaration, "paragraph")

    has_content = (bool(ingestion.declaration.content_axes) and ingestion.content is not None
                   and len(ingestion.content) > 0)
    lens = _ContentLens(ingestion, "paragraph", device) if has_content else None
    texts = [_question_text(ingestion, questions, position, "text_span")
             for position in range(len(question_qid))]  # loop-ok: one span read per QUESTION
    query_matrix = lens.queries(texts) if lens is not None else None

    per_question: list[dict[str, Any]] = []
    for position, qid in enumerate(question_qid):  # loop-ok: one step per scored QUESTION
        gold_local = gold_rows.get(qid)
        in_jurisdiction = paragraph_pid == int(question_pid[position])
        total = int(in_jurisdiction.sum())
        if not gold_local or not total:
            continue
        gold_mask = torch.zeros(len(paragraphs), dtype=torch.bool, device=device)
        gold_mask[torch.tensor(gold_local, dtype=torch.int64, device=device)] = True

        resolved = _resolved_anchor_rows(ingestion, texts[position])
        expansion = anchor_expansion(ingestion, resolved, "paragraph", horizon)
        anchor_mask = torch.zeros(len(paragraphs), dtype=torch.bool, device=device)
        reached = expansion["carrier_local"]
        if reached.numel():
            anchor_mask[reached] = True
        anchor_mask &= in_jurisdiction

        content_mask = torch.zeros(len(paragraphs), dtype=torch.bool, device=device)
        if lens is not None and query_matrix is not None:
            carriers = lens.carriers_of_top_m(query_matrix[position], in_jurisdiction)
            if carriers.numel():
                content_mask[carriers] = True

        classes = {"all": in_jurisdiction, "anchor_resolved": anchor_mask,
                   "content_top_m": content_mask,
                   "anchor_or_content": anchor_mask | content_mask}
        gold_total = int(gold_mask.sum())
        row: dict[str, Any] = {"question_id": qid, "gold_paragraphs": gold_total,
                               "paragraphs_in_jurisdiction": total,
                               "jurisdiction_rows": total,   # the uniform name _summarise reads
                               "resolved_anchors": int(resolved.numel())}
        for name, mask in classes.items():  # loop-ok: the declared condition classes
            admitted = int(mask.sum())
            row[name] = {"reach": int((mask & gold_mask).sum()) / gold_total,
                         "cost": admitted / total,
                         "admitted_bytes": int(paragraph_bytes[mask].sum())}
        per_question.append(row)

    golds = [row["gold_paragraphs"] for row in per_question]  # loop-ok: the scored questions
    sizes = [row["paragraphs_in_jurisdiction"] for row in per_question]  # loop-ok: as above
    extra: dict[str, Any] = {
        "gold_paragraphs_total": sum(golds), "paragraphs_total": sum(sizes),
        "declared_walk_horizon": horizon,
        "content_axis": (None if lens is None else
                         {"axis": lens.axis.axis, "encoder_id": lens.axis.encoder_id,
                          "leaves": int(lens.vectors.shape[0]),
                          "query_encode_seconds": lens.seconds})}
    extra.update(provenance)
    return _summarise(per_question, CLASSES, extra)
