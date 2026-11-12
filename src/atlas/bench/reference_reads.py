"""reference_reads.py - three model-free reads, built to EXERCISE the instrument, not to be the arm.

WHAT THESE ARE AND ARE NOT. Packet M1 builds the scorer; the graded carrier and the read that
opens it are packet I1G, in the next wave. F.23's instrument nevertheless has to be shown scoring
a GRADED read and a FLAT read on the same questions before any result exists, so this module
supplies the smallest honest pair, plus the summary-shaped read that the closed-node path exists
for. They are reference instruments. None of them is a submitted arm, none of them is tuned, and
none of them is quoted as a method result anywhere in this packet's output.

They are all deterministic and model-free: no embedding, no cosine, no reader. The only score is
an INTEGER - how many of the question's condition tokens a unit carries - which is a located count,
not a similarity, and which makes the coarse node's bound EXACT:

    a node's face is the union of its members' faces, so
    |condition & face(node)|  >=  |condition & face(m)|  for every member m.

That is why the graded read's prune is a proof and not a heuristic, and it is the property the
author's correction asks a coarse node to carry (the face folded by ONE rule at every level, with
integer block-summed member counts beside it).

READ 1  flat_read     - scan every level-0 unit, score it, supply in descending score order.
READ 2  graded_read   - branch and bound over the node ladder on the exact face bound; supply a
                        node OPENED (all its members' spans, at its own grade) when every member is
                        admitted, otherwise descend and supply the admitted members at grade 0.
                        Answer content differs from READ 1: opening a node also brings in the
                        members that carry no condition token, at the node's full byte cost.
READ 3  summary_read  - RAPTOR-shaped: supply the best coarse nodes CLOSED, i.e. their face text.
                        It spends bytes and covers nothing, which is the point: a stored summary is
                        not the bytes it suppressed.

Executed-work counters are returned with every read (faces tested, nodes expanded, units scored),
because the charter forbids "counters that do not count executed work" and the graded read's whole
claim is that it touches fewer objects for the same answer.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .evidence_coverage import CoverageError, SuppliedUnit, budgeted_prefix
from .gold_spans import UNIT_SEPARATOR, ContainerImage, Node, Unit, _tokens

#: What one unit costs the prompt beyond its own bytes: the separator that keeps two units from
#: running together. Declared here rather than assumed at zero, because a byte budget that ignores
#: the separators is a budget an arm can cheat by supplying many tiny units.
SEPARATOR_COST = len(UNIT_SEPARATOR)


class NoCondition(CoverageError):
    """The question's tokens do not occur anywhere in the container, so no read is defined.

    Fail closed: a read that returns its first k units when it has no condition to evaluate is the
    fallback branch the charter forbids.
    """


@dataclass(frozen=True, slots=True)
class ReadResult:
    """A read's supplied units in supply order, with what it cost to produce them."""

    read_id: str
    units: tuple[SuppliedUnit, ...]
    work: dict

    def as_dict(self) -> dict:
        return {
            "read_id": self.read_id,
            "n_units": len(self.units),
            "grades": sorted({u.grade for u in self.units}),
            "bytes_offered": sum(u.bytes_charged for u in self.units),
            "work": dict(self.work),
        }


def condition_tokens(question: str, image: ContainerImage) -> frozenset[str]:
    """The question's tokens that occur somewhere in this container.

    A token occurring nowhere cannot separate any unit from any other, so it carries no condition;
    dropping it is exact, not a relaxation. If nothing is left, the read refuses.
    """
    vocabulary: frozenset[str] = (
        frozenset().union(*(_tokens(u.text) for u in image.units)) if image.units else frozenset()
    )
    condition = _tokens(question) & vocabulary
    if not condition:
        raise NoCondition(f"no question token occurs in {image.handle}")
    return condition


def _unit_cost(unit: Unit) -> int:
    return unit.span.nbytes + SEPARATOR_COST


def _node_cost(node: Node) -> int:
    return node.span.nbytes + SEPARATOR_COST


def flat_read(question: str, image: ContainerImage, budget_bytes: int) -> ReadResult:
    """READ 1. Exhaustive scan of every level-0 unit; supply in descending integer score.

    Complexity O(U t) for U units and t condition tokens, plus O(U log U) to order them.
    """
    condition = condition_tokens(question, image)
    scored: list[tuple[int, int, Unit]] = []
    for position, unit in enumerate(image.units):
        overlap = len(condition & _tokens(unit.text))
        if overlap:
            scored.append((-overlap, position, unit))
    scored.sort()
    units: list[SuppliedUnit] = []
    used = 0
    for _, _, unit in scored:
        cost = _unit_cost(unit)
        if used + cost > budget_bytes:
            break
        used += cost
        units.append(
            SuppliedUnit(
                unit_id=unit.unit_id, grade=0, opened=True, spans=(unit.span,), bytes_charged=cost
            )
        )
    return ReadResult(
        read_id="flat",
        units=tuple(units),
        work={
            "units_scored": len(image.units),
            "faces_tested": 0,
            "nodes_expanded": 0,
            "objects_touched": len(image.units),
        },
    )


