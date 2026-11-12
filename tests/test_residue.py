"""Tests for laplace.engine.residue - the typed remainder of an UP act - and its one live producer.

Contracts: a record round-trips through the store unchanged; the vocabulary is CLOSED (an unknown
kind is refused at the call site, not coerced); the aggregate keys per (axis, grade, kind) and
never sums a magnitude across grades; banking never raises into the producer; and the meaning fold
banks typed rows on a real scoped fold - the assignment step's uncarried mass, an emptied cluster's
dropped handle, a depth-capped cluster's overflow - with a sealed leaf riding an opaque handle.

The fold half reuses ``test_meaning_upfold_incremental``'s deterministic in-process FakeBackend so
the clustering is fixed and offline; nothing here embeds against the real router."""

from __future__ import annotations

import json

import pytest

from laplace.representation import embed_router
from laplace.engine import meaning_upfold, residue

from test_meaning_upfold_incremental import FakeBackend, _leaf, _residue


# --- the record + the store ---

def test_row_round_trips_through_the_store(tmp_path):
    row = residue.build_row("probe.act", "unplaced", 3.0, axis="semantic", grade=1,
                            ids=["a.md", "b.md", "c.md"], detail={"why": "no handle"})
    residue.append_rows(tmp_path, [row])
    back = residue.read_rows(tmp_path)
    assert back == [row]
    assert back[0]["unit"] == "items" and back[0]["schema"] == residue.SCHEMA
    assert back[0]["n"] == 3 and back[0]["act_id"].startswith("probe.act:")


def test_unknown_kind_is_refused(tmp_path):
    with pytest.raises(residue.UnknownRemainder):
        residue.build_row("probe.act", "vibes", 1.0, axis="semantic")
    with pytest.raises(residue.UnknownRemainder):
        residue.ResidueLedger("probe.act", axis="semantic").add("lossy", 1.0)
    assert not residue.store_path(tmp_path).exists()      # a refused kind banks nothing


def test_every_kind_carries_a_unit_and_a_meaning():
    for kind, (unit, meaning) in residue.remainder_kinds().items():
        assert unit and meaning and residue.unit_of(kind) == unit
        assert residue.build_row("probe.act", kind, 1.0, axis="semantic")["unit"] == unit


def test_ids_are_capped_but_the_count_is_exact(tmp_path):
    many = [f"leaf_{i}.md" for i in range(200)]
    row = residue.build_row("probe.act", "unplaced", 200.0, axis="semantic", ids=many)
    assert row["n"] == 200 and len(row["ids"]) == residue.IDS_CAP
    assert row["detail"]["ids_truncated"] == 200


def test_ledger_banks_one_act_in_one_append(tmp_path):
    led = residue.ResidueLedger("probe.act", axis="semantic")
    led.add("unplaced", 2.0, grade=0, ids=["a.md", "b.md"])
    led.add("uncarried_mass", 0.25, n=4, mean=0.0625)
    led.bank(tmp_path)
    rows = residue.read_rows(tmp_path)
    assert len(rows) == 2 and len({r["act_id"] for r in rows}) == 1
    assert [r["kind"] for r in rows] == ["unplaced", "uncarried_mass"]
    assert rows[1]["grade"] is None and rows[1]["detail"]["mean"] == 0.0625


def test_aggregate_keys_per_axis_grade_kind_and_never_sums_across_grades(tmp_path):
    led = residue.ResidueLedger("probe.act", axis="semantic")
    led.add("dropped_handle", 1.0, grade=1, ids=["concept::a"])
    led.add("dropped_handle", 1.0, grade=1, ids=["concept::b"])
    led.add("dropped_handle", 1.0, grade=2, ids=["concept::c"])
    led.bank(tmp_path)
    cells = residue.aggregate(residue.read_rows(tmp_path))
    by_grade = {c["grade"]: c for c in cells if c["kind"] == "dropped_handle"}
    assert set(by_grade) == {1, 2}                       # the grades stay separate cells
    assert by_grade[1]["magnitude"] == 2.0 and by_grade[1]["rows"] == 2
    assert by_grade[2]["magnitude"] == 1.0
    assert all(c["acts"] == 1 for c in cells)


