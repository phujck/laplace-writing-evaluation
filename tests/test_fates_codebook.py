"""Unit tests for derive_fates.py - the empirically DERIVED fates codebook (F14).

Covers the carving read off a batch (each occupied cell -> its expected label), the SELF-GATE (a
disagreeing batch is VOID: nonzero, nothing written, the gap banked as a report), the base-only
merge (absent artifact -> the frozen three, byte-identical), and the candidate seal (an unoccupied
cell is never stampable, and the merged view exposes it only when it graduates to non-candidate).
All on fixture verdict-objects and tmp calibration dirs - zero cloud, no ghost.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_SCRIPTS = _REPO / "src" / "laplace" / "pipeline" / "canon" / "skills" / "reconstruction_fitness" / "scripts"
_DERIVE = _SCRIPTS / "derive_fates.py"


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)
    return mod


df = _load(_DERIVE)


def _v(lost=(), added=(), structured=False, recurses=False, just="cited the content"):
    return {"lost": list(lost), "added": list(added), "structured": structured,
            "recurses": recurses, "justification": just}


def _item(cdir: Path, name: str, label: str, verdicts: list[dict], plant: str = ""):
    """Write one calibration item: a subdir with expected.json + the verdict ensemble."""
    sub = cdir / name
    sub.mkdir(parents=True)
    exp = {"label": label}
    if plant:
        exp["plant"] = plant
    (sub / "expected.json").write_text(json.dumps(exp), encoding="utf-8")
    for i, v in enumerate(verdicts, 1):
        (sub / f"v{i}.json").write_text(json.dumps(v), encoding="utf-8")


# A CONSENSUS item needs >= 2 judges raising the same finding (support >= CONSENSUS_SUPPORT), so each
# fixture stacks identical verdicts to lift its signal above the tail.
def _faithful():   return [_v(structured=True, recurses=True)] * 3
def _partial():    return [_v(lost=["the finer mechanism"], structured=True, recurses=True)] * 3
def _confab():     return [_v(lost=["dropped a true claim"], added=["invented a false one"])] * 3
def _enriched():   return [_v(added=["a coherent claim added on a preserved base"],
                             structured=True, recurses=True)] * 3


# --------------------------------------------------------------------------- #
# The signal vector - read at consensus.
# --------------------------------------------------------------------------- #
def test_signal_vector_counts_only_consensus():
    ad = df._sealed()
    # one judge raises a lone finding (support 1, the tail) + two raise a shared one (support 2).
    vs = [_v(lost=["shared loss", "lone loss"]), _v(lost=["shared loss"]), _v(lost=["shared loss"])]
    sig = df.signal_vector(ad.aggregate(vs))
    assert sig["n_lost"] == 1  # only the support>=2 finding counts; the lone one is tail


# --------------------------------------------------------------------------- #
# The carving - each occupied cell classifies to its expected label.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("fixture,expected", [
    (_faithful, "faithful"), (_partial, "partial"),
    (_confab, "confabulated"), (_enriched, "enriched"),
])
def test_carving_classifies_each_cell(fixture, expected):
    ad = df._sealed()
    sig = df.signal_vector(ad.aggregate(fixture()))
    assert df.classify_carving(sig) == expected


def test_derive_writes_codebook_when_batch_agrees(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "state"))
    cdir = tmp_path / "calibration"
    _item(cdir, "f", "faithful", _faithful())
    _item(cdir, "p", "partial", _partial())
    _item(cdir, "c", "confabulated", _confab(), plant="the false one")
    result = df.derive(cdir)
    assert result["disagreements"] == []
    assert result["agreement"] == "3/3"
    cb = result["codebook"]
    assert cb["derived"] is True
    assert cb["derived_from"]["calibration_n"] == 3
    assert cb["derived_from"]["telemetry_n"] == 0          # empty shards, reported not conflated
    assert cb["fates"]["confabulated"]["n_observed"] == 1
    # enriched is present but UNOCCUPIED -> candidate, n:0, never asserted from an empty count.
    assert cb["fates"]["enriched"]["candidate"] is True
    assert cb["fates"]["enriched"]["n_observed"] == 0


# --------------------------------------------------------------------------- #
# The self-gate - a disagreeing batch is VOID (nonzero, nothing written).
# --------------------------------------------------------------------------- #
def test_disagreeing_batch_is_void(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "state"))
    cdir = tmp_path / "calibration"
    # a batch whose signal (added present) contradicts its expected 'faithful' label
    _item(cdir, "liar", "faithful", _confab())
    result = df.derive(cdir)
    assert result["disagreements"]
    assert result["disagreements"][0]["id"] == "liar"
    assert result["agreement"] == "0/1"


def test_void_batch_exits_nonzero_and_writes_no_codebook(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "state"))
    cdir = tmp_path / "calibration"
    _item(cdir, "liar", "faithful", _confab())
    out = tmp_path / "codebook.json"
    report = tmp_path / "VOID.md"
    rc = df.main(["derive", "--calibration", str(cdir), "--out", str(out), "--report", str(report)])
    assert rc == 1                     # VOID -> nonzero, the same bar as the faithfulness gate
    assert not out.exists()            # an unfaithful vocabulary is not shipped
    assert report.exists() and "VOID" in report.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# The base-only merge - absent artifact -> the frozen three, byte-identical.
# --------------------------------------------------------------------------- #
def test_absent_artifact_yields_base_fates_only(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "state"))
    from laplace.engine import telemetry
    monkeypatch.setattr(telemetry, "_FATES_CODEBOOK", tmp_path / "does_not_exist.json")
    assert telemetry.reconstruction_fates() == telemetry.RECONSTRUCTION_FATES


def test_committed_codebook_merges_settled_without_moving_base(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "state"))
    from laplace.engine import telemetry
    merged = telemetry.reconstruction_fates()   # resolves the real committed artifact
    assert {"faithful", "partial", "confabulated"} <= set(merged)
    assert (merged["faithful"], merged["partial"], merged["confabulated"]) == (0.9, 0.6, 0.2)


# --------------------------------------------------------------------------- #
# The candidate seal - an unoccupied cell is never stampable.
# --------------------------------------------------------------------------- #
def test_candidate_fate_not_stampable_via_telemetry(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "state"))
    from laplace.engine import telemetry
    # enriched is a candidate cell in the committed codebook -> withheld from the merged view.
    assert "enriched" not in telemetry.reconstruction_fates()
    with pytest.raises(ValueError):
        telemetry.reconstruction(fate="enriched")


def test_classify_skips_candidate_but_derivation_counts_it():
    ad = df._sealed()
    sig = df.signal_vector(ad.aggregate(_enriched()))
    fates = {n: {"predicate": p, "candidate": n in df._CANDIDATE} for n, p in df.CARVING.items()}
    # the stamp path excludes candidates -> no fate; the derivation's own read counts the cell.
    assert df.classify(sig, fates) is None
    assert df.classify(sig, fates, include_candidate=True) == "enriched"
    assert df.classify_carving(sig) == "enriched"


def test_merged_view_exposes_enriched_only_when_non_candidate(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "state"))
    from laplace.engine import telemetry
    art = tmp_path / "codebook.json"

    def _write(candidate: bool):
        art.write_text(json.dumps({"version": "test", "fates": {
            "faithful": {"predicate": {"n_lost": "==0", "n_added": "==0"},
                         "value": 0.9, "candidate": False},
            "enriched": {"predicate": {"n_lost": "==0", "n_added": ">=1"},
                         "value": 0.95, "candidate": candidate},
        }}), encoding="utf-8")

    monkeypatch.setattr(telemetry, "_FATES_CODEBOOK", art)
    _write(candidate=True)
    assert "enriched" not in telemetry.reconstruction_fates()   # held shut while candidate
    _write(candidate=False)                                     # graduates
    merged = telemetry.reconstruction_fates()
    assert merged["enriched"] == 0.95                           # now stampable, value from codebook
    assert telemetry.reconstruction(fate="enriched")["value"] == 0.95
