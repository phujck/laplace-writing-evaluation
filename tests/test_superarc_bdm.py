"""nBDM over the vendored pybdm surface (B12).

The known values are not self-generated: every expected number was produced by
pybdm 0.1.0 itself, installed in a throwaway venv, and is asserted here bit for
bit. That is what makes the vendoring auditable — if a patch in
``scripts/vendor_ctm_tables.py`` ever changes the arithmetic, these move.
"""

import hashlib
import importlib.util
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from laplace.research.superarc.bdm import CTM_DIR, ascii_to_binary_list, bdm_engine, nbdm

REPO = Path(__file__).resolve().parents[1]

CTM_TABLE = "ctm-b2-d12.pkl.gz"
CTM_TABLE_SHA256 = "d97c1c3f59876353d3ef4d8b38087fd0ff447f4ac473dbe9b35b7ef7058a7eb1"
WHEEL_SHA256 = "28cec2b7263f4448ef9d62ae71bf84d1450b83d8a160a69779be0022959ce3c1"

# text -> pybdm 0.1.0's BDM(ndim=1, partition=PartitionRecursive).nbdm(ascii bits)
KNOWN_NBDM = {
    "1,1,0,0,0,1,0,0,0,0,1,0": 0.39709716116701,
    "0,0,0,0,0,0,0,0,0,0,0,0": 0.20624646940857816,
    "1,0,1,0,1,0,1,0,1,0,1,0": 0.3978949504223092,
    "lambda n: n % 2": 0.7861495665369932,
    "a_n = 2*n + 1": 0.87225126312348,
    'print("1,0,1")': 0.8730337567263885,
    "x": 0.860642201555723,
    "ab": 0.69751889835996,
    "0": 0.6252944994548113,
}

# The published SuperARC-seq table (Nature Communications 17:4885, Table 1),
# rounded as printed: rho over the four bins, delta over the three scoring bins, phi.
PUBLISHED_TABLE_1 = {
    "chatgpt_4.5": {"rho": [0.00, 1.00, 0.00, 0.00], "delta": [0.000, 0.419, 0.000], "phi": 0.042},
    "o1_mini": {"rho": [0.00, 0.64, 0.00, 0.36], "delta": [0.000, 0.537, 0.000], "phi": 0.034},
    "claude_3.7": {"rho": [0.00, 0.81, 0.00, 0.19], "delta": [0.000, 0.407, 0.000], "phi": 0.033},
    "claude_3.5": {"rho": [0.06, 0.14, 0.00, 0.80], "delta": [0.449, 0.428, 0.000], "phi": 0.033},
    "gemini": {"rho": [0.00, 0.00, 1.00, 0.00], "delta": [0.000, 0.000, 0.762], "phi": 0.008},
}

BENCH_CSV_NAME = "seriesWithLLMs_ext_Aug2025.csv"
BENCH_CSV_SHA256 = "ea521b4a0a6ab98fa245110f72c883c658e7eb1b5f436051f0eff5b7d3a819f5"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest() -> dict:
    return json.loads((CTM_DIR / "MANIFEST.json").read_text())


def _vendored():
    """The vendored package, which only exists once the engine has been built."""
    bdm_engine()
    return sys.modules["laplace._vendored_ctm"]


def test_manifest_matches_disk():
    manifest = _manifest()
    assert manifest["source"]["sha256"] == WHEEL_SHA256
    assert manifest["source"]["spec"] == "pybdm==0.1.0"
    for name, rec in manifest["vendored"].items():
        path = CTM_DIR / name
        assert path.is_file(), f"{name} listed in MANIFEST.json but absent"
        assert path.stat().st_size == rec["bytes"], name
        assert _sha256(path) == rec["sha256"], name
    for path in CTM_DIR.iterdir():
        if path.name == "MANIFEST.json" or path.name == "__pycache__":
            continue
        assert path.name in manifest["vendored"], f"{path.name} vendored but unrecorded"


def test_only_the_binary_table_is_vendored():
    tables = sorted(p.name for p in CTM_DIR.glob("*.pkl.gz"))
    assert tables == [CTM_TABLE]
    assert _sha256(CTM_DIR / CTM_TABLE) == CTM_TABLE_SHA256
    assert (CTM_DIR / CTM_TABLE).stat().st_size == 23803
    # The wheel's other five tables are 39.9 MB; nothing may drag them back in.
    assert sum(p.stat().st_size for p in CTM_DIR.glob("*.*")) < 100_000
    with pytest.raises(ValueError, match="CTM-B2-D4x4"):
        type(bdm_engine())(ndim=2)


