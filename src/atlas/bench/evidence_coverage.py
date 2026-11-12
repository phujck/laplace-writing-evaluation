"""evidence_coverage.py - contract F.23's complete-evidence coverage, the campaign's SEARCH metric.

WHAT THIS IS. F.23: "COMPLETE-EVIDENCE COVERAGE at budget B for a question q is 1 if every gold
span of q is contained in the supplied set S(q) within B bytes, else 0. It is computed from gold
spans and supplied spans alone - no model, no cost, fully deterministic and re-runnable."

This module is that predicate and nothing else that needs a model: it never embeds, never calls a
reader, never looks at an arm's name while it scores, and never compares text to text except
through the ONE shared normalizer already ported in ``atlas.bench.scoring.normalize`` (used only
where a legacy metric is reproduced, never to decide containment).

WHAT IT IS NOT, and why the distinction is the whole point. ``atlas.bench.scoring.score`` is the
ANSWER-ATOM scorer: it asks whether the answer's atoms occur in an arm's context. That is a
different, secondary endpoint. F.23 is a SPAN-CONTAINMENT predicate on byte addresses at a byte
budget. A passage that merely mentions the gold entity does not cover it; F.23's own planted
violation is exactly a fuzzy text-match standing in for containment, and
``fuzzy_match_coverage`` below exhibits it and this module's refusal of it.

THE GRADED READ. A supplied unit may sit at any grade. The author's correction (STATE.json
THE_GRAPH_IS_NOT_FLAT_2026_09_21) is that a node at one grade IS a whole conceptric at the grade
below, and its coarsening carries a typed face, block-summed counts and a named residual. This
scorer therefore takes each supplied unit with its GRADE and whether DOWN was taken:

  * opened (DOWN taken)   - the finer conceptric's level-0 spans are in the prompt; those spans
                            are what the predicate tests, exactly as for a flat unit.
  * closed (face supplied)- the node's FACE - a projection - is in the prompt. It costs bytes and
                            COVERS NOTHING, because the record never points up into a projection
                            and a summary is not the bytes it suppressed. This is deliberate and
                            it is the anti-default: crediting a stored summary for the gold it
                            coarsens is the architecture the eigen paper names as the
                            consequential error (charter conventional_defaults[1]).
  * pruned                - not in the supplied list at all: no bytes, no coverage.

A flat read is the special case where every unit has grade 0 and is opened. The same predicate,
the same budget, the same code path scores both - which is the point of requirement (5): the
instrument exists before the result.

ARM-BLINDNESS. ``complete_evidence`` sees gold spans, supplied units and a byte budget. Arm names
enter only in ``score_run``, and only to key the output rows and to run the identity audit; no
branch anywhere reads an arm name to decide a score.

Complexity (F.23's own implementation note: O(questions x gold spans x |S|)). Here, per question:
merging the supplied intervals is O(u log u) in the number of supplied spans u, and each gold
requirement is answered by a binary search over the merged list, so a question costs
O(u log u + g log u) for g gold requirements. Stdlib only; no tensor, no device. That is not a
"CPU numeric path": F.23's implementation field says tensor_form "none - span containment on byte
addresses", package "stdlib". This is host-side accounting, not the numeric core.
"""

from __future__ import annotations


import hashlib
import json
import math
import unicodedata
from bisect import bisect_right
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from ..errors import BenchError

#: Identity of this scorer. Any change to the predicate, the budget rule or the normalizer used
#: for a reproduced legacy metric changes this string, so a coverage number can never be compared
#: across two instruments by accident.
COVERAGE_SCORER_VERSION = "atlas-bench-evidence-coverage/F.23/1"


# --------------------------------------------------------------------------------------------
# Declared parameters. The charter forbids "a numeric literal, threshold, size, count or
# vocabulary in construction or read code that does not resolve to a declared row with
# provenance". Every number this module uses is here, with where it comes from and when it
# expires. Nothing below reads a bare literal.
# --------------------------------------------------------------------------------------------

