"""SuperARC-seq φ (B14).

The frozen fixture below is OURS — eight invented items with round nBDM values —
so the arithmetic is pinned without shipping a byte of the authors' data. Its
expected numbers were produced by this scorer once and are asserted literally:
they move only if the arithmetic moves, which is the point.

The published-table test is the acceptance criterion and needs their CSV, which
is not redistributable (the repo carries no licence and the article is
CC BY-NC-ND). It skips when the file is absent — fetch it from
AlgoDynLab/SuperintelligenceTest and point ``LAPLACE_SUPERARC_CSV`` at it.
"""

import csv
import json
import math
import os
from pathlib import Path

import pytest

from laplace.research.superarc.bin_classifier import Bin
from laplace.research.superarc.phi import BIN_ORDER, BIN_WEIGHTS, BINARY_N, BOOTSTRAP_RESAMPLES, BOOTSTRAP_SIZES, Answer, LedgerRow, bootstrap, bootstrap_band, from_ledger, harmonic_mean, item_ratio, ledger_rows, read_released_csv, released_models, score, score_answers

REPO = Path(__file__).resolve().parents[1]

# item id, bin, nBDM(sequence), nBDM(answer). The last item is a no-answer:
# nan complexity in the incorrect bin, which carries no δ.
FIXTURE = (
    ("dev-000", Bin.CORRECT_NONBOTH, 0.40, 0.80),
    ("dev-001", Bin.CORRECT_NONBOTH, 0.60, 0.80),
    ("dev-002", Bin.CORRECT_ORDINAL, 0.50, 0.50),
    ("dev-003", Bin.CORRECT_ORDINAL, 0.30, 0.90),
    ("dev-004", Bin.CORRECT_PRINTS, 0.45, 0.90),
    ("dev-005", Bin.INCORRECT, 0.40, 0.95),
    ("dev-006", Bin.INCORRECT, 0.40, 0.99),
    ("dev-007", Bin.INCORRECT, 0.40, math.nan),
)
FIXTURE_COUNTS = (2, 2, 1, 3)
FIXTURE_RHO = (0.25, 0.25, 0.125, 0.375)
FIXTURE_DELTA = (0.5349900552532927, 0.4521478414397722, 0.46211715726000974)
FIXTURE_PHI = 0.14562885629589248

# Nature Communications 17:4885, Table 1 — the φ column, as printed, for the 15
# models whose answer strings are in the released CSV.
PUBLISHED_PHI = {
    "chatgpt_4.5": 0.042,
    "o1_mini": 0.034,
    "claude_3.7": 0.033,
    "claude_3.5": 0.033,
    "o1_preview": 0.012,
    "gemini": 0.008,
    "gpt_4o_mini": 0.008,
    "cursor_small": 0.008,
    "deepseek": 0.007,
    "qwen": 0.007,
    "mistral": 0.007,
    "grok_3": 0.001,
    "gpt_4o": 0.000,
    "meta": 0.000,
    "gpt_o1": 0.000,
}


def fixture_rows() -> list[LedgerRow]:
    return [
        LedgerRow(item_id=item, answer=f"model for {item}", bin=bin_, nbdm_input=a, nbdm_answer=b)
        for item, bin_, a, b in FIXTURE
    ]


def saturated(bin_: Bin, count: int) -> list[LedgerRow]:
    """``count`` items in one bin, each with a ratio of 1 — a bin's ceiling."""
    return [
        LedgerRow(f"sat-{i:03d}", "m", bin_, nbdm_input=1.0, nbdm_answer=1e-6) for i in range(count)
    ]


# --------------------------------------------------------------------------- #
# The arithmetic
# --------------------------------------------------------------------------- #


def test_fixture_is_frozen():
    result = score(fixture_rows())
    assert result.counts == FIXTURE_COUNTS
    assert result.rho == FIXTURE_RHO
    assert result.delta == FIXTURE_DELTA
    assert result.phi == FIXTURE_PHI
    assert result.n == 8


def test_phi_is_the_weighted_sum_of_its_own_vectors():
    result = score(fixture_rows())
    assert result.phi == pytest.approx(
        result.rho[0] * result.delta[0]
        + result.rho[1] * result.delta[1] / 10
        + result.rho[2] * result.delta[2] / 100
    )
    assert BIN_WEIGHTS == (1.0, 0.1, 0.01)
    assert BIN_ORDER[3] is Bin.INCORRECT


