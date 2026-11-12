"""question.py - the DECLARED question, and the compiler that turns it into typed conditions.

A query, in the charter's own words, is "a declared observable plus a budget: per-fibre
directions, typed exact conditions that MASK rows (date, id, kind, polarity, claim,
jurisdiction), operators over typed fields (order, count, compare, distinct), k and a byte
budget, and the fibre's price". This module is that object and nothing else: it holds no answer,
no score, no embedding and no ranking. The read (``read.py``) is what executes it.

THREE CLOSED SETS, and extending any of them is a declared, versioned, measurement-forced
addition (the charter's rule for its own closed sets):

  CONDITION KINDS   exactly ``ranges.admits``'s five - equality, membership, day, day_interval,
                    count_threshold - because a condition that the range reductions cannot
                    answer is a condition the frontier read cannot decide, and a read that
                    cannot decide a condition must not be given it.
  OPERATORS         five: first_by, latest_by, count_distinct, distinct_values, exists. Each is
                    a REDUCTION over the answer column of the admitted rows, which is what lets
                    an answer come from a range the read never opened.
  DERIVED CONDITION SETS  three, each a B.7 typed-field predicate over DECLARED columns computed
                    at compile time from the record alone, with its provenance on the compiled
                    object: the live claim set (a claim with a negated row is refuted), the
                    anchor-reached set (the surfaces of the question, resolved through the
                    anchor index and walked to the DECLARED horizon), and the as-of day (the
                    record's own latest declared date - never the clock).

NOTHING HERE IS FITTED OR TUNED. A tolerance is DERIVED from the declared answer precision
(L7: "tolerances derived from the declared answer precision and budget, not hand-set") and the
three tolerances the read is measured at are three DIFFERENT declared answer precisions, each
with its derivation string, not one number times three constants.

THE TYPED PLAN SHAPE. ``as_query_plan`` emits atlas.front.question/2 using the
unchanged canonical reconstruction dataclasses. Conditions are exact dataset
ContextBinding declarations, not English ClaimObligation objects. Actual literal
occurrences alone get lexical spans; absent or derived vocabulary is still a typed
condition. Record-sized runtime codes remain in the exact live CompiledQuestion,
with an explicitly non-replayable reference in the bounded serialized projection.
No historical English compiler or semantic parser is invoked.

Complexity: O(rows of the answering kind) device work per derived set; O(1) per condition.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Sequence


from .lift import lifted

__all__ = ["Condition", "Operator", "QuestionSpec", "CompiledQuestion", "QuestionRefusal",
           "CONDITION_KINDS", "OPERATORS", "compile_question", "as_query_plan",
           "as_obligation_plan", "toy_questions", "engine_questions", "longmem_questions",
           "qasper_questions", "TOLERANCE_LADDER", "OBSERVABLE_RANGE"]

CONDITION_KINDS = ("equality", "membership", "day", "day_interval", "count_threshold")
OPERATORS = ("first_by", "latest_by", "count_distinct", "distinct_values", "exists")


class QuestionRefusal(ValueError):
    def __init__(self, refusal: str, **context: Any) -> None:
        self.refusal = refusal
        self.context = context
        super().__init__(f"{refusal}: {context}")


@dataclass(frozen=True, slots=True)
class Condition:
    """ONE typed exact condition on ONE declared column of ONE declared row kind.

    ``surfaces`` are declared record vocabulary, which may not occur literally in
    the question text; they are resolved to
    the column's codes at compile time and a surface outside the vocabulary is refused, never
    dropped. ``derived`` names the derived set a membership condition was built from, so a
    condition that came from the record rather than from the question text says so.
    """

    kind: str
    row_kind: str
    column: str
    surfaces: tuple[str, ...] = ()
    day: str | None = None
    lo_day: str | None = None
    hi_day: str | None = None
    threshold: int | None = None
    op: str = ">="
    derived: str = ""
    why: str = ""

    def __post_init__(self) -> None:
        if self.kind not in CONDITION_KINDS:
            raise QuestionRefusal("QUESTION-CONDITION-KIND-NOT-ADMITTED", kind=self.kind,
                                  admitted=list(CONDITION_KINDS))

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "row_kind": self.row_kind, "column": self.column,
                "surfaces": list(self.surfaces), "day": self.day, "lo_day": self.lo_day,
                "hi_day": self.hi_day, "threshold": self.threshold, "op": self.op,
                "derived": self.derived, "why": self.why}


@dataclass(frozen=True, slots=True)
class Operator:
    """One of the five declared operators over TYPED fields - order, count, compare, distinct."""

    name: str
    answer_column: str
    order_column: str = ""

    def __post_init__(self) -> None:
        if self.name not in OPERATORS:
            raise QuestionRefusal("QUESTION-OPERATOR-NOT-ADMITTED", operator=self.name,
                                  admitted=list(OPERATORS))

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "answer_column": self.answer_column,
                "order_column": self.order_column}


@dataclass(frozen=True, slots=True)
class QuestionSpec:
    """A declared question of a dataset: its text, its typed conditions, its operator, its
    budget, and - for a known-answer corpus - the answer the FIXTURE states, with the row source
    that states it. The known answer is never consulted by the read; it is compared against
    afterwards, by the door's gate."""

    qid: str
    text: str
    dataset_id: str
    row_kind: str
    conditions: tuple[Condition, ...]
    operator: Operator
    byte_budget: int
    anchor_surfaces: tuple[str, ...] = ()
    walk_hops: int = 0
    live_claim_column: str = ""
    as_of_column: str = ""
    interval_columns: tuple[str, str] = ("", "")
    known_answer: Any = None
    known_answer_source: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"qid": self.qid, "text": self.text, "dataset_id": self.dataset_id,
                "row_kind": self.row_kind, "byte_budget": self.byte_budget,
                "conditions": [c.as_dict() for c in self.conditions],  # loop-ok: the question's own declared condition list
                "operator": self.operator.as_dict(),
                "anchor_surfaces": list(self.anchor_surfaces), "walk_hops": self.walk_hops,
                "live_claim_column": self.live_claim_column, "as_of_column": self.as_of_column,
                "interval_columns": list(self.interval_columns),
                "known_answer": _jsonable(self.known_answer),
                "known_answer_source": self.known_answer_source}