DECLARED: dict[str, dict] = {
    "coverage.primary_budget_bytes": {
        "value": 4096,
        "kind": "DERIVED-AND-MEASURED",
        "provenance": "contract F.21 derivation: B = smallest whole kibibyte >= max_q |gold(q)|; "
        "measured max 3947 bytes over the 60 burnt non-abstention LongMemEval_s questions",
        "expiry": "recomputed on the 107-question development stratum before the preregistration "
        "commit; B rises if that maximum exceeds 4096",
    },
    "coverage.secondary_budget_bytes": {
        "value": (8192, 16384),
        "kind": "DECLARED",
        "provenance": "contract F.21: declared secondaries for the budget-sensitivity curve, "
        "reported beside the primary and never in its place",
        "expiry": "frozen with the preregistration",
    },
    "coverage.packing_rule": {
        "value": "prefix-stop",
        "kind": "LABELLED ASSUMPTION",
        "provenance": "the supplied set is truncated at B by taking units in the arm's own supply "
        "order and stopping at the first unit that does not fit. Reason: the supplied sets at the "
        "primary and the secondary budgets must be NESTED for F.21's budget-sensitivity curve to "
        "be a curve in one variable; a packer that skips an oversized unit and keeps filling makes "
        "S(q) a non-monotone function of B, so the same arm at 4096 and 8192 bytes would not be "
        "the same arm observed twice.",
        "expiry": "at the preregistration commit, where the packer's own rule is frozen with it",
    },
    "identity.floor_a_discordant_pairs": {
        "value": 6,
        "kind": "DERIVED",
        "provenance": "contract F.23 derivation, from F.22: at any n a paired win needs at least 6 "
        "all-one-sided discordant pairs to reach alpha = 0.05 under the exact test",
        "expiry": "none - it is a property of the exact test",
    },
    "identity.conversion_gap": {
        "value": 0.75,
        "kind": "MEASURED",
        "provenance": "contract F.23 derivation / F.22 conversion model: p1 - p0 = 0.75 measured by "
        "P3 (complete evidence converts 25/28, incomplete 2/14)",
        "expiry": "re-measured at the confirmation run",
    },
    "identity.delta_target": {
        "value": 0.10,
        "kind": "LABELLED ASSUMPTION",
        "provenance": "contract F.23: the recommended delta_target; the sizing floor is "
        "ceil(delta_target / (p1 - p0) * n) questions",
        "expiry": "at the author's ruling on delta_target, which F.23 says the gate is recomputed "
        "from",
    },
}


def declared(key: str):
    """The value of a declared parameter. The only way a number enters this module."""
    try:
        return DECLARED[key]["value"]
    except KeyError:  # pragma: no cover - a typo in a key is a programming error
        raise KeyError(f"undeclared parameter {key!r}: add a row to DECLARED with provenance") from None


# --------------------------------------------------------------------------------------------
# Refusals. Every one of these is a fail-closed path: the charter forbids a fallback that lets a
# measurement proceed on an input the metric cannot carry.
# --------------------------------------------------------------------------------------------


class CoverageError(BenchError):
    """Base of every refusal this scorer raises."""


class GoldUnresolvable(CoverageError):
    """A gold requirement does not resolve to a byte address in the record.

    F.23's check fails exactly here: "gold spans are not resolvable to byte addresses in the
    record (a coverage number computed against unresolvable gold is meaningless and the gate
    refuses it)".
    """


class SuppliedUnitMalformed(CoverageError):
    """A supplied unit's declaration contradicts itself (charged bytes below the bytes it supplies,
    an opened unit with no spans, a closed unit that claims record spans)."""


class MissingDocumentIds(CoverageError):
    """A context row carries no ``document_ids``.

    The named fix on ``reconstruction/evaluation_scoring.py:59``: the original wrote
    ``c.get("document_ids", [])``, so a context row that simply forgot to declare its sources was
    scored as reaching nothing - a silent zero that looks like a measured result. Reach is not
    defined for a row that does not declare its sources, so the scorer refuses instead.
    """


class BurntQuestionRefused(CoverageError):
    """A claim was asked for on a question that is burnt.

    360 questions (288 QASPER + 72 LongMemEval) were used for development or a frozen final test
    in the prior work. Q09's condition_for_reuse: "Every one of these 360 questions is burnt for
    any superiority claim."
    """


class RunVoided(CoverageError):
    """The identity audit voided the run: the arm's supplied set equals a control's on so many
    questions that the remaining questions cannot carry the claim (see ``identity_audit``)."""


class AmbiguousGoldMapping(CoverageError):
    """A gold evidence string matched more than one addressable span under the repair rules, so the
    repair refuses rather than pick one."""