def test_bank_degrades_loud_and_never_raises(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(residue, "append_rows",
                        lambda *_a, **_k: (_ for _ in ()).throw(OSError("disk full")))
    row = residue.build_row("probe.act", "degenerate", 5.0, axis="semantic")
    assert residue.bank(tmp_path, [row]) is None
    assert "DEGRADED" in capsys.readouterr().err


def test_kill_switch_stops_the_write(tmp_path, monkeypatch):
    monkeypatch.setenv(residue.ENV_DISABLE, "0")
    assert residue.bank(tmp_path, [residue.build_row("p", "unplaced", 1.0, axis="semantic")]) is None
    assert not residue.store_path(tmp_path).exists()


def test_unparseable_tail_row_does_not_cost_the_store(tmp_path, capsys):
    residue.append_rows(tmp_path, [residue.build_row("p", "unplaced", 1.0, axis="semantic")])
    with residue.store_path(tmp_path).open("a", encoding="utf-8") as fh:
        fh.write('{"schema": "residue/v1", "kind": "unpl')      # a torn append
    rows = residue.read_rows(tmp_path)
    assert len(rows) == 1
    assert "unparseable" in capsys.readouterr().err


# --- the one live producer: the meaning fold ---

@pytest.fixture()
def backend(monkeypatch):
    fb = FakeBackend()
    monkeypatch.setattr(embed_router, "get_backend", lambda: fb)
    return fb


def _fold_rows(repo, up_act=None):
    return residue.read_rows(repo, up_act=up_act)


def test_fold_banks_uncarried_mass_on_a_real_incremental_fold(tmp_path, backend):
    res = _residue({"alpha": 8, "beta": 8, "gamma": 8})
    meaning_upfold.cluster_residue_incremental(tmp_path, res, None, lens_hash="L0")
    tree0 = meaning_upfold.load_tree(tmp_path)

    res["alpha/alpha_new.md"] = _leaf("md", ["alpha", "alphaNEW"], essence="alpha")
    meaning_upfold.cluster_residue_incremental(tmp_path, res, tree0, lens_hash="L0")

    rows = [r for r in _fold_rows(tmp_path) if r["kind"] == "uncarried_mass"]
    assert rows, "the assignment step banked no fibre residual"
    row = rows[-1]
    assert row["up_act"] == "meaning_upfold.incremental" and row["axis"] == "semantic"
    assert row["unit"] == "cosine_distance" and row["grade"] is None     # act-level, spans grades
    assert row["n"] == 1 and 0.0 <= row["magnitude"] <= 2.0
    assert row["detail"]["worst_id"] == "alpha/alpha_new.md"


def test_fold_banks_a_dropped_handle_when_a_cluster_empties(tmp_path, backend, capsys):
    # the (d1) setup the incremental suite uses: a whole small family removed (4 of 24 = 16.7%),
    # which empties its cluster without tripping the 20% churn trigger into a full rebuild
    res = _residue({"alpha": 10, "beta": 10, "gamma": 4})
    meaning_upfold.cluster_residue_incremental(tmp_path, res, None, lens_hash="L0")
    tree0 = meaning_upfold.load_tree(tmp_path)
    for i in range(4):
        res.pop(f"gamma/gamma_{i}.md")
    meaning_upfold.cluster_residue_incremental(tmp_path, res, tree0, lens_hash="L0")
    assert "dropped in place" in capsys.readouterr().out       # the drop path, not a rebuild

    dropped = [r for r in _fold_rows(tmp_path) if r["kind"] == "dropped_handle"]
    assert dropped, "an emptied cluster left no typed remainder"
    assert dropped[-1]["unit"] == "handles" and dropped[-1]["n"] == 1
    assert dropped[-1]["grade"] >= 1 and dropped[-1]["ids"][0].startswith("concept::")


def test_fold_banks_overflow_when_the_depth_cap_declines_a_resplit(tmp_path, backend, monkeypatch):
    # The cap is a dial, not a constant (RUL-20260914-no-hardcoded-dials): set it by a successor
    # row in an isolated dial store, the way any dial is changed.
    dial_root = tmp_path / "dials"; dial_root.mkdir()
    monkeypatch.setenv("LAPLACE_DIALS_ROOT", str(dial_root))
    meaning_upfold.dials.pour_genesis(dial_root)
    meaning_upfold.dials.set_value("engine-fold", "max_depth", "1", by="test",
                                   why="every cluster sits at the cap", root=dial_root)
    res = _residue({"alpha": 8, "beta": 8, "gamma": 8})
    meaning_upfold.cluster_residue_incremental(tmp_path, res, None, lens_hash="L0")
    tree0 = meaning_upfold.load_tree(tmp_path)
    for i in range(4):                                       # accrete past LEAF_MAX
        res[f"alpha/alpha_x{i}.md"] = _leaf("md", ["alpha", f"alphaX{i}"], essence="alpha")
    meaning_upfold.cluster_residue_incremental(tmp_path, res, tree0, lens_hash="L0",
                                               allow_spectral=False)

    over = [r for r in _fold_rows(tmp_path) if r["kind"] == "overflow"]
    assert over, "a declined re-split left the overflow untyped"
    assert over[-1]["unit"] == "items" and over[-1]["magnitude"] > 0
    assert over[-1]["detail"]["held"] > meaning_upfold.dials.value("engine-fold", "leaf_max")


def test_a_sealed_leaf_never_rides_a_row_by_path(tmp_path, backend):
    res = _residue({"alpha": 8, "beta": 8, "gamma": 8})
    meaning_upfold.cluster_residue_incremental(tmp_path, res, None, lens_hash="L0")
    tree0 = meaning_upfold.load_tree(tmp_path)
    res["soul/0099_secret.md"] = _leaf("md", ["alpha", "soul"], sealed=True, essence="alpha")
    meaning_upfold.cluster_residue_incremental(tmp_path, res, tree0, lens_hash="L0")

    blob = json.dumps(_fold_rows(tmp_path))
    assert "0099_secret" not in blob and "soul/" not in blob
    worst = [r for r in _fold_rows(tmp_path) if r["kind"] == "uncarried_mass"][-1]
    assert worst["detail"]["worst_id"].startswith("sealed::")


def test_a_degraded_fold_types_itself_degenerate(tmp_path, monkeypatch):
    monkeypatch.setattr(embed_router, "get_backend", lambda: None)   # no embedder: nothing folds
    res = _residue({"alpha": 8, "beta": 8, "gamma": 8})
    pm, cn = meaning_upfold.cluster_residue_incremental(tmp_path, res, None, lens_hash="L0")
    assert (pm, cn) == ({}, {})
    rows = [r for r in _fold_rows(tmp_path) if r["kind"] == "degenerate"]
    assert len(rows) == 1 and rows[0]["n"] == len(res)
    assert rows[0]["unit"] == "items"


def test_a_full_rebuild_inside_a_deposit_is_its_own_act(tmp_path, backend, monkeypatch):
    res = _residue({"alpha": 8, "beta": 8, "gamma": 8})
    meaning_upfold.cluster_residue_incremental(tmp_path, res, None, lens_hash="L0")
    acts = {r["up_act"] for r in _fold_rows(tmp_path)}
    # the cold path routes through _full -> cluster_residue: the nested act is named as itself,
    # and the outer incremental act never double-types the same failure as degenerate
    assert "meaning_upfold.full" in acts or not acts
    assert not [r for r in _fold_rows(tmp_path) if r["kind"] == "degenerate"]


@pytest.fixture(autouse=True)
def _isolated_fold_dials(tmp_path, monkeypatch):
    root = tmp_path / "fold-dials"
    monkeypatch.setenv("LAPLACE_DIALS_ROOT", str(root))
    meaning_upfold.dials.pour_genesis(root)