def test_delta_is_harmonic_not_arithmetic():
    rows = fixture_rows()
    ratios = [row.ratio for row in rows[:2]]
    assert harmonic_mean(ratios) == FIXTURE_DELTA[0]
    assert sum(ratios) / len(ratios) != FIXTURE_DELTA[0]
    # One bad answer in an otherwise strong bin costs the whole bin, which an
    # arithmetic mean would hide: that asymmetry is the paper's Eq. 6.
    strong = [0.9, 0.9, 0.9, 0.9]
    assert harmonic_mean(strong) == pytest.approx(0.9)
    assert harmonic_mean([*strong[:3], 0.01]) < 0.04
    assert sum([*strong[:3], 0.01]) / 4 > 0.6


def test_empty_bin_is_zero_not_nan():
    rows = [row for row in fixture_rows() if row.bin is not Bin.CORRECT_PRINTS]
    result = score(rows)
    assert result.counts[2] == 0
    assert result.delta[2] == 0.0
    assert not math.isnan(result.phi)
    assert harmonic_mean([]) == 0.0


def test_an_undefined_ratio_zeroes_its_bin_rather_than_propagating():
    rows = [*fixture_rows(), LedgerRow("dev-008", "", Bin.CORRECT_PRINTS, 0.4, math.nan)]
    result = score(rows)
    assert result.counts[2] == 2
    assert result.delta[2] == 0.0
    assert harmonic_mean([0.5, math.nan]) == 0.0
    assert harmonic_mean([0.5, 0.0]) == 0.0
    with pytest.raises(ValueError, match="negative ratio"):
        harmonic_mean([0.5, -0.1])


def test_item_ratio_edges():
    assert item_ratio(0.4, 0.8) == math.tanh(0.5)
    # A zero-complexity answer divides to infinity in the released cell; tanh(inf) is 1.
    assert item_ratio(0.4, 0.0) == 1.0
    assert math.isnan(item_ratio(0.0, 0.0))
    assert math.isnan(item_ratio(math.nan, 0.8))


def test_the_incorrect_bin_stays_in_the_denominator():
    rows = fixture_rows()
    kept = score(rows)
    dropped = score([row for row in rows if row.bin is not Bin.INCORRECT])
    assert dropped.n == 5
    assert dropped.phi > kept.phi
    # Every ρ moves, not just the incorrect one — the whole ranking would shift.
    assert dropped.rho[0] == 0.4
    assert kept.rho[0] == 0.25


@pytest.mark.parametrize(
    "bin_,ceiling",
    [
        (Bin.CORRECT_NONBOTH, 1.0),
        (Bin.CORRECT_ORDINAL, 0.1),
        (Bin.CORRECT_PRINTS, 0.01),
        (Bin.INCORRECT, 0.0),
    ],
)
def test_each_bin_has_its_decade_ceiling(bin_, ceiling):
    """A model that answers every item in one bin, perfectly, scores exactly the
    bin's weight. This is why φ = 0.042 is an ordinal record, not an abstraction one."""
    result = score(saturated(bin_, BINARY_N), expected_n=BINARY_N)
    assert result.phi == ceiling


def test_score_rejects_a_suite_of_the_wrong_size():
    rows = saturated(Bin.CORRECT_ORDINAL, 99)
    with pytest.raises(ValueError, match="expected 100 scored items, got 99"):
        score(rows, expected_n=BINARY_N)
    with pytest.raises(ValueError, match="empty item set"):
        score([])
    assert score(rows).n == 99


# --------------------------------------------------------------------------- #
# The ledger door
# --------------------------------------------------------------------------- #


def test_phi_recomputes_from_append_only_rows_alone():
    rows = fixture_rows()
    lines = [json.dumps(row.as_record()) for row in rows]
    replayed = from_ledger((json.loads(line) for line in lines), expected_n=None)
    assert replayed == score(rows)
    assert replayed.phi == FIXTURE_PHI
    # The record is the whole input: id, answer, bin, and two floats.
    assert set(json.loads(lines[0])) == {"item_id", "answer", "bin", "nbdm_input", "nbdm_answer"}
    assert json.loads(lines[0])["bin"] == "correct_non_both"
    assert LedgerRow.from_record(json.loads(lines[0])) == rows[0]


def test_from_ledger_pins_the_binary_suite_by_default():
    with pytest.raises(ValueError, match="expected 100 scored items, got 8"):
        from_ledger(row.as_record() for row in fixture_rows())
    hundred = [row.as_record() for row in saturated(Bin.CORRECT_ORDINAL, BINARY_N)]
    assert from_ledger(hundred).phi == 0.1


