"""Blind comparative judgment: acceptance requires beating a rival.

Candidates are stripped of provenance and shuffled deterministically; judges rank and
must articulate the delta. The plateau rule ends iteration: two consecutive challenger
rounds failing to beat the incumbent means dry, and dry is the only exit. Judges never
edit prose; their output is a ranking and typed reasons.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass
class Candidate:
    text: str
    provenance: str   # kept locally, never shown to a judge


def blind_order(candidates: list[Candidate], round_id: str) -> list[int]:
    """Deterministic provenance-free shuffle keyed on content + round, so no seat maps
    to a generation slot across rounds."""
    keyed = sorted(
        range(len(candidates)),
        key=lambda i: hashlib.sha256((round_id + candidates[i].text).encode()).hexdigest())
    return keyed


JUDGE_RETURN_SCHEMA = {
    "type": "object",
    "properties": {
        "ranking": {"type": "array", "items": {"type": "integer"}},
        "winner_beats_runner_up_because": {"type": "string"},
        "defects_in_winner": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["ranking", "winner_beats_runner_up_because", "defects_in_winner"],
}


def compile_judge_prompt(seats: list[str], contract: str, exemplars: str, findings_context: str) -> str:
    body = "\n\n".join(f"CANDIDATE {chr(65 + i)}:\n---\n{t}\n---" for i, t in enumerate(seats))
    return f"""You are judging {len(seats)} candidate versions of the same manuscript passage,
blind: you do not know which is incumbent, which is new, or who produced any of them.
Never assume an ordering signal in the seat letters.

THE CONTRACT the passage must satisfy:
{contract}

CALIBRATION - defects this manuscript's readers have already flagged (a candidate
reproducing any of these fails on that count):
{findings_context}

EXEMPLARS of the register the passage must hold (real published prose; measure
distance from these, not from your taste alone):
{exemplars}

{body}

Rank all candidates strictly (no ties). You MUST articulate specifically why the
winner beats the runner-up - a ranking without a specific, checkable delta is invalid.
Then list the winner's remaining defects; an empty defect list on any candidate is
suspicious and will be audited. Return the JSON only: ranking as seat indices
(0-based, best first), the delta, the winner's defects."""


@dataclass
class Plateau:
    """Two consecutive failed challenges = dry."""

    consecutive_failures: int = 0
    DRY_AT: int = 2

    def record(self, challenger_won: bool) -> None:
        self.consecutive_failures = 0 if challenger_won else self.consecutive_failures + 1

    @property
    def dry(self) -> bool:
        return self.consecutive_failures >= self.DRY_AT