# --------------------------------------------------------------------------------------------
# The objects: a byte address, a supplied unit, a gold requirement.
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, order=True)
class SpanAddress:
    """``(content_handle, start, end)`` - the address F.23's planted violation turns on.

    Half-open ``[start, end)`` over the bytes of one content handle. The handle is whatever names
    an immutable byte image: a record content hash, a QASPER paper id, a LongMemEval case id.
    """

    handle: str
    start: int
    end: int

    def __post_init__(self) -> None:
        if not self.handle:
            raise SuppliedUnitMalformed("a span address with no content handle")
        if self.start < 0 or self.end < self.start:
            raise SuppliedUnitMalformed(f"malformed byte range [{self.start}, {self.end}) on {self.handle}")

    @property
    def nbytes(self) -> int:
        return self.end - self.start

    def as_tuple(self) -> tuple[str, int, int]:
        return (self.handle, self.start, self.end)


@dataclass(frozen=True, slots=True)
class SuppliedUnit:
    """One object an arm put in the prompt, at whatever grade it put it there.

    ``grade``    0 is a level-0 record span; k > 0 is a node of the k-th coarsening.
    ``opened``   True iff DOWN was taken and the finer conceptric's spans are in the prompt.
    ``spans``    the level-0 byte intervals actually in the prompt (empty for a closed node).
    ``bytes_charged``  what this unit costs against the byte budget. For an opened unit that is at
                 least the bytes of its spans; for a closed node it is the size of the face text.
    """

    unit_id: str
    grade: int
    opened: bool
    spans: tuple[SpanAddress, ...]
    bytes_charged: int
    face_kind: str = ""

    def __post_init__(self) -> None:
        if self.grade < 0:
            raise SuppliedUnitMalformed(f"{self.unit_id}: negative grade {self.grade}")
        if self.bytes_charged < 0:
            raise SuppliedUnitMalformed(f"{self.unit_id}: negative byte charge")
        if self.opened:
            if not self.spans:
                raise SuppliedUnitMalformed(
                    f"{self.unit_id}: opened (DOWN taken) but supplies no level-0 span - an opened "
                    "node whose members are not in the prompt is a summary, declare it closed"
                )
            supplied = sum(s.nbytes for s in self.spans)
            if self.bytes_charged < supplied:
                raise SuppliedUnitMalformed(
                    f"{self.unit_id}: charges {self.bytes_charged} bytes for {supplied} bytes of "
                    "text - an arm cannot be charged less than the record bytes it supplies"
                )
        else:
            if self.spans:
                raise SuppliedUnitMalformed(
                    f"{self.unit_id}: closed (face only) but claims {len(self.spans)} record spans"
                )
            if self.bytes_charged <= 0:
                raise SuppliedUnitMalformed(
                    f"{self.unit_id}: a closed node in the prompt costs the bytes of its face; a "
                    "node that costs nothing was PRUNED and does not belong in the supplied list"
                )


@dataclass(frozen=True, slots=True)
class GoldRequirement:
    """One thing the question's evidence requires, and every address that satisfies it.

    QASPER's ``evidence_alternatives`` entries are lists of text-identical observations, so ANY of
    them satisfies the requirement. LongMemEval's answer turns and MultiHop-RAG's facts give
    singletons. An EMPTY ``addresses`` tuple is an unresolved requirement: it stays in the
    denominator and can never be satisfied, which is what ``qasper_data.export_gold`` already does
    with ``unmapped_evidence`` and what F.23's check refuses to compute a headline number against.
    """

    requirement_id: str
    addresses: tuple[SpanAddress, ...]
    text: str = ""

    @property
    def resolved(self) -> bool:
        return bool(self.addresses)


@dataclass(frozen=True, slots=True)
class GoldAlternative:
    """One human annotation: the complete set of requirements that annotation asks for."""

    alternative_id: str
    requirements: tuple[GoldRequirement, ...]


@dataclass(frozen=True, slots=True)
class GoldEvidence:
    """The gold evidence of one question: one or more alternatives, the best of which counts.

    Taking the best alternative is not a choice made here - it is what the established QASPER
    scorer does (``qasper_benchmark.evidence_metrics``: ``max(candidates, key=(complete, recall,
    f1))``), and reproducing it to the digit is this packet's requirement (2).
    """

    question_id: str
    dataset: str
    alternatives: tuple[GoldAlternative, ...]
    eligible: bool = True

    @property
    def fully_resolved(self) -> bool:
        return any(all(r.resolved for r in a.requirements) for a in self.alternatives)


# --------------------------------------------------------------------------------------------
# The predicate.
# --------------------------------------------------------------------------------------------