FRONT_PLAN_VERSION = "atlas.front.question/2"


def _compiled_reference(compiled: "CompiledQuestion", index: int, field: str) -> dict:
    """A label inside this exact live object, never a cross-record replay resolver."""
    return {"compiled_ref": {"dataset_id": compiled.spec.dataset_id,
                             "qid": compiled.spec.qid, "condition_index": index,
                             "field": field},
            "availability": "live_compiled_question_only"}


def _condition_payload(compiled: "CompiledQuestion", index: int) -> dict:
    entry = compiled.coded[index]
    payload = dict(entry["payload"])
    if entry["condition"].derived == "live_claims" and "codes" in payload:
        payload["codes"] = _compiled_reference(compiled, index, "payload.codes")
    return payload


def _reported_codes(compiled: "CompiledQuestion", index: int) -> Any:
    entry = compiled.coded[index]
    if entry["condition"].derived == "live_claims" and entry.get("codes") is not None:
        return _compiled_reference(compiled, index, "codes")
    return entry.get("codes")


def as_query_plan(compiled: "CompiledQuestion") -> Any:
    """Project declared conditions without pretending to parse the question's English.

    Existing ContextBinding objects carry each exact typed declaration and scalar
    compiled payload. Record-sized derived codes stay in the executable CompiledQuestion;
    their JSON reference is usable only with that same live object, not a replay recipe.
    Only literal occurrences get LexicalCandidate/TextSpan objects. No condition becomes
    an English ClaimObligation. Shared reconstruction dataclasses remain unchanged.

    Complexity: O(declared conditions + literal searches + emitted occurrences), with
    no tensor materialization or record traversal. Historical /1 output is not rewritten.
    """
    from ..ids import canonical_json
    from ..errors import NotCanonicalizable

    qp = lifted("query_plan")
    text = compiled.spec.text
    candidates, context = [], []

    def lexical(surfaces, key):
        for surface_index, surface in enumerate(surfaces):
            if not isinstance(surface, str) or not surface:
                continue
            start = text.find(surface)
            occurrence = 0
            while start >= 0:
                end = start + len(surface)
                candidates.append(qp.LexicalCandidate(
                    id=f"x-{key}:{surface_index}:{occurrence}", surface=surface,
                    kind="rare_term", source_binding_id=None,
                    asserted_semantic_truth=False, span=qp.TextSpan(start, end)))
                occurrence += 1
                start = text.find(surface, start + 1)

    for index, entry in enumerate(compiled.coded):
        condition = entry["condition"]
        # condition_index addresses compiled.coded, which also contains appended
        # derived conditions; it is deliberately not an index in spec.conditions.
        value = {"declaration": condition.as_dict(),
                 "payload": _condition_payload(compiled, index)}
        try:
            encoded = canonical_json(value)
        except NotCanonicalizable as exc:
            raise QuestionRefusal("QUESTION-DECLARATION-NOT-ENCODABLE",
                                  condition_index=index) from exc
        context.append(qp.ContextBinding(
            id=f"k-condition:{index}", namespace=compiled.spec.dataset_id,
            field=f"{entry['row_kind']}.{entry['column']}", value=encoded,
            role="exact", scope="question", binding_key=f"condition:{index}",
            resolution="provided"))
        lexical(condition.surfaces, f"condition:{index}")
    if "live_claims" in compiled.derived:
        provenance = compiled.derived["live_claims"]
        context.append(qp.ContextBinding(
            id="k-live-claims", namespace=compiled.spec.dataset_id,
            field=provenance["claim_column"], value=str(provenance["claims_live"]),
            role="exact", scope="question", binding_key="live_claims",
            resolution="provided"))
    if compiled.anchor.get("surfaces"):
        context.append(qp.ContextBinding(
            id="k-anchor", namespace=compiled.spec.dataset_id, field="anchor_index",
            value=canonical_json({"surfaces": compiled.anchor["surfaces"],
                                  "resolved": compiled.anchor.get("resolved", 0)}),
            role="exact", scope="question", binding_key="anchor_reached",
            resolution="provided" if compiled.anchor.get("resolved") else "unresolved"))
        lexical(compiled.anchor["surfaces"], "anchor")
    obligation = qp.EvidenceObligation(
        id="e0", facet_text=text, source_binding_ids=(), publication_date_ids=(),
        event_date_ids=(), context_binding_ids=tuple(c.id for c in context),
        claim_ids=(), lexical_candidate_ids=tuple(c.id for c in candidates),
        span=qp.TextSpan(0, len(text)))
    unresolved = compiled.anchor.get("surfaces") and not compiled.anchor.get("resolved")
    return qp.QueryPlan(
        version=FRONT_PLAN_VERSION, question=text,
        status="ambiguous" if unresolved else "supported",
        source_bindings=(), dates=(), context_bindings=tuple(context),
        claims=(), lexical_candidates=tuple(candidates), evidence_obligations=(obligation,),
        logic=(), identity=(), binding_alternatives=(), issues=())