def test_import_needs_no_pybdm_and_no_network():
    assert importlib.util.find_spec("pybdm") is None, "pybdm must not be installed"
    program = """
import socket, sys, importlib.util
class _Blocked(Exception): pass
def _no(*a, **k): raise _Blocked("network use during nBDM")
socket.socket = _no
socket.create_connection = _no
socket.getaddrinfo = _no
assert importlib.util.find_spec("pybdm") is None
from laplace.research.superarc.bdm import nbdm
print(repr(nbdm("1,1,0,0,0,1,0,0,0,0,1,0")))
"""
    env = dict(os.environ, PYTHONPATH=str(REPO / "src"))
    env.pop("LAPLACE_CTM_DIR", None)
    out = subprocess.run(
        [sys.executable, "-c", program], capture_output=True, text=True, env=env, check=True
    )
    assert float(out.stdout.strip()) == KNOWN_NBDM["1,1,0,0,0,1,0,0,0,0,1,0"]


def test_engine_asserts_the_recursive_partition():
    vendored = _vendored()
    engine = bdm_engine()
    assert isinstance(engine.partition, vendored.PartitionRecursive)
    assert engine.partition.shape == (12,)
    assert engine.partition.min_length == 2
    assert engine.ctmname == "CTM-B2-D12"
    assert bdm_engine() is engine


def test_the_other_partitions_are_the_traps_they_look_like():
    vendored = _vendored()
    short = ascii_to_binary_list("ab")  # 16 bits: one 12-bit block plus a 4-bit tail
    # The default 'ignore' boundary drops every block that is not exactly 12 wide,
    # so anything under 12 bits decomposes to nothing at all.
    with pytest.raises(ValueError, match="Computed BDM is 0"):
        vendored.BDM(ndim=1).nbdm(ascii_to_binary_list("a")[:8])
    assert vendored.BDM(ndim=1).nbdm(short) != nbdm("ab")
    with pytest.raises(NotImplementedError):
        vendored.BDM(ndim=1, partition=vendored.PartitionCorrelated).nbdm(short)


@pytest.mark.parametrize("text,expected", sorted(KNOWN_NBDM.items()))
def test_known_nbdm_values(text, expected):
    assert nbdm(text) == expected


def test_ascii_expansion_is_eight_bits_per_character():
    bits = ascii_to_binary_list("a,b")
    assert bits.tolist() == [0, 1, 1, 0, 0, 0, 0, 1, 0, 0, 1, 0, 1, 1, 0, 0, 0, 1, 1, 0, 0, 0, 1, 0]
    assert bits.dtype == np.int8
    assert len(ascii_to_binary_list("1,1,0,0,0,1,0,0,0,0,1,0")) == 8 * 23


def test_the_separator_is_load_bearing():
    # The paper's convention is comma, no space; a space after the comma is a
    # different string and therefore a different complexity.
    assert nbdm("1, 1, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0") != nbdm("1,1,0,0,0,1,0,0,0,0,1,0")


def test_empty_input_is_rejected():
    with pytest.raises(ValueError, match="Computed BDM is 0"):
        nbdm("")


def _bench_csv() -> Path:
    override = os.environ.get("LAPLACE_SUPERARC_CSV")
    return Path(override) if override else REPO / "synthetics papers" / "superarc" / BENCH_CSV_NAME


def _phi_from_csv(path: Path, model: str) -> tuple[list[float], list[float], float]:
    """The published scorer, inlined as this test's oracle (the organ is B14's phi.py)."""
    import csv

    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))[:100]  # the headline phi ranks the binary suite only
    bins: list[list[float]] = [[], [], [], []]
    for row in rows:
        correct = row[f"{model}-formula-correctness"] == "TRUE"
        ordinal = row[f"{model}-formula-ordinal"] == "TRUE"
        copied = row[f"{model}-formula-copy_seq"] == "TRUE"
        if not correct:
            index = 3
        elif ordinal:  # checked before copy_seq: an answer flagged both bins as ordinal
            index = 1
        elif copied:
            index = 2
        else:
            index = 0
        if index < 3:
            bins[index].append(
                math.tanh(nbdm(row["sequence"]) / nbdm(row[f"{model}-formula"]))
            )
        else:
            bins[index].append(0.0)
    total = sum(len(b) for b in bins)
    rho = [len(b) / total for b in bins]
    # delta is the harmonic mean of the per-item ratios within a bin, 0 when empty.
    delta = [len(b) / sum(1 / x for x in b) if b else 0.0 for b in bins[:3]]
    phi = sum(r * d * w for r, d, w in zip(rho[:3], delta, (1, 0.1, 0.01), strict=True))
    return rho, delta, phi


@pytest.mark.parametrize("model", sorted(PUBLISHED_TABLE_1))
def test_reproduces_published_table_1(model):
    csv_path = _bench_csv()
    if not csv_path.is_file():
        pytest.skip(
            f"benchmark CSV absent at {csv_path}; fetch it from the authors' repo "
            "(AlgoDynLab/SuperintelligenceTest) or set LAPLACE_SUPERARC_CSV"
        )
    assert _sha256(csv_path) == BENCH_CSV_SHA256, f"{csv_path} is not the Aug-2025 release"
    published = PUBLISHED_TABLE_1[model]
    rho, delta, phi = _phi_from_csv(csv_path, model)
    assert [round(x, 2) for x in rho] == published["rho"]
    assert [round(x, 3) for x in delta] == published["delta"]
    assert round(phi, 3) == published["phi"]