def budgeted_prefix(
    units: Sequence[SuppliedUnit], budget_bytes: int
) -> tuple[tuple[SuppliedUnit, ...], int]:
    """The supplied set within B bytes, under the declared packing rule.

    Complexity O(|units|). Stops at the first unit that does not fit - see
    ``DECLARED['coverage.packing_rule']`` for why it stops rather than skips.
    """
    if budget_bytes <= 0:
        raise CoverageError(f"byte budget must be positive, got {budget_bytes}")
    rule = declared("coverage.packing_rule")
    if rule != "prefix-stop":  # pragma: no cover - the declaration is the only source of the rule
        raise CoverageError(f"unimplemented declared packing rule {rule!r}")
    used = 0
    kept: list[SuppliedUnit] = []
    for unit in units:
        if used + unit.bytes_charged > budget_bytes:
            break
        used += unit.bytes_charged
        kept.append(unit)
    return tuple(kept), used


def merge_intervals(units: Iterable[SuppliedUnit]) -> dict[str, tuple[list[int], list[int]]]:
    """Per content handle, the merged supplied byte intervals as (starts, ends), both sorted.

    Merging is load-bearing: a gold span that straddles two ADJACENT supplied spans of the same
    handle is genuinely in the prompt, and a scorer that tested containment span-by-span would
    report it missing. Merging is exact - it never joins two intervals with a gap between them.

    Complexity O(u log u) for u supplied spans.
    """
    by_handle: dict[str, list[tuple[int, int]]] = {}
    for unit in units:
        for span in unit.spans:
            by_handle.setdefault(span.handle, []).append((span.start, span.end))
    merged: dict[str, tuple[list[int], list[int]]] = {}
    for handle, spans in by_handle.items():
        spans.sort()
        starts: list[int] = []
        ends: list[int] = []
        for start, end in spans:
            if starts and start <= ends[-1]:
                if end > ends[-1]:
                    ends[-1] = end
            else:
                starts.append(start)
                ends.append(end)
        merged[handle] = (starts, ends)
    return merged


def contains(merged: Mapping[str, tuple[list[int], list[int]]], address: SpanAddress) -> bool:
    """True iff ``address`` lies inside one merged supplied interval. O(log u)."""
    entry = merged.get(address.handle)
    if entry is None:
        return False
    starts, ends = entry
    i = bisect_right(starts, address.start) - 1
    if i < 0:
        return False
    return ends[i] >= address.end


@dataclass(frozen=True, slots=True)
class CoverageRow:
    """The scored outcome for one (question, arm, budget). ``complete`` IS F.23's predicate."""

    question_id: str
    dataset: str
    budget_bytes: int
    eligible: bool
    complete: float
    recall: float
    n_requirements: int
    n_satisfied: int
    n_unresolved_requirements: int
    missing: tuple[dict, ...]
    alternative_id: str
    bytes_used: int
    n_units: int
    n_units_opened: int
    n_units_closed: int
    closed_bytes: int
    grades_supplied: tuple[int, ...]
    supplied_fingerprint: str
    complete_text_mapping_possible: bool

    def as_dict(self) -> dict:
        return {
            "question_id": self.question_id,
            "dataset": self.dataset,
            "budget_bytes": self.budget_bytes,
            "eligible": self.eligible,
            "complete": self.complete,
            "recall": self.recall,
            "n_requirements": self.n_requirements,
            "n_satisfied": self.n_satisfied,
            "n_unresolved_requirements": self.n_unresolved_requirements,
            "missing": list(self.missing),
            "alternative_id": self.alternative_id,
            "bytes_used": self.bytes_used,
            "n_units": self.n_units,
            "n_units_opened": self.n_units_opened,
            "n_units_closed": self.n_units_closed,
            "closed_bytes": self.closed_bytes,
            "grades_supplied": list(self.grades_supplied),
            "supplied_fingerprint": self.supplied_fingerprint,
            "complete_text_mapping_possible": self.complete_text_mapping_possible,
        }

    @classmethod
    def from_dict(cls, payload: Mapping) -> "CoverageRow":
        """Rebuild a row from its deposited form - the inverse of ``as_dict``.

        A deposited rows file is therefore not a picture of the scoring: the identity audit, the
        coverage means and the missing-span lists are all recomputable from it by a later reader
        with no access to the corpus, which is what makes a failure diagnosable without a reader
        model. Unknown keys (e.g. the ``read`` label the deposit adds) are ignored.
        """
        fields = {
            "question_id", "dataset", "budget_bytes", "eligible", "complete", "recall",
            "n_requirements", "n_satisfied", "n_unresolved_requirements", "missing",
            "alternative_id", "bytes_used", "n_units", "n_units_opened", "n_units_closed",
            "closed_bytes", "grades_supplied", "supplied_fingerprint",
            "complete_text_mapping_possible",
        }
        missing_keys = fields - set(payload)
        if missing_keys:
            raise CoverageError(
                f"deposited coverage row is missing {sorted(missing_keys)}: it cannot be rebuilt, "
                "and a row that cannot be rebuilt cannot be audited"
            )
        values = {k: payload[k] for k in fields}
        values["missing"] = tuple(values["missing"])
        values["grades_supplied"] = tuple(values["grades_supplied"])
        return cls(**values)