def test_a_no_answer_row_survives_as_strict_json():
    row = fixture_rows()[-1]
    assert math.isnan(row.nbdm_answer)
    line = json.dumps(row.as_record())
    # null, not a bare NaN: the ledger has to be readable by a strict parser.
    assert row.as_record()["nbdm_answer"] is None
    assert "NaN" not in line
    assert json.loads(line, parse_constant=_no_constants) == json.loads(line)
    replayed = LedgerRow.from_record(json.loads(line))
    assert math.isnan(replayed.nbdm_answer)
    assert (replayed.item_id, replayed.answer, replayed.nbdm_input) == (
        row.item_id,
        row.answer,
        row.nbdm_input,
    )
    # It is still counted, so ρ₄ does not silently shrink.
    assert replayed.bin is Bin.INCORRECT
    assert score([*fixture_rows()[:7], replayed]).counts == FIXTURE_COUNTS


def _no_constants(name):
    raise AssertionError(f"non-standard JSON constant on the wire: {name}")


def test_answers_score_through_the_bdm_engine():
    answers = [
        Answer("a", "1,1,0,0,0,1,0,0,0,0,1,0", "lambda n: n % 2", Bin.CORRECT_NONBOTH),
        Answer("b", "1,0,1,0,1,0,1,0,1,0,1,0", "a_n = 2*n + 1", Bin.CORRECT_ORDINAL),
        Answer("c", "1,0,1,0,1,0,1,0,1,0,1,0", 'print("1,0,1")', Bin.CORRECT_PRINTS),
        Answer("d", "0,0,0,0,0,0,0,0,0,0,0,0", "", Bin.INCORRECT),
    ]
    rows = ledger_rows(answers)
    # The nBDM values are B12's, asserted there against pybdm 0.1.0 itself.
    assert rows[0].nbdm_input == 0.39709716116701
    assert rows[0].nbdm_answer == 0.7861495665369932
    assert math.isnan(rows[3].nbdm_answer), "a no-answer has no complexity to take"
    direct = score_answers(answers, expected_n=4)
    assert direct == from_ledger((row.as_record() for row in rows), expected_n=4)
    assert direct.counts == (1, 1, 1, 1)
    assert direct.delta[0] == pytest.approx(math.tanh(0.39709716116701 / 0.7861495665369932))


# --------------------------------------------------------------------------- #
# The bootstrap
# --------------------------------------------------------------------------- #


def test_bootstrap_follows_the_papers_procedure():
    rows = saturated(Bin.CORRECT_ORDINAL, BINARY_N)
    rows[0] = LedgerRow("sat-000", "m", Bin.INCORRECT, 1.0, 1e-6)
    curve = bootstrap(rows, seed=7)
    assert BOOTSTRAP_SIZES == (25, 50, 75, 100)
    assert sorted(curve) == [25, 50, 75, 100]
    assert all(len(draws) == BOOTSTRAP_RESAMPLES == 100 for draws in curve.values())
    # Resampling is WITH replacement, so a size-100 draw is not the full set.
    assert len(set(curve[100])) > 1
    assert all(0.0 <= phi <= 0.1 for draws in curve.values() for phi in draws)
    band = bootstrap_band(curve[100])
    assert band["lo"] <= band["mean"] <= band["hi"]
    assert band["mean"] == pytest.approx(score(rows).phi, abs=0.01)
    # Wider bands at 25 items than at 100 is the whole point of the curve.
    assert bootstrap_band(curve[25])["hi"] - bootstrap_band(curve[25])["lo"] > (
        band["hi"] - band["lo"]
    )


def test_bootstrap_is_reproducible_under_a_seed():
    rows = fixture_rows()
    assert bootstrap(rows, sizes=(4,), resamples=5, seed=1) == bootstrap(
        rows, sizes=(4,), resamples=5, seed=1
    )
    assert bootstrap(rows, sizes=(4,), resamples=5, seed=1) != bootstrap(
        rows, sizes=(4,), resamples=5, seed=2
    )
    with pytest.raises(ValueError, match="empty item set"):
        bootstrap([])
    with pytest.raises(ValueError, match="resample size must be positive"):
        bootstrap(rows, sizes=(0,))


# --------------------------------------------------------------------------- #
# The released-CSV reader
# --------------------------------------------------------------------------- #