def graded_read(question: str, image: ContainerImage, budget_bytes: int) -> ReadResult:
    """READ 2. Branch and bound on the exact face bound; supply nodes opened where every member is.

    The root's face is tested first; a node whose face bound is zero is pruned WITHOUT any of its
    members being scored, which is where the executed-work difference comes from. A node all of
    whose members are admitted is supplied as ONE opened unit at its own grade, carrying every
    member's span - which is what DOWN returning the finer conceptric means for a supplied set.

    The CANDIDATE sequence - which nodes open whole and which descend to their admitted members -
    is decided once, from face-admission alone, before the budget is ever consulted (this is the
    fix for evidence/ATLAS_PROGRAMME/waves/F1-foundations/synthesis.json seams[0]: the previous
    version chose whole-node-vs-members from the BUDGET remaining at that point in the scan, so a
    bigger budget could pay for a higher-priority node it could not previously afford and crowd out
    a cheaper, lower-priority one that fit inside the smaller budget - LongMemEval e831120c's
    missing set grew from B=4096 to B=8192 this way). Truncating that fixed sequence is then exactly
    ``DECLARED['coverage.packing_rule']`` = "prefix-stop", via the scorer's own
    ``evidence_coverage.budgeted_prefix`` (reused rather than re-derived): stop at the first
    candidate that does not fit and supply nothing after it, so the supplied set at any budget is a
    byte-for-byte PREFIX of the supplied set at every larger budget - true nestedness, not merely
    "coverage happens not to fall".

    Complexity O(N t + U' t) for N nodes, U' the units under admitted nodes only.
    """
    condition = condition_tokens(question, image)
    grade1 = [n for n in image.nodes if n.grade == 1]
    roots = [n for n in image.nodes if n.grade > 1]
    by_unit_id = image.by_unit_id
    faces_tested = 0
    nodes_expanded = 0
    units_scored = 0

    for root in roots:
        faces_tested += 1
        if not (condition & root.face_tokens):
            return ReadResult(
                read_id="graded",
                units=(),
                work={
                    "units_scored": 0,
                    "faces_tested": faces_tested,
                    "nodes_expanded": 0,
                    "objects_touched": faces_tested,
                },
            )

    admitted: list[tuple[int, int, Node]] = []
    for position, node in enumerate(grade1):
        faces_tested += 1
        bound = len(condition & node.face_tokens)
        if bound:
            admitted.append((-bound, position, node))
    admitted.sort()

    candidates: list[SuppliedUnit] = []
    for _, _, node in admitted:
        nodes_expanded += 1
        members = [by_unit_id[m] for m in node.member_ids]
        units_scored += len(members)
        hits = [m for m in members if condition & _tokens(m.text)]
        if not hits:
            continue
        if len(hits) == len(members):
            candidates.append(
                SuppliedUnit(
                    unit_id=node.node_id,
                    grade=node.grade,
                    opened=True,
                    spans=tuple(m.span for m in members),
                    bytes_charged=_node_cost(node),
                    face_kind=node.kind,
                )
            )
        else:
            for member in hits:
                candidates.append(
                    SuppliedUnit(
                        unit_id=member.unit_id,
                        grade=0,
                        opened=True,
                        spans=(member.span,),
                        bytes_charged=_unit_cost(member),
                    )
                )
    units, _used = budgeted_prefix(candidates, budget_bytes)
    return ReadResult(
        read_id="graded",
        units=units,
        work={
            "units_scored": units_scored,
            "faces_tested": faces_tested,
            "nodes_expanded": nodes_expanded,
            "objects_touched": faces_tested + units_scored,
        },
    )


def summary_read(question: str, image: ContainerImage, budget_bytes: int) -> ReadResult:
    """READ 3. The summary-shaped control: the best coarse nodes, supplied CLOSED.

    Each supplied unit costs the bytes of the node's face text and supplies no record span. The
    scorer therefore reports coverage 0 with the budget spent, which is the measurement the
    charter's second fatal default deserves: "a stored summary per node is the architecture the
    eigen paper names as the consequential error".
    """
    condition = condition_tokens(question, image)
    grade1 = [n for n in image.nodes if n.grade == 1]
    scored: list[tuple[int, int, Node]] = []
    faces_tested = 0
    for position, node in enumerate(grade1):
        faces_tested += 1
        bound = len(condition & node.face_tokens)
        if bound:
            scored.append((-bound, position, node))
    scored.sort()
    units: list[SuppliedUnit] = []
    used = 0
    for _, _, node in scored:
        cost = len(node.face_text.encode("utf-8")) + SEPARATOR_COST
        if used + cost > budget_bytes:
            break
        used += cost
        units.append(
            SuppliedUnit(
                unit_id=f"summary:{node.node_id}",
                grade=node.grade,
                opened=False,
                spans=(),
                bytes_charged=cost,
                face_kind=node.kind,
            )
        )
    return ReadResult(
        read_id="summary",
        units=tuple(units),
        work={
            "units_scored": 0,
            "faces_tested": faces_tested,
            "nodes_expanded": 0,
            "objects_touched": faces_tested,
        },
    )


READS = {"flat": flat_read, "graded": graded_read, "summary": summary_read}


def run_reads(
    question: str, image: ContainerImage, budget_bytes: int, read_ids: Sequence[str] = ("flat", "graded", "summary")
) -> dict[str, ReadResult]:
    return {read_id: READS[read_id](question, image, budget_bytes) for read_id in read_ids}


__all__ = [
    "SEPARATOR_COST",
    "NoCondition",
    "ReadResult",
    "condition_tokens",
    "flat_read",
    "graded_read",
    "summary_read",
    "READS",
    "run_reads",
]