def supplied_fingerprint(units: Iterable[SuppliedUnit]) -> str:
    """A canonical identity of WHAT WAS SUPPLIED, independent of the order or the grade it came at.

    Two arms with the same fingerprint put the same record bytes in front of the reader. That is
    the object the identity audit compares; comparing unit ids instead would let an arm that
    re-labelled a control's output look different from it.
    """
    addresses = sorted({span.as_tuple() for unit in units for span in unit.spans})
    payload = json.dumps(addresses, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def complete_evidence(
    gold: GoldEvidence, units: Sequence[SuppliedUnit], budget_bytes: int
) -> CoverageRow:
    """F.23's predicate for one question at one budget. Arm-blind: no arm name is an input.

    1 iff, for the best alternative, every gold requirement's address is contained in the merged
    supplied intervals of the units that fit inside ``budget_bytes``.

    Complexity O(u log u + g log u); no model, no embedding, no text comparison.
    """
    kept, used = budgeted_prefix(units, budget_bytes)
    merged = merge_intervals(kept)
    fingerprint = supplied_fingerprint(kept)
    opened = [u for u in kept if u.opened]
    closed = [u for u in kept if not u.opened]
    grades = tuple(sorted({u.grade for u in kept}))
    common = {
        "question_id": gold.question_id,
        "dataset": gold.dataset,
        "budget_bytes": budget_bytes,
        "bytes_used": used,
        "n_units": len(kept),
        "n_units_opened": len(opened),
        "n_units_closed": len(closed),
        "closed_bytes": sum(u.bytes_charged for u in closed),
        "grades_supplied": grades,
        "supplied_fingerprint": fingerprint,
    }
    if not gold.eligible or not gold.alternatives:
        return CoverageRow(
            eligible=False, complete=0.0, recall=0.0, n_requirements=0, n_satisfied=0,
            n_unresolved_requirements=0, missing=(), alternative_id="",
            complete_text_mapping_possible=False, **common,
        )

    best: tuple | None = None
    for alternative in gold.alternatives:
        requirements = alternative.requirements
        satisfied = [
            any(contains(merged, address) for address in requirement.addresses)
            for requirement in requirements
        ]
        n = len(requirements)
        n_hit = sum(satisfied)
        recall = n_hit / n if n else 0.0
        complete = float(n and n_hit == n)
        unresolved = sum(not r.resolved for r in requirements)
        key = (complete, recall, -unresolved, alternative.alternative_id)
        candidate = (key, alternative, satisfied, n, n_hit, recall, complete, unresolved)
        if best is None or key > best[0]:
            best = candidate

    _, alternative, satisfied, n, n_hit, recall, complete, unresolved = best
    missing = tuple(
        {
            "requirement_id": requirement.requirement_id,
            "resolved": requirement.resolved,
            "addresses": [a.as_tuple() for a in requirement.addresses],
            "text": requirement.text[:200],
        }
        for requirement, hit in zip(alternative.requirements, satisfied)
        if not hit
    )
    return CoverageRow(
        eligible=True, complete=complete, recall=recall, n_requirements=n, n_satisfied=n_hit,
        n_unresolved_requirements=unresolved, missing=missing,
        alternative_id=alternative.alternative_id,
        complete_text_mapping_possible=any(
            all(r.resolved for r in a.requirements) for a in gold.alternatives
        ),
        **common,
    )


# --------------------------------------------------------------------------------------------
# The identity audit. Charter forbidden_moves: "Any branch that makes an arm equal to its control
# (score_rows = dense_scores), any fallback that silently replaces the method with a baseline."
# v2.1 reported parity on runs where the arm was identical to dense on 252/256 and 45/48.
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class IdentityAudit:
    """Per question, whether the arm's supplied set equals each control's; per run, whether the
    remaining questions can still carry a claim.

    THE VOID RULE IS DERIVED, not chosen. A question on which the arm supplies exactly what a
    control supplies is CONCORDANT by construction: it can never be a discordant pair in the exact
    paired test F.22 and F.23 run. So the questions that can carry the claim are at most
    ``n_scored - n_identical``. F.23's pre-spend gate needs, on n questions, the binding one of
      floor (a) 6 all-one-sided discordant pairs, and
      floor (b) ceil(delta_target / (p1 - p0) * n) questions of coverage gap.
    If the non-identical questions cannot reach that count, the run cannot produce the claim it
    would be quoted for, and the scorer refuses to report one. No new literal enters: 6, 0.75 and
    delta_target are the declared rows above, all three from F.22/F.23's own derivations.
    """

    n_scored: int
    controls: tuple[str, ...]
    identical_by_control: dict
    n_identical_any: int
    identical_question_ids: tuple[str, ...]
    n_identical_empty: int
    capacity: int
    required_discordant: int
    floor_a: int
    floor_b: int
    void: bool

    def as_dict(self) -> dict:
        return {
            "n_scored": self.n_scored,
            "controls": list(self.controls),
            "n_identical_by_control": {k: len(v) for k, v in self.identical_by_control.items()},
            "identical_question_ids_by_control": {
                k: list(v) for k, v in self.identical_by_control.items()
            },
            "n_identical_any": self.n_identical_any,
            "n_identical_because_both_supplied_nothing": self.n_identical_empty,
            "identical_question_ids": list(self.identical_question_ids),
            "capacity_for_discordant_pairs": self.capacity,
            "required_discordant_pairs": self.required_discordant,
            "floor_a_statistical": self.floor_a,
            "floor_b_sizing": self.floor_b,
            "void": self.void,
            "rule": IdentityAudit.__doc__.strip(),
        }


def identity_audit(
    arm_rows: Mapping[str, CoverageRow], control_rows: Mapping[str, Mapping[str, CoverageRow]]
) -> IdentityAudit:
    """Compare the arm's supplied fingerprint against every control's, question by question."""
    question_ids = sorted(arm_rows)
    n = len(question_ids)
    identical_by_control: dict[str, list[str]] = {}
    identical_any: set[str] = set()
    for control, rows in sorted(control_rows.items()):
        hits = [
            qid
            for qid in question_ids
            if qid in rows and rows[qid].supplied_fingerprint == arm_rows[qid].supplied_fingerprint
        ]
        identical_by_control[control] = hits
        identical_any.update(hits)
    empty = supplied_fingerprint(())
    n_identical_empty = sum(
        1 for qid in identical_any if arm_rows[qid].supplied_fingerprint == empty
    )
    floor_a = declared("identity.floor_a_discordant_pairs")
    gap = declared("identity.delta_target") / declared("identity.conversion_gap")
    floor_b = math.ceil(gap * n) if n else 0
    required = max(floor_a, floor_b)
    capacity = n - len(identical_any)
    return IdentityAudit(
        n_scored=n,
        controls=tuple(sorted(control_rows)),
        identical_by_control=identical_by_control,
        n_identical_any=len(identical_any),
        identical_question_ids=tuple(sorted(identical_any)),
        n_identical_empty=n_identical_empty,
        capacity=capacity,
        required_discordant=required,
        floor_a=floor_a,
        floor_b=floor_b,
        void=bool(n) and capacity < required,
    )


# --------------------------------------------------------------------------------------------
# The burnt split. 360 questions are spent; a claim on any of them is refused.
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BurntSplit:
    """The 360 questions burnt by the prior work, with how each id was recovered.

    Q09 reusable_assets "Burnt-split and fresh-draw record": QASPER's 288 are reproduced by sorting
    question_ids on ``sha256('skein-extension:qasper:' + question_id)`` and taking the first limit;
    LongMemEval's 72 are the 24 development and 48 final ids of the recorded salted draw
    (``longmem_split_manifest.json``, salt ``skein-longmemeval-s-cleaned-v1``).
    """

    qasper: frozenset[str]
    longmem: frozenset[str]
    provenance: dict = field(default_factory=dict)

    @property
    def all_ids(self) -> frozenset[str]:
        return self.qasper | self.longmem

    def refuse_claim(self, question_ids: Iterable[str]) -> None:
        """Raise if any question a CLAIM is being made on is burnt."""
        burnt = sorted(set(question_ids) & self.all_ids)
        if burnt:
            raise BurntQuestionRefused(
                f"{len(burnt)} of the scored questions are burnt and cannot carry a superiority "
                f"claim (Q09: all 360 are spent); first ids: {burnt[:5]}"
            )

    def as_dict(self) -> dict:
        return {
            "n_qasper": len(self.qasper),
            "n_longmem": len(self.longmem),
            "n_total": len(self.all_ids),
            "provenance": self.provenance,
        }


QASPER_SALT = "skein-extension:qasper:"


def qasper_burnt_ids(raw_questions_by_split: Mapping[str, Sequence[str]], limits: Mapping[str, int]) -> list[str]:
    """Re-derive a burnt QASPER draw with the recorded salt. ``qasper_data.select_query_ids``'s rule."""
    out: list[str] = []
    for split, limit in limits.items():
        ids = list(raw_questions_by_split[split])
        ordered = sorted(ids, key=lambda x: hashlib.sha256((QASPER_SALT + x).encode()).hexdigest())
        out.extend(ordered[:limit])
    return out


# --------------------------------------------------------------------------------------------
# Reproducing the two established offline scorers (requirement 2), and the named fix
# (requirement 3).
# --------------------------------------------------------------------------------------------


def reach_scores(contexts: Sequence[Mapping], evidence: Sequence[Mapping], documents: Iterable) -> dict:
    """``reconstruction/evaluation_scoring.evidence_scores`` LIFTED WITH ITS ONE NAMED FIX.

    Identical arithmetic to the original (Q06: "Reuse verbatim"), with the single correction the
    quarry names: a context row that does not declare ``document_ids`` RAISES ``MissingDocumentIds``
    instead of being silently counted as reaching nothing. The original's
    ``c.get("document_ids", [])`` at ``evaluation_scoring.py:59`` turned a malformed row into a
    measured zero, which is indistinguishable in the output from an arm that genuinely retrieved
    the wrong documents.

    Everything else is byte-for-byte the same rule: gold URLs matched exactly, title a fallback
    only when the URL is unmatched, an unmapped gold item stays in the denominator, empty evidence
    is N/A. ``atlas/tests/test_bench_evidence_coverage.py`` asserts equality against the original
    function on randomized inputs.
    """
    if not evidence:
        return {
            "source_recall_at_8": None,
            "source_recall_at_20": None,
            "literal_fact_coverage": None,
            "unmapped_gold_items": 0,
            "evidence_items": 0,
        }
    by_url: dict[str, set] = {}
    by_title: dict[str, set] = {}
    for doc in documents:
        if doc.url:
            by_url.setdefault(doc.url, set()).add(doc.document_id)
        by_title.setdefault(doc.title, set()).add(doc.document_id)
    for position, context in enumerate(contexts):
        if "document_ids" not in context:
            raise MissingDocumentIds(
                f"context row {position} declares no document_ids: source reach is undefined for a "
                "row that does not declare its sources (fix of evaluation_scoring.py:59)"
            )
    reached = {}
    for k in (8, 20):
        reached[k] = set().union(*(set(c["document_ids"]) for c in contexts[:k])) if contexts[:k] else set()
    literal_text = " ".join(" ".join(c["text"].casefold().split()) for c in contexts)
    hits = {8: 0, 20: 0}
    unmatched = literal = 0
    for item in evidence:
        ids = by_url.get(item.get("url"), set()) or by_title.get(item.get("title"), set())
        unmatched += int(not ids)
        for k in hits:
            hits[k] += int(bool(ids & reached[k]))
        fact = " ".join(str(item.get("fact", "")).casefold().split())
        literal += int(bool(fact) and fact in literal_text)
    n = len(evidence)
    return {
        "source_recall_at_8": hits[8] / n,
        "source_recall_at_20": hits[20] / n,
        "literal_fact_coverage": literal / n,
        "unmapped_gold_items": unmatched,
        "evidence_items": n,
    }


def qasper_all_metric(selected_ids: Sequence[str], annotations: Sequence[Mapping]) -> dict:
    """The established QASPER 'all' metric - ``qasper_benchmark.evidence_metrics`` - in ID space.

    Kept here to be COMPARED against, not to be the metric: requirement (2) is that this module's
    span-containment predicate reproduces this function's ``complete`` field to the digit on the
    real gold bank. The algorithm is unchanged from ``qasper_benchmark.py:388-411``; the test
    lifts that function's own source text out of the file, hashes it, and asserts equality
    row-by-row so the reproduction is against the file and not against this transcription.
    """
    selected = set(selected_ids)
    candidates = []
    for a in annotations:
        if a["answer_type"] == "unanswerable":
            continue
        groups = a["evidence_alternatives"]
        if not groups:
            continue
        hit = sum(bool(selected.intersection(group)) for group in groups)
        supplied_hit = len(selected.intersection(set().union(*(set(g) for g in groups))))
        recall = hit / len(groups)
        precision = supplied_hit / len(selected) if selected else 0.0
        candidates.append(
            {
                "recall": recall,
                "complete": float(hit == len(groups)),
                "precision": precision,
                "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
                "fully_text_mapped": all(groups),
                "unmapped_requirements": sum(not g for g in groups),
            }
        )
    if not candidates:
        return {"eligible": False, "recall": None, "complete": None, "f1": None}
    best = max(candidates, key=lambda x: (x["complete"], x["recall"], x["f1"]))
    return {
        "eligible": True,
        **best,
        "complete_text_mapping_possible": any(c["fully_text_mapped"] for c in candidates),
        "minimum_unmapped_requirements": min(c["unmapped_requirements"] for c in candidates),
    }


# --------------------------------------------------------------------------------------------
# The planted violations the packet must be proven on.
# --------------------------------------------------------------------------------------------


def fuzzy_match_coverage(gold: GoldEvidence, supplied_text: str) -> float:
    """THE PLANT, not the metric: F.23's own planted violation.

    "score coverage with a fuzzy text-match against gold rather than span containment, so that a
    passage merely mentioning the gold entity counts as covering it." This function does exactly
    that - it asks whether each gold requirement's TEXT appears anywhere in the supplied text,
    through the shared normalizer. It exists so a test can show it crediting a supplied set whose
    spans do not contain the gold interval, while ``complete_evidence`` scores the same set 0.
    """
    from .scoring import normalize

    hay = normalize(supplied_text)
    best = 0.0
    for alternative in gold.alternatives:
        hits = sum(bool(r.text) and normalize(r.text) in hay for r in alternative.requirements)
        best = max(best, float(hits == len(alternative.requirements) and bool(alternative.requirements)))
    return best


def plant_identity_arm(control_units: Sequence[SuppliedUnit]) -> tuple[SuppliedUnit, ...]:
    """THE PLANT: an "arm" that is its control with the unit ids relabelled.

    The charter's forbidden move, in the form it actually took: a fallback branch that hands back
    the baseline's selection. Relabelling is included on purpose - the audit compares supplied
    byte addresses, not unit ids, so the relabelling does not hide it.
    """
    return tuple(
        SuppliedUnit(
            unit_id=f"arm-relabelled:{u.unit_id}",
            grade=u.grade,
            opened=u.opened,
            spans=u.spans,
            bytes_charged=u.bytes_charged,
            face_kind=u.face_kind,
        )
        for u in control_units
    )


# --------------------------------------------------------------------------------------------
# Text normalization used ONLY by the gold-address repair (never to decide containment).
# --------------------------------------------------------------------------------------------


def repair_normalize(text: str) -> str:
    """NFKC, soft hyphens removed, the dash family unified, whitespace collapsed, casefolded.

    This is the normalizer of the QASPER gold-evidence MAP repair: it decides which addressable
    span a gold evidence STRING names. It never decides coverage - coverage is byte containment.
    The dash and whitespace rules are the same ones ``atlas.bench.scoring.normalize`` applies, so
    an arm and the gold map cannot disagree about a character class.
    """
    t = unicodedata.normalize("NFKC", text)
    t = t.replace("­", "")
    t = "".join("-" if ("‐" <= ch <= "―" or ch == "−") else ch for ch in t)
    return " ".join(t.split()).casefold()


__all__ = [
    "COVERAGE_SCORER_VERSION",
    "DECLARED",
    "declared",
    "CoverageError",
    "GoldUnresolvable",
    "SuppliedUnitMalformed",
    "MissingDocumentIds",
    "BurntQuestionRefused",
    "RunVoided",
    "AmbiguousGoldMapping",
    "SpanAddress",
    "SuppliedUnit",
    "GoldRequirement",
    "GoldAlternative",
    "GoldEvidence",
    "CoverageRow",
    "budgeted_prefix",
    "merge_intervals",
    "contains",
    "supplied_fingerprint",
    "complete_evidence",
    "IdentityAudit",
    "identity_audit",
    "BurntSplit",
    "qasper_burnt_ids",
    "reach_scores",
    "qasper_all_metric",
    "fuzzy_match_coverage",
    "plant_identity_arm",
    "repair_normalize",
]