def as_obligation_plan(compiled: "CompiledQuestion", plan: Any) -> Any:
    """The same compiled question in the LIFTED OBLIGATION shape - ``query_obligations.py``.

    Its INVENTORY row is REUSE_WITH_FIX and its ``literals`` and ``bypasses`` entries both name
    the same thing: ``query_obligations.compile_query`` runs the v1 English parser and then a
    connector grammar with a hardcoded English vocabulary, and attaches a sole binding to every
    clause whether or not the source is inside it. THAT ENTRY IS NOT REACHED, and it is not
    reached for a reason this packet can state: a hardcoded English noun vocabulary on the read
    path is the charter's first forbidden move (a literal that resolves to no declared row), so
    joining the parser would be a defect, not a join.

    What IS joined is the module's typed object set, used exactly as ``as_query_plan`` uses
    ``query_plan``'s: ``ObligationPlan`` is built here as the v2 statement of what this question
    obliges, and ``AttachmentConstraint`` carries the one thing the record-built plan can leave
    unresolved - a declared anchor surface that resolved to no row, which is an attachment the
    record could not license. The status ladder is the module's own three-valued one.

    Complexity: O(conditions + surfaces).
    """
    qo = lifted("query_obligations")
    attachments = []
    surfaces = compiled.anchor.get("surfaces") or []
    if surfaces and not compiled.anchor.get("resolved"):
        attachments.append(qo.AttachmentConstraint(
            id="attachment:0", relation="anchor_surface_unresolved",
            member_ids=tuple(o.id for o in plan.evidence_obligations),  # loop-ok: the one evidence obligation of a compiled question
            status="unresolved", cue=", ".join(surfaces), shared_text=tuple(surfaces),
            recovery_text=compiled.spec.text))
    issues = tuple(
        f"anchor surface resolved to no row: {s}" for s in (surfaces if attachments else ()))  # loop-ok: the question's own surfaces
    return qo.ObligationPlan(
        "atlas.front.obligations/2", compiled.spec.text,
        ("unsupported" if attachments else plan.status),
        plan.source_bindings, plan.dates, plan.context_bindings, plan.claims,
        plan.lexical_candidates, plan.evidence_obligations, plan.logic, plan.identity,
        plan.binding_alternatives, tuple(attachments), issues)


def _jsonable(value: Any) -> Any:
    if isinstance(value, (set, frozenset)):
        return sorted(str(v) for v in value)
    return value


@dataclass(frozen=True, slots=True)
class CompiledQuestion:
    """What the read executes: conditions with their CODES, the answer and order columns, the
    tolerance ladder, the byte budget, and the receipt of what compiling cost.

    ``coded`` is one entry per condition: the condition, its ``ranges.admits`` payload (already
    in codes), and the row kind and column its face must be reduced from.
    """

    spec: QuestionSpec
    coded: tuple[dict[str, Any], ...]
    tolerances: tuple[dict[str, Any], ...]
    anchor: dict[str, Any]
    derived: dict[str, Any]
    seconds: float
    # C1 (P3-THE-READ): THE QUESTION'S OWN GATE, beside the declared control ladder.
    # ``question_tau`` is ruling R-i's tau = eps_answer * sqrt(1/b - 1) at ``reference_mass`` b -
    # the mass the AND of this question's coded conditions admits under the LENS'S OWN DERIVED
    # pi - and it is what the read descends on. The four-rung ladder above is RETAINED as the
    # declared control (the ablation switch), not as the read's tolerance.
    question_tau: float = 0.0
    reference_mass: float = 0.0
    gate_derivation: str = ""
    direction_axis: str = ""

    def payloads(self) -> list[dict[str, Any]]:
        return [entry["payload"] for entry in self.coded]  # loop-ok: the question's own condition list

    def as_dict(self) -> dict[str, Any]:
        return {"typed_projection_version": FRONT_PLAN_VERSION, "spec": self.spec.as_dict(),
                "coded": [{"row_kind": e["row_kind"], "column": e["column"],
                           "kind": e["payload"]["kind"],
                           "codes": _reported_codes(self, index), "derived": e["condition"].derived}
                          for index, e in enumerate(self.coded)],  # loop-ok: the compiled condition list
                "tolerances": list(self.tolerances),
                # the two tensors (the seed rows and the reached rows) are the compiled object's
                # working state, not its statement; the COUNTS of both are already here and the
                # rows themselves are reachable through the answer's range handles.
                "anchor": {k: v for k, v in self.anchor.items()
                           if k not in ("reached_rows", "seed_rows")},  # loop-ok: the anchor block's own keys
                "derived": {k: v for k, v in self.derived.items()
                            if k != "live_claim_codes"},  # loop-ok: the derived block's own keys
                "derived_live_claim_codes": len(self.derived.get("live_claim_codes", [])),
                "question_tau": self.question_tau,
                "reference_mass": self.reference_mass,
                "gate_derivation": self.gate_derivation,
                "direction_axis": self.direction_axis,
                "seconds": self.seconds}


# --------------------------------------------------------------------- the tolerance ladder
TOLERANCE_LADDER = (
    ("one_row_of_the_answering_kind",
     "tau = 1/M with M the rows of the ANSWERING row kind in this record: the answer to this "
     "question is a value read off one row of that kind, so the strictest honest demand is that "
     "the read may misplace the mass of at most one such row. Same derivation as the lens's own "
     "eps_a (grading/lenses.py EPS_DERIVATION), applied to the QUESTION instead of the lens - "
     "which is the distinction the J1 synthesis' seams[9] says the read has to decide."),
    ("one_row_of_the_carrier",
     "tau = 1/M_carrier with M_carrier every bound carrier row of the lens: the demand a "
     "question makes when it asks about the carrier as a whole rather than about one answering "
     "row. Strictly looser than the first whenever the carrier is larger than the answering "
     "kind, which is the normal case."),
    ("the_observables_whole_range",
     "tau = 1: the DECLARED OBSERVABLE'S OWN RANGE, and therefore the coarsest FINITE demand a "
     "question can make. A.11's observables are masses under the reference measure - "
     "tree._range_observable computes the residual as sqrt(cell_mass - cell_mass^2 / sub_mass) "
     "over pi, which sums to one - so an answer read off them lies in [0, 1] and can never be "
     "wrong by more than 1. A bound at or below 1 still asserts something about the answer; any "
     "tau above 1 asserts exactly what tau = infinity asserts, namely nothing. It is in the "
     "ladder because the judge of the first pass measured that the two ROW-scale precisions, "
     "6.1x apart in tau, give byte-identical splits on every lens: a ladder whose only moving "
     "rung is the degenerate one cannot show the tolerance deciding, and this rung is the one "
     "the observable's own declared range supplies - derived, not chosen to separate."),
    ("no_distinction_demanded",
     "tau = infinity: the coarsest possible demand, which decides every range at the root. It is "
     "in the ladder because it is the control for the other three - if they give the same "
     "decided/excluded/open split then the tolerance is carrying no information at all, which is "
     "exactly what the J1 synthesis could not tell."),
)