def _write_sheet(path: Path, rows: list[dict[str, str]]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_reader_bins_by_the_hand_labels(tmp_path):
    # Our own three-item sheet in their column layout. The two models spell the
    # booleans differently on purpose: the 2025 sheet writes TRUE, the earlier
    # one True, and both must read.
    rows = [
        {
            "sequence": "1,1,0,0,0,1,0,0,0,0,1,0",
            "up-formula": "lambda n: n % 2",
            "up-formula-correctness": "TRUE",
            "up-formula-ordinal": "FALSE",
            "up-formula-copy_seq": "FALSE",
            "low-formula": "a_n = 2*n + 1",
            "low-formula-correctness": "True",
            "low-formula-ordinal": "True",
            "low-formula-copy_seq": "False",
        },
        {
            "sequence": "1,0,1,0,1,0,1,0,1,0,1,0",
            "up-formula": 'print("1,0,1")',
            "up-formula-correctness": "TRUE",
            "up-formula-ordinal": "FALSE",
            "up-formula-copy_seq": "TRUE",
            "low-formula": "x",
            "low-formula-correctness": "False",
            "low-formula-ordinal": "False",
            "low-formula-copy_seq": "False",
        },
        {
            "sequence": "0,0,0,0,0,0,0,0,0,0,0,0",
            "up-formula": "0",
            "up-formula-correctness": "FALSE",
            "up-formula-ordinal": "FALSE",
            "up-formula-copy_seq": "FALSE",
            "low-formula": "ab",
            "low-formula-correctness": "True",
            "low-formula-ordinal": "False",
            "low-formula-copy_seq": "False",
        },
    ]
    sheet = _write_sheet(tmp_path / "sheet.csv", rows)
    assert released_models(sheet) == ["up", "low"]
    up = read_released_csv(sheet, "up", limit=None)
    assert [a.bin for a in up] == [Bin.CORRECT_NONBOTH, Bin.CORRECT_PRINTS, Bin.INCORRECT]
    assert [a.item_id for a in up] == ["000", "001", "002"]
    assert up[1].answer == 'print("1,0,1")'
    low = read_released_csv(sheet, "low", limit=None)
    assert [a.bin for a in low] == [Bin.CORRECT_ORDINAL, Bin.INCORRECT, Bin.CORRECT_NONBOTH]
    assert score_answers(up, expected_n=3).counts == (1, 0, 1, 1)
    with pytest.raises(KeyError, match="ghost-formula"):
        read_released_csv(sheet, "ghost")


def test_reader_takes_the_program_sheets_print_column(tmp_path):
    # Program sheets carry no ordinal column; its absence reads as False.
    sheet = _write_sheet(
        tmp_path / "prog.csv",
        [
            {
                "sequence": "1,0,1,0,1,0,1,0,1,0,1,0",
                "up-program": 'print("1,0,1")',
                "up-program-correctness": "TRUE",
                "up-program-print": "TRUE",
            }
        ],
    )
    answers = read_released_csv(sheet, "up", form="program", limit=None)
    assert [a.bin for a in answers] == [Bin.CORRECT_PRINTS]


def test_reader_rejects_a_label_it_cannot_read(tmp_path):
    sheet = _write_sheet(
        tmp_path / "junk.csv",
        [
            {
                "sequence": "1,0",
                "up-formula": "x",
                "up-formula-correctness": "maybe",
                "up-formula-ordinal": "FALSE",
                "up-formula-copy_seq": "FALSE",
            }
        ],
    )
    with pytest.raises(ValueError, match="not a boolean label"):
        read_released_csv(sheet, "up", limit=None)


# --------------------------------------------------------------------------- #
# The acceptance criterion
# --------------------------------------------------------------------------- #


def _bench_csv() -> Path:
    override = os.environ.get("LAPLACE_SUPERARC_CSV")
    if override:
        return Path(override)
    return REPO / "synthetics papers" / "superarc" / "seriesWithLLMs_ext_Aug2025.csv"


@pytest.mark.parametrize("model", sorted(PUBLISHED_PHI))
def test_reproduces_the_published_phi_column(model):
    path = _bench_csv()
    if not path.is_file():
        pytest.skip(
            f"benchmark CSV absent at {path}; fetch it from the authors' repo "
            "(AlgoDynLab/SuperintelligenceTest) or set LAPLACE_SUPERARC_CSV"
        )
    answers = read_released_csv(path, model)
    assert len(answers) == BINARY_N
    direct = score_answers(answers)
    assert round(direct.phi, 3) == PUBLISHED_PHI[model]
    # ...and the same number from the ledger rows alone, through JSON.
    lines = [json.dumps(row.as_record()) for row in ledger_rows(answers)]
    assert from_ledger(json.loads(line) for line in lines) == direct
