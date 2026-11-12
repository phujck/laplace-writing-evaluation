"""phi.py — B14: SuperARC-seq (φ), ported from the released scoring cell.

The port is of ``11_S-ARC_ext.ipynb``'s ~40-line ranking cell, not of the paper's
prose: where the two differ the code wins, because the published φ column is what
the code produced. Four things in it are load-bearing.

* **Four bins, in the notebook's order** — correct-and-neither, correct-ordinal,
  correct-prints, incorrect. ρ is each bin's share of the item count, and the
  incorrect bin is counted in the denominator while carrying no δ. That is why
  N = 100 must include it: dropping incorrect answers inflates every ρ.
* **δ_k is a HARMONIC mean over the bin** (the paper's Eq. 6), not a mean of
  per-item ratios and not a ratio of means. One near-zero ratio drags the whole
  bin down. An empty bin is δ_k := 0, so it contributes nothing rather than nan.
* **φ = δ₁ρ₁ + δ₂ρ₂/10 + δ₃ρ₃/100.** The decade weights are the whole ranking:
  an all-ordinal model is capped at 0.1 and an all-prints model at 0.01, so the
  published 0.042 record is a ρ₂ = 1.0 set, not evidence of abstraction.
* **The ratio is per item**, tanh(nBDM(sequence) / nBDM(answer)), over the 8-bit
  ASCII expansion of the literal strings — see :py:mod:`laplace.research.superarc.bdm` for
  the separator and partition conventions that fix those two numbers.

The scored suite is the 100 binary sequences only; the 90 integer items are
reported separately, as the paper does.

:py:func:`from_ledger` is the recomputation door: φ from append-only per-item rows
(item id, answer, bin, nBDM(input), nBDM(answer)) with no access to the item bank,
the classifier or the BDM engine. A run's score has to survive as arithmetic over
its own ledger, or the run cannot be audited after the fact.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from .bdm import nbdm
from .bin_classifier import Bin

#: The scorer's bins in the notebook's slice order. The first three carry a δ.
BIN_ORDER: tuple[Bin, ...] = (
    Bin.CORRECT_NONBOTH,
    Bin.CORRECT_ORDINAL,
    Bin.CORRECT_PRINTS,
    Bin.INCORRECT,
)
#: The decade weights of ``tst_calc``: ``sum(v1[:3] * v2 * [1, 0.1, 0.01])``.
BIN_WEIGHTS: tuple[float, float, float] = (1.0, 0.1, 0.01)
#: The headline φ ranks the binary suite: 100 items, incorrect bin included.
BINARY_N = 100
#: The paper's robustness curve: 100 resamples with replacement at each size.
BOOTSTRAP_SIZES: tuple[int, ...] = (25, 50, 75, 100)
BOOTSTRAP_RESAMPLES = 100

_NBDM_CACHE = 8192


@lru_cache(maxsize=_NBDM_CACHE)
def _nbdm(text: str) -> float:
    """nBDM, memoized — the same 100 sequences are re-scored once per model."""
    return nbdm(text)


def _wire(value: float) -> float | None:
    return None if math.isnan(value) else value


def _unwire(value: Any) -> float:
    return math.nan if value is None else float(value)


@dataclass(frozen=True)
class Answer:
    """One model's answer to one item, already binned."""

    item_id: str
    sequence: str
    answer: str
    bin: Bin