# A.11's observables are masses under the reference measure, so their whole declared range is 1.
# This is a DERIVED constant of the observable, not a dial: change the observable's declared range
# and this changes with it; it is stated here once so no call site can invent a different one.
OBSERVABLE_RANGE = 1.0


def _tolerance_ladder(rows_of_answer_kind: int, carrier_rows: int) -> tuple[dict[str, Any], ...]:
    values = (1.0 / max(rows_of_answer_kind, 1), 1.0 / max(carrier_rows, 1), OBSERVABLE_RANGE,
              float("inf"))
    return tuple({"name": name, "tau": value, "derivation": derivation}
                 for (name, derivation), value in zip(TOLERANCE_LADDER, values))  # loop-ok: the declared answer precisions, three finite and one control


# --------------------------------------------------------------------- the compiler
def _code_of(table: Any, column: str, surface: str) -> int:
    if column not in table.spec.columns:
        raise QuestionRefusal("QUESTION-COLUMN-NOT-DECLARED", column=column,
                              row_kind=table.spec.kind, declared=list(table.spec.columns))
    code = table.surface_code(column, surface)
    if code is None:
        raise QuestionRefusal("QUESTION-SURFACE-NOT-IN-VOCABULARY", column=column,
                              surface=surface, row_kind=table.spec.kind)
    return int(code)


def _live_claims(table: Any, claim_column: str, polarity_column: str,
                 negated_surface: str) -> tuple[list[int], dict[str, Any]]:
    """B.7 typed-field predicate over DECLARED columns: the claim codes NO row negates.

    This is the "claim" mask the charter's query definition names, and it is the reason Q4's
    answer is False and Q3's is not Leeds: an asserted row whose CLAIM a later row negates is
    refuted, and no condition on ``polarity`` alone can see that, because the refuting row is a
    different row. Vectorised: one mask, one unique, one set difference. O(rows).
    """
    import torch
    from ..record.columns import NULL_OF
    claims = table.column(claim_column)
    polarity = table.column(polarity_column)
    negated_code = table.surface_code(polarity_column, negated_surface)
    null = NULL_OF[claims.dtype]
    declared = claims != null
    all_claims = torch.unique(claims[declared])
    if negated_code is None:
        refuted = torch.empty(0, dtype=all_claims.dtype, device=all_claims.device)
    else:
        refuted = torch.unique(claims[declared & (polarity == int(negated_code))])
    live = all_claims[~torch.isin(all_claims, refuted)]
    return ([int(c) for c in live.tolist()],  # loop-ok: the surviving claim codes, a declared vocabulary slice
            {"predicate": "B.7 typed_field_predicate: a claim code with any row of polarity "
                          f"'{negated_surface}' is REFUTED and every row carrying it is excluded",
             "claim_column": claim_column, "claims_declared": int(all_claims.numel()),
             "claims_refuted": int(refuted.numel()), "claims_live": int(live.numel())})


def _as_of_day(table: Any, column: str) -> tuple[int, dict[str, Any]]:
    """The record's OWN latest declared day in ``column`` - never the clock (the charter's own
    rule for relative dates: resolved against the row's declared time). O(rows)."""
    from ..record.columns import NULL_OF
    values = table.column(column)
    null = NULL_OF[values.dtype]
    declared = values[values != null]
    if not declared.numel():
        raise QuestionRefusal("QUESTION-AS-OF-COLUMN-EMPTY", column=column,
                              row_kind=table.spec.kind)
    day = int(declared.max())
    return day, {"as_of_column": column, "as_of_day_key": day,
                 "derivation": "the record's own latest declared value of this date column; "
                               "the clock is never read"}


def rarest_declared(opened: Any, row_kind: str, column: str) -> tuple[str, dict[str, Any]]:
    """The record's own RAREST declared value of one column - a SELECTIVE condition, derived.

    S4B of the theory manuscript proves that a FIXED cutoff prunes from the root while a moving
    one cannot, so a question only exercises the hierarchy when its condition is satisfied by a
    small fraction of the rows. It must not be satisfied by a hand-picked literal either (the
    charter's forbidden move 1), so the value is MEASURED on the record: one ``bincount`` over
    the column's codes, the smallest positive count wins, ties go to the lowest code so the
    choice is deterministic. Complexity: O(N) on the device, one D2H of a single code.

    Returns (the surface as the record spells it, the derivation with its own counts).
    """
    import torch
    from ..record.columns import NULL_OF
    table = opened.ingestion.store.table(row_kind)
    if column not in table.spec.columns:
        raise QuestionRefusal("QUESTION-COLUMN-NOT-DECLARED", column=column, row_kind=row_kind,
                              declared=list(table.spec.columns))
    values = table.column(column)
    null = NULL_OF[values.dtype]
    declared = values[values != null].to(torch.int64)
    if not declared.numel():
        raise QuestionRefusal("QUESTION-RAREST-COLUMN-EMPTY", column=column, row_kind=row_kind)
    counts = torch.bincount(declared)
    present = torch.nonzero(counts > 0, as_tuple=False).flatten()
    code = int(present[int(torch.argmin(counts.index_select(0, present)))])
    hits = int(counts[code])
    vocabulary = table.vocabulary(column)
    surface = vocabulary[code] if vocabulary else str(code)
    return surface, {
        "column": column, "row_kind": row_kind, "surface": surface,
        "rows_carrying_it": hits, "rows_of_the_kind": int(len(table)),
        "distinct_declared_values": int(present.numel()),
        "selectivity": hits / max(int(len(table)), 1),
        "derivation": "the record's own least frequent declared value of this column, by one "
                      "bincount over its codes; ties go to the lowest code. Nothing is chosen "
                      "by hand and nothing is tuned on an outcome (S4B: a fixed cutoff prunes "
                      "from the root, so a question must be selective to exercise the tree)"}


def compile_question(spec: QuestionSpec, opened: Any, lens: Any,
                     carrier_rows: int, *, loaded: Any = None,
                     columns: Any = None) -> CompiledQuestion:
    """Compile a declared question against THIS record: codes, derived sets, tolerances.

    No corpus traversal, no embedding, no answer access (the lifted ``query_plan.compile_query``
    states that contract in its own docstring and this is the same discipline against a record).
    Every surface is resolved through the record's own dictionaries, so the compiled object is a
    pure function of (question, record) and a question that names something the record does not
    declare is refused by name here rather than answered with an empty mask.

    Complexity: O(rows of the answering kind) for the derived sets, O(1) per condition.
    """
    import time

    started = time.perf_counter()
    store = opened.ingestion.store
    table = store.table(spec.row_kind)
    coded: list[dict[str, Any]] = []
    derived: dict[str, Any] = {}

    conditions = list(spec.conditions)
    if spec.live_claim_column:
        live, provenance = _live_claims(table, spec.live_claim_column, "polarity", "negated")
        derived["live_claims"] = provenance
        conditions.append(Condition("membership", spec.row_kind, spec.live_claim_column,
                                    derived="live_claims",
                                    why=provenance["predicate"]))
        derived["live_claim_codes"] = live
    as_of = None
    if spec.as_of_column:
        as_of, provenance = _as_of_day(table, spec.as_of_column)
        derived["as_of"] = provenance

    anchor = _resolve_anchors(spec, opened)
    if anchor["reached_rows"] is not None:
        derived["anchor_reached"] = {k: v for k, v in anchor.items()
                                     if k not in ("reached_rows", "seed_rows")}

    for condition in conditions:  # loop-ok: the question's own declared condition list
        entry: dict[str, Any] = {"condition": condition, "row_kind": condition.row_kind,
                                 "column": condition.column}
        if condition.kind == "equality":
            code = _code_of(table, condition.column, condition.surfaces[0])
            entry["payload"] = {"kind": "equality", "code": code}
            entry["codes"] = [code]
        elif condition.kind == "membership":
            if condition.derived == "live_claims":
                codes = derived["live_claim_codes"]
            else:
                codes = [_code_of(table, condition.column, s)
                         for s in condition.surfaces]  # loop-ok: the condition's own declared surface list
            entry["payload"] = {"kind": "membership", "codes": codes}
            entry["codes"] = codes
        elif condition.kind == "count_threshold":
            code = _code_of(table, condition.column, condition.surfaces[0])
            entry["payload"] = {"kind": "count_threshold", "code": code,
                                "threshold": int(condition.threshold or 0), "op": condition.op}
            entry["codes"] = [code]
        else:
            lo = condition.lo_day or condition.day
            hi = condition.hi_day or condition.day
            payload = ({"kind": "day", "day": _day_key_of(lo, as_of)}
                       if condition.kind == "day" else
                       {"kind": "day_interval", "lo_day": _day_key_of(lo, as_of),
                        "hi_day": _day_key_of(hi, as_of)})
            entry["payload"] = payload
            entry["codes"] = None
        coded.append(entry)

    rows_of_answer_kind = int(len(table))
    compiled = CompiledQuestion(
        spec=spec, coded=tuple(coded),
        tolerances=_tolerance_ladder(rows_of_answer_kind, carrier_rows),
        anchor=anchor, derived=derived, seconds=time.perf_counter() - started)
    # THE GATE REPLACES THE LADDER AT ITS SOLE CALL SITE (C1). eps_answer is this question's own
    # declared answer precision - the ladder's first rung, 1/M of the ANSWERING row kind, with
    # the derivation lenses.EPS_DERIVATION states - and b is the reference mass the AND of the
    # coded conditions admits under the lens's OWN derived pi (B.19), measured here on the loaded
    # lens rather than assumed. Where the caller passes no loaded lens (a compile with no open
    # tree), b falls back to the CARRIER-row share, which is the same quantity under the uniform
    # reference and is labelled as such in the derivation.
    tau, mass, why = _question_gate(compiled, opened, loaded, columns, rows_of_answer_kind,
                                    carrier_rows)
    axis = ""
    axes = getattr(opened.ingestion.declaration, "content_axes", ())
    if axes:
        axis = str(axes[0].axis)
    return replace(compiled, question_tau=tau, reference_mass=mass, gate_derivation=why,
                   direction_axis=axis)