@dataclass(frozen=True)
class LedgerRow:
    """A scored item as it survives on disk: no strings needed but the answer's.

    ``nbdm_answer`` is nan for an empty answer — a no-answer is always INCORRECT,
    whose bin carries no δ, so the nan is never consulted. It is stored rather
    than dropped so the row count still reconstructs ρ. On the wire that nan is
    ``null``: ``json.dumps`` would otherwise write a bare ``NaN``, which no strict
    JSON reader will take back.
    """

    item_id: str
    answer: str
    bin: Bin
    nbdm_input: float
    nbdm_answer: float

    def as_record(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "answer": self.answer,
            "bin": self.bin.value,
            "nbdm_input": _wire(self.nbdm_input),
            "nbdm_answer": _wire(self.nbdm_answer),
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> LedgerRow:
        return cls(
            item_id=str(record["item_id"]),
            answer=record["answer"],
            bin=Bin(record["bin"]),
            nbdm_input=_unwire(record["nbdm_input"]),
            nbdm_answer=_unwire(record["nbdm_answer"]),
        )

    @property
    def ratio(self) -> float:
        return item_ratio(self.nbdm_input, self.nbdm_answer)


@dataclass(frozen=True)
class Score:
    """φ with the vectors it was built from — ρ over four bins, δ over three."""

    phi: float
    rho: tuple[float, float, float, float]
    delta: tuple[float, float, float]
    counts: tuple[int, int, int, int]

    @property
    def n(self) -> int:
        return sum(self.counts)

    def as_record(self) -> dict[str, Any]:
        return {
            "phi": self.phi,
            "rho": list(self.rho),
            "delta": list(self.delta),
            "counts": list(self.counts),
            "n": self.n,
        }


def item_ratio(nbdm_input: float, nbdm_answer: float) -> float:
    """The per-item ratio tanh(nBDM(input) / nBDM(answer)).

    A zero-complexity answer divides to infinity in the released cell (numpy, not
    Python), and tanh(inf) is 1; 0/0 is nan there and is nan here.
    """
    if math.isnan(nbdm_input) or math.isnan(nbdm_answer):
        return math.nan
    if nbdm_answer == 0.0:
        return math.nan if nbdm_input == 0.0 else 1.0
    return math.tanh(nbdm_input / nbdm_answer)


def harmonic_mean(values: Sequence[float]) -> float:
    """δ_k. Zero for an empty bin, and zero — never nan — when a ratio is
    undefined, which is the released cell's ``np.nan_to_num`` on the δ vector."""
    if not values:
        return 0.0
    total = 0.0
    for value in values:
        if value < 0.0:
            raise ValueError(f"negative ratio in a bin: {value!r}")
        if math.isnan(value) or value == 0.0:
            return 0.0
        total += 1.0 / value
    return len(values) / total


def score(rows: Sequence[LedgerRow], *, expected_n: int | None = None) -> Score:
    """φ over a set of scored items. ``expected_n`` pins the suite size."""
    if expected_n is not None and len(rows) != expected_n:
        raise ValueError(f"expected {expected_n} scored items, got {len(rows)}")
    if not rows:
        raise ValueError("cannot score an empty item set")
    grouped: dict[Bin, list[float]] = {bin_: [] for bin_ in BIN_ORDER}
    for row in rows:
        grouped[row.bin].append(row.ratio)
    counts = tuple(len(grouped[bin_]) for bin_ in BIN_ORDER)
    total = sum(counts)
    rho = tuple(count / total for count in counts)
    delta = tuple(harmonic_mean(grouped[bin_]) for bin_ in BIN_ORDER[:3])
    phi = sum(r * d * w for r, d, w in zip(rho[:3], delta, BIN_WEIGHTS, strict=True))
    return Score(phi=phi, rho=rho, delta=delta, counts=counts)


def to_ledger_row(answer: Answer) -> LedgerRow:
    """Score one answer: the only step that touches the BDM engine."""
    return LedgerRow(
        item_id=answer.item_id,
        answer=answer.answer,
        bin=answer.bin,
        nbdm_input=_nbdm(answer.sequence),
        nbdm_answer=_nbdm(answer.answer) if answer.answer else math.nan,
    )


def ledger_rows(answers: Iterable[Answer]) -> list[LedgerRow]:
    return [to_ledger_row(answer) for answer in answers]


def score_answers(answers: Iterable[Answer], *, expected_n: int | None = BINARY_N) -> Score:
    """φ straight from answer strings — the live path, BDM engine included."""
    return score(ledger_rows(answers), expected_n=expected_n)


def from_ledger(
    records: Iterable[Mapping[str, Any] | LedgerRow], *, expected_n: int | None = BINARY_N
) -> Score:
    """φ recomputed from append-only rows alone — no item bank, no BDM engine.

    Accepts the dicts :py:meth:`LedgerRow.as_record` writes (one JSON object per
    line is the campaign's on-disk form) or the rows themselves.
    """
    rows = [r if isinstance(r, LedgerRow) else LedgerRow.from_record(r) for r in records]
    return score(rows, expected_n=expected_n)


def bootstrap(
    rows: Sequence[LedgerRow],
    *,
    sizes: Sequence[int] = BOOTSTRAP_SIZES,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int | None = None,
) -> dict[int, list[float]]:
    """The paper's robustness curve: ``resamples`` draws with replacement per size.

    The released cell calls ``np.random.seed(42)`` and then ``np.random.default_rng()``,
    which ignores that seed — their curve is unseeded and unreproducible. Ours takes
    an explicit seed so a published band can be regenerated.
    """
    if not rows:
        raise ValueError("cannot bootstrap an empty item set")
    rng = np.random.default_rng(seed)
    curve: dict[int, list[float]] = {}
    for size in sizes:
        if size < 1:
            raise ValueError(f"resample size must be positive, got {size}")
        draws = []
        for _ in range(resamples):
            index = rng.integers(low=0, high=len(rows), size=size, dtype=int)
            draws.append(score([rows[i] for i in index]).phi)
        curve[size] = draws
    return curve


def bootstrap_band(draws: Sequence[float], *, coverage: float = 0.95) -> dict[str, float]:
    """Mean and the percentile interval of one resample size's φ draws."""
    if not draws:
        raise ValueError("no draws to summarize")
    tail = (1.0 - coverage) / 2.0 * 100.0
    values = np.asarray(draws, dtype=float)
    return {
        "mean": float(values.mean()),
        "lo": float(np.percentile(values, tail)),
        "hi": float(np.percentile(values, 100.0 - tail)),
    }


_TRUE = {"true", "1", "yes"}
_FALSE = {"false", "0", "no", ""}


def _flag(value: str | None, column: str) -> bool:
    """The released CSVs disagree with themselves on case: the 2025 file writes
    ``TRUE``/``FALSE``, the earlier one ``True``/``False``."""
    text = (value or "").strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    raise ValueError(f"{column}: not a boolean label: {value!r}")


def read_released_csv(
    path: str | Path,
    model: str,
    *,
    form: str = "formula",
    limit: int | None = BINARY_N,
) -> list[Answer]:
    """The authors' answer table for one model, as binnable answers.

    Their hand labels are three booleans per row (correctness / ordinal /
    copy_seq); ``program`` sheets carry no ordinal column, and its absence reads
    as False. The binning itself is B11a's :py:func:`hand_bin`, not restated here.
    """
    from .bin_classifier import hand_bin

    with Path(path).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if limit is not None:
        rows = rows[:limit]
    answer_col = f"{model}-{form}"
    if not rows or answer_col not in rows[0]:
        raise KeyError(f"{answer_col} not in {path}")
    ordinal_col = f"{answer_col}-ordinal"
    copy_col = f"{answer_col}-copy_seq"
    if copy_col not in rows[0]:
        copy_col = f"{answer_col}-print"
    out = []
    for index, row in enumerate(rows):
        bin_ = hand_bin(
            _flag(row[f"{answer_col}-correctness"], f"{answer_col}-correctness"),
            _flag(row.get(ordinal_col), ordinal_col) if ordinal_col in row else False,
            _flag(row.get(copy_col), copy_col) if copy_col in row else False,
        )
        out.append(
            Answer(
                item_id=f"{index:03d}",
                sequence=row["sequence"],
                answer=row[answer_col],
                bin=bin_,
            )
        )
    return out


def released_models(path: str | Path, *, form: str = "formula") -> list[str]:
    """Every model with a released answer column on the given sheet."""
    with Path(path).open(newline="", encoding="utf-8") as handle:
        header = next(csv.reader(handle))
    suffix = f"-{form}"
    return [
        name[: -len(suffix)]
        for name in header
        if name.endswith(suffix) and f"{name}-correctness" in header
    ]