def _question_gate(compiled: "CompiledQuestion", opened: Any, loaded: Any, columns: Any,
                   rows_of_answer_kind: int, carrier_rows: int) -> tuple[float, float, str]:
    """Ruling R-i: tau = eps_answer * sqrt(1/b - 1) at the question's OWN condition mass.

    ``down.py:69-88 question_gate``'s arithmetic, lifted into the compiler where the brief puts
    it. O(rows of the conditioned columns).
    """
    import torch
    import math

    epsilon = 1.0 / max(rows_of_answer_kind, 1)
    mass = 1.0
    source = "the carrier-row share under the uniform reference (no loaded lens was passed)"
    if loaded is not None and columns is not None and getattr(loaded, "rank_pi", None) is not None:
        from . import read as _RD

        admitted = torch.ones(loaded.rows, dtype=torch.bool, device=loaded.rank_pi.device)
        # b IS THE MASS THE CONDITIONS ADMIT, read off the RANKED COLUMNS the read itself reads.
        # ``_satisfies`` is the read's own per-condition predicate over rank positions
        # (read.py:232-256, the only place a read may interpret a declared null); the AND of them
        # over the lens's whole rank order is the conditioning event, and pi summed over it is b.
        # (The first form of this call asked ``_face_for`` for a FrontierFace, which is a
        # per-RANGE count table of a frontier and not a per-position mask, with ``opened`` in the
        # boundary argument's place - it raised AttributeError: '_Opened' object has no attribute
        # 'numel' at faces.py:479 on every question of the door's answer stage.)
        for entry in _RD._entries(compiled, columns):  # loop-ok: this question's own conditions
            ranked = entry["ranked"]
            if ranked is None:
                continue
            admitted = admitted & _RD._satisfies(entry, ranked, entry["null"])[:loaded.rows]
        total = float(loaded.rank_pi.sum())
        mass = float(loaded.rank_pi[admitted].sum()) / total if total > 0 else 1.0
        source = ("the LENS'S OWN derived reference measure pi (B.19), summed over the rank "
                  "positions the AND of this question's coded conditions admits")
    mass = min(max(mass, 1.0 / max(carrier_rows, 1)), 1.0)
    chi = math.sqrt(max(1.0 / mass - 1.0, 0.0))
    tau = epsilon * chi
    return tau, mass, (
        f"tau = eps_answer * sqrt(1/b - 1) = {epsilon!r} * {chi!r} = {tau!r} (ruling R-i, "
        "section_synthesis sec. 4's bound at the question's own conditioning event). "
        f"eps_answer = 1/M with M = {rows_of_answer_kind} rows of the ANSWERING kind, the "
        "derivation grading/lenses.py EPS_DERIVATION states; b = "
        f"{mass!r} is {source}. This is the ONLY tolerance the read applies: the build carries "
        "residuals and passes no verdict, and the four-rung ladder on this object is retained "
        "as the DECLARED CONTROL (the ablation switch), not as the read's tolerance.")


def _day_key_of(value: str | None, as_of: int | None) -> int:
    """A declared day surface as its integer day key; the literal ``as_of`` resolves to the
    record's own latest declared day. Never a string comparison, never the clock."""
    from ..record.columns import day_key
    if value in (None, "", "as_of"):
        if as_of is None:
            raise QuestionRefusal("QUESTION-AS-OF-NOT-DECLARED")
        return int(as_of)
    import datetime as _dt

    return int(day_key(_dt.date.fromisoformat(str(value))))


def _resolve_anchors(spec: QuestionSpec, opened: Any) -> dict[str, Any]:
    """The question's surfaces, through the anchor index, walked to the DECLARED horizon.

    The walk is ``anchors.anchor_expansion`` - the corrected instrument, lifted out of the
    deleted ``record/measure.py`` into the running path, which is what "deleted into the
    receipts" means for it: the measurement script is gone and the organ is now on the read's
    own path with its counters in the read's own receipt.
    """
    from .anchors import anchor_expansion, declared_walk_horizon

    if not spec.anchor_surfaces:
        return {"surfaces": [], "resolved": 0, "reached_rows": None, "seed_rows": None,
                "hops": 0, "horizon": 0,
                "why": "this question names no surface: its mask is columns only"}
    index = opened.ingestion.anchors
    if index is None:
        raise QuestionRefusal("QUESTION-ANCHOR-INDEX-ABSENT", surfaces=list(spec.anchor_surfaces))
    # THE LEXICAL PREDICATE, lifted: what counts as the SAME surface is decided by
    # ``lexical_index.normalize_tokens`` (NFKC, casefold, the module's own frozen token regex),
    # not by a normalisation invented here. A question surface whose observable word-form tokens
    # are empty names nothing the anchor index can resolve and is refused by name rather than
    # resolved to zero rows quietly. The module's SCORING half (build_lexical_index,
    # score_token_queries) is not reached: a BM25/IDF score over the corpus is a ranking, and a
    # ranking is what this read exists not to be.
    lx = lifted("lexical_index")
    tokenised = {surface: lx.normalize_tokens(surface)
                 for surface in spec.anchor_surfaces}  # loop-ok: the question's own declared surface list
    empty = sorted(s for s, t in tokenised.items() if not t)  # loop-ok: the question's own surfaces
    if empty:
        raise QuestionRefusal("QUESTION-SURFACE-HAS-NO-OBSERVABLE-TOKEN", surfaces=empty)
    seeds = index.resolve(list(spec.anchor_surfaces))
    declared_horizon = declared_walk_horizon(opened.ingestion.declaration, spec.row_kind)
    if spec.walk_hops:
        # The walk cap is the DECLARED horizon; a question asking for fewer hops than the
        # declaration admits is asking a narrower question and says so by its own hop count,
        # which is never allowed to exceed the declaration.
        horizon = min(int(spec.walk_hops), max(int(declared_horizon), 1))
        walked = anchor_expansion(opened.ingestion, seeds, spec.row_kind, horizon)
        table = opened.ingestion.store.table(spec.row_kind)
        reached = table.global_ordinals.index_select(0, walked["carrier_local"])
    else:
        horizon = 0
        walked = {"resolved": int(seeds.numel()), "depth": 0,
                  "rows_by_hop": [int(seeds.numel())], "horizon": 0}
        reached = seeds
    return {"surfaces": list(spec.anchor_surfaces),
            "surface_tokens": {s: list(t) for s, t in tokenised.items()},  # loop-ok: the question's own surfaces
            "surface_tokens_by": ("reconstruction/extension/lexical_index.py normalize_tokens, "
                                  "loaded by atlas.front.lift"),
            "resolved": int(seeds.numel()),
            "seed_rows": seeds, "reached_rows": reached,
            "reached": int(reached.numel()), "hops": int(walked.get("depth", 0)),
            "rows_by_hop": list(walked.get("rows_by_hop", [])),
            "horizon": int(walked.get("horizon", horizon)),
            "declared_horizon": int(declared_horizon),
            "why": "the question's surfaces resolved through the anchor index (C.3) and walked "
                   "over the DECLARED relations to the declared horizon; the reached set is a "
                   "two-code derived column the frontier reduces like any other face"}


# --------------------------------------------------------------------- the declared questions
def toy_questions(_opened: Any = None) -> tuple[QuestionSpec, ...]:
    """The toy corpus's five questions, EXACTLY as C.25 and the fixture declare them.

    The fixture (``evidence/ATLAS_PROGRAMME/lane_c/toy_corpus.py``) states the text of Q1..Q6
    and the gold answer of each in ``GOLD``; C.25 states that no clause may introduce a row that
    is not in its table. The conditions below are the question's own words in the record's own
    columns - the compiler resolves each surface to a code and refuses one the record does not
    declare. Q6 is the empty-mask case (C.11) and is not in QUESTION_ORDER, so the five
    known-answer questions are Q1..Q5.

    Where the fixture's gold is prose ("the vet visit"), the known answer here is the typed
    value of the answer COLUMN that names it (``vet_visit``, the predicate of row r3), because
    the read answers with a typed value and not with a sentence; the fixture row that states it
    is named in ``known_answer_source``.
    """
    budget = 1 << 14        # the toy's whole blob is 8 turns; a budget above it cannot bind
    return (
        QuestionSpec(
            qid="Q1", text="Which happened first: Miso's vet visit or the move to Lisbon?",
            dataset_id="atlas-toy-corpus", row_kind="toy_row",
            conditions=(
                Condition("equality", "toy_row", "kind", ("event",),
                          why="both candidates are EVENTS: the question asks which HAPPENED"),
                Condition("equality", "toy_row", "polarity", ("asserted",),
                          why="a hypothetical or attributed event did not happen"),
                Condition("membership", "toy_row", "predicate", ("vet_visit", "move"),
                          why="the two events the question names, as the record spells them"),
            ),
            operator=Operator("first_by", "predicate", "event_date"),
            byte_budget=budget, known_answer="vet_visit",
            known_answer_source="toy_corpus.GOLD['Q1'] = 'the vet visit'; the row it names is "
                                "r3 (predicate vet_visit, event_date 2026-02-10), earlier than "
                                "r5 (move, 2026-03-15)"),
        QuestionSpec(
            qid="Q2", text="In how many sessions did I mention Miso?",
            dataset_id="atlas-toy-corpus", row_kind="toy_row",
            conditions=(),
            operator=Operator("count_distinct", "session_id"),
            byte_budget=budget, anchor_surfaces=("Miso",), walk_hops=0,
            known_answer=3,
            known_answer_source="toy_corpus.GOLD['Q2'] = 3; MENTIONS['Miso'] = [r1, r3, r6], "
                                "whose sessions are s1, s2, s3 - and the fixture states that "
                                "the mentions ARE the anchor_index posting lists, which is why "
                                "this question's mask is the anchor resolution and no column"),
        QuestionSpec(
            qid="Q3", text="Where do I live now?",
            dataset_id="atlas-toy-corpus", row_kind="toy_row",
            conditions=(
                Condition("equality", "toy_row", "kind", ("state",)),
                Condition("equality", "toy_row", "predicate", ("residence",)),
                Condition("equality", "toy_row", "subject", ("self",),
                          why="'I' is the declared principal surface 'self' (the toy's own "
                              "alias table resolves I/me/my to it)"),
                Condition("equality", "toy_row", "polarity", ("asserted",)),
            ),
            operator=Operator("latest_by", "object", "valid_from"),
            byte_budget=budget, live_claim_column="claim_id", as_of_column="event_date",
            interval_columns=("valid_from", "valid_to"),
            known_answer="Lisbon",
            known_answer_source="toy_corpus.GOLD['Q3'] = 'Lisbon' (row r5b, valid_from "
                                "2026-03-15, open above; r7's Leeds is refuted by r8's negation "
                                "of claim c7 and r8b's Sheffield is older)"),
        QuestionSpec(
            qid="Q4", text="Did I ever live in Leeds?",
            dataset_id="atlas-toy-corpus", row_kind="toy_row",
            conditions=(
                Condition("equality", "toy_row", "kind", ("state",)),
                Condition("equality", "toy_row", "predicate", ("residence",)),
                Condition("equality", "toy_row", "subject", ("self",)),
                Condition("equality", "toy_row", "place", ("Leeds",)),
                Condition("equality", "toy_row", "polarity", ("asserted",)),
            ),
            operator=Operator("exists", "place"),
            byte_budget=budget, live_claim_column="claim_id",
            known_answer=False,
            known_answer_source="toy_corpus.GOLD['Q4'] = False: r7 asserts it but r8 negates "
                                "claim c7, so no LIVE asserted residence row places self in "
                                "Leeds - the answer the polarity column alone cannot give"),
        QuestionSpec(
            qid="Q5", text="Who has met Miso?",
            dataset_id="atlas-toy-corpus", row_kind="toy_row",
            conditions=(
                Condition("equality", "toy_row", "predicate", ("meet",)),
                Condition("equality", "toy_row", "polarity", ("asserted",)),
            ),
            operator=Operator("distinct_values", "subject"),
            byte_budget=budget, anchor_surfaces=("Miso",), walk_hops=1,
            known_answer=["Ana"],
            known_answer_source="toy_corpus.GOLD['Q5'] = {'Ana'}: r6 (meet, subject Ana) is the "
                                "only asserted meet row the walk from Miso reaches"),
    )


def engine_questions(opened: Any) -> tuple[QuestionSpec, ...]:
    """Three questions on the ENGINE'S OWN LEDGERS - the dataset the campaign exists for.

    There is no fixture here, so there is no gold string: each answer is checked against an
    INDEPENDENT recount over the decoded rows in the same run (``read.direct_answer``), which is
    the stronger check anyway - it is the identity audit's own route. The questions are the ones
    the charter says the engine could not answer on 2026-09-21 ("which ruling came after which,
    what is open since when"): they are relational and temporal.
    """
    budget = 1 << 20
    rarest_status, rarest_why = rarest_declared(opened, "work_order", "status")
    return (
        QuestionSpec(
            qid="G1", text="which lanes carry the open work orders",
            dataset_id="engine-ledgers", row_kind="work_order",
            conditions=(Condition("equality", "work_order", "status", ("open",)),),
            operator=Operator("count_distinct", "lane"), byte_budget=budget),
        QuestionSpec(
            qid="G2", text="what is the latest open work order's own lane",
            dataset_id="engine-ledgers", row_kind="work_order",
            conditions=(Condition("equality", "work_order", "status", ("open",)),),
            operator=Operator("latest_by", "lane", "date"), byte_budget=budget),
        QuestionSpec(
            qid="G3", text="is there any open work order in the atlas corpus",
            dataset_id="engine-ledgers", row_kind="work_order",
            conditions=(Condition("equality", "work_order", "status", ("open",)),),
            operator=Operator("exists", "id"), byte_budget=budget),
        # ---- THE SELECTIVE ONES. G1-G3 are satisfied by a large fraction of the ledger, and
        # J2 measured what follows from that: the descent touched 99.6% of the lens's positions
        # and so could not overtake a packed scan. These two are the questions S4B says the
        # hierarchy is FOR - a condition a fixed cutoff can refuse from the root - and neither
        # carries a literal: the status is the record's own rarest declared one and the day is
        # the record's own latest declared day.
        QuestionSpec(
            qid="S-G1",
            text="which lanes carry the work orders in the record's rarest declared status",
            dataset_id="engine-ledgers", row_kind="work_order",
            conditions=(Condition("equality", "work_order", "status",
                                  (rarest_status,), derived="rarest declared status",
                                  why=rarest_why["derivation"]),),
            operator=Operator("count_distinct", "lane"), byte_budget=budget),
        QuestionSpec(
            qid="S-G2",
            text="which lanes carry the work orders declared on the record's own latest day",
            dataset_id="engine-ledgers", row_kind="work_order",
            conditions=(Condition("day", "work_order", "date", day="as_of",
                                  derived="the record's own latest declared day",
                                  why="a RANGE SET AT A DECLARED STRENGTH: the narrowest "
                                      "interval the date column declares, one day wide, "
                                      "resolved against the record and never the clock"),),
            operator=Operator("count_distinct", "lane"), byte_budget=budget,
            as_of_column="date"),
    )


def longmem_questions(opened: Any) -> tuple[QuestionSpec, ...]:
    """Two SMOKE questions on LongMemEval-S at rung (ab) and two SELECTIVE ones.

    L1 and L2 exercise the same read on a real corpus with a row-scale carrier, which is where
    the dense reduction refuses and the sparse one must answer - but ``speaker`` has two
    declared values, so they are satisfied by about half the turns and the descent has nothing
    to refuse. S-L1 and S-L2 ask about ONE haystack's turns, named by the question_id the
    record itself carries fewest turns for, which at 100 haystacks is about one percent of the
    carrier - the fraction S4B's fixed cutoff can actually prune on.
    """
    budget = 1 << 20
    rarest_question, rarest_why = rarest_declared(opened, "turn", "question_id")
    return (
        QuestionSpec(
            qid="L1", text="which speakers hold the turns of this draw",
            dataset_id="longmemeval-s-rung-ab", row_kind="turn",
            conditions=(Condition("equality", "turn", "speaker", ("user",)),),
            operator=Operator("count_distinct", "session_index"), byte_budget=budget),
        QuestionSpec(
            qid="L2", text="is any turn of this draw spoken by the assistant",
            dataset_id="longmemeval-s-rung-ab", row_kind="turn",
            conditions=(Condition("equality", "turn", "speaker", ("assistant",)),),
            operator=Operator("exists", "session_index"), byte_budget=budget),
        QuestionSpec(
            qid="S-L1",
            text="how many sessions hold the turns of the record's sparsest history",
            dataset_id="longmemeval-s-rung-ab", row_kind="turn",
            conditions=(Condition("equality", "turn", "question_id", (rarest_question,),
                                  derived="rarest declared question_id",
                                  why=rarest_why["derivation"]),),
            operator=Operator("count_distinct", "session_index"), byte_budget=budget),
        QuestionSpec(
            qid="S-L2",
            text="who speaks the last turn of the record's sparsest history",
            dataset_id="longmemeval-s-rung-ab", row_kind="turn",
            conditions=(Condition("equality", "turn", "question_id", (rarest_question,),
                                  derived="rarest declared question_id",
                                  why=rarest_why["derivation"]),),
            operator=Operator("latest_by", "speaker", "turn_index"), byte_budget=budget),
    )


def qasper_questions(opened: Any) -> tuple[QuestionSpec, ...]:
    """One SMOKE question on QASPER dev and one SELECTIVE one.

    P1 has no column condition at all - it counts an axis over the whole carrier - so it is the
    least selective question of the draw and the packed control cannot even run on it (no
    binary axis to pack). S-P1 asks the same count over ONE paper, the one the record carries
    fewest paragraphs for.
    """
    rarest_paper, rarest_why = rarest_declared(opened, "paragraph", "paper_id")
    return (
        QuestionSpec(
            qid="P1", text="which sections hold the paragraphs of these papers",
            dataset_id="qasper-v0.3-rung-ab", row_kind="paragraph",
            conditions=(),
            operator=Operator("count_distinct", "section_index"), byte_budget=1 << 20),
        QuestionSpec(
            qid="S-P1",
            text="how many sections hold the paragraphs of the record's sparsest paper",
            dataset_id="qasper-v0.3-rung-ab", row_kind="paragraph",
            conditions=(Condition("equality", "paragraph", "paper_id", (rarest_paper,),
                                  derived="rarest declared paper_id",
                                  why=rarest_why["derivation"]),),
            operator=Operator("count_distinct", "section_index"), byte_budget=1 << 20),
    )


# Serialized explanation projection; exact tau/precision/conditions remain present.

# The inert closed receipt contract; numeric execution remains owned here.
from ..receipt_diagnostics import compiled_question_parts
