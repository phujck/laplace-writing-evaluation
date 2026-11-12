"""E4.5 — the axis-gap router: the demand stops being a report.

His placement ruling (2026-07-22): "I think all this lives in the storyboard/narrative
stage, feeding back to the conceptric". The router lives in the storyboard stage and
mints a typed, model-heavy work order per coverage-axis gap (literature / validation /
figure demonstration), through the SAME store + shape ``bank_work_order`` uses, so the
order carries a composed block whose ``what`` names the feedback-to-conceptric leg. The
router BANKS, never fires (PSU discipline). The growth door is dual-piloting (machine or
him), actor-guarded, and false-ruling-refused (the posted consequence fingerprint must
match the served coverage row's routing action). The feedback door keeps a valid composed
block and refuses an invalid one.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from laplace.web import growth_surface
from laplace.manuscript import storyboard
from laplace.manuscript import manuscript_bridge as mb
from laplace.pipeline import composed as _composed
from laplace.pipeline import demand

REPO = Path(__file__).resolve().parents[1]
CORPUS = "paper_falqon"


# ---------------------------------------------------------------------------
# a synthetic coverage vector — gaps on every axis (real 0/N), so the router
# stands alone on a corpus-independent substrate.
# ---------------------------------------------------------------------------

def _cov_with_gaps(root, corpus):
    return {
        "literature": {"axis": "supports", "covered": 0, "total": 3,
                       "uncovered": ["claim:a", "claim:b", "claim:c"]},
        "validation": {"axis": "validates", "covered": 0, "total": 2,
                       "uncovered": ["claim:x", "claim:y"]},
        "demonstration": {"axis": "demonstrates", "covered": 0, "total": 4,
                          "uncovered": ["res:1", "res:2", "res:3", "res:4"]},
    }


_AXIS_TO_ACTION = {
    "literature": "mint-literature",
    "validation": "derive-validation",
    "demonstration": "figure-from-evidence",
}


# ============================================================ 1. the router mints an order

def test_router_mints_a_typed_order_per_axis(tmp_path, monkeypatch):
    monkeypatch.setattr(demand, "coverage_vector", _cov_with_gaps)
    for axis, action in _AXIS_TO_ACTION.items():
        status, obj = storyboard.route_axis_gap(
            CORPUS, axis, requested_by="gerard", root=tmp_path)
        assert status == 200, (axis, obj)
        assert obj["ok"] is True
        rec = obj["work_order"]
        assert rec["kind"] == "work-order"
        assert rec["action"] == action
        assert rec["cost_class"] == "model-heavy"
        assert rec["status"] == "open"
        # additive, typed fields — the axis and the nodes it targets.
        assert rec["axis"] == axis
        assert rec["target_node_ids"] == _cov_with_gaps(None, None)[axis]["uncovered"]
        # the composed block is schema-clean, and its glance rode the response.
        _composed.validate_composed(rec["composed"])
        assert obj["glance"] and obj["glance"] == rec["composed"]["glance"]
        # the feedback-to-conceptric leg is named in the what.
        assert "conceptric" in rec["what"]

    # the router BANKED, never fired: the three orders live in the tmp store.
    banked = storyboard.load_work_orders(tmp_path)
    assert len([r for r in banked if r.get("kind") == "work-order"]) == 3


def test_router_named_node_subset_rides_the_order(tmp_path, monkeypatch):
    monkeypatch.setattr(demand, "coverage_vector", _cov_with_gaps)
    status, obj = storyboard.route_axis_gap(
        CORPUS, "demonstration", node_ids=["res:2"], requested_by="worker", root=tmp_path)
    assert status == 200
    assert obj["work_order"]["target_node_ids"] == ["res:2"]


# ============================================================ 2. the router refuses

def test_router_refuses_an_unknown_axis(tmp_path, monkeypatch):
    monkeypatch.setattr(demand, "coverage_vector", _cov_with_gaps)
    status, obj = storyboard.route_axis_gap(
        CORPUS, "bogus-axis", requested_by="gerard", root=tmp_path)
    assert status == 400
    assert obj["ok"] is False and "unknown axis" in obj["error"]


def test_router_refuses_a_covered_axis_and_a_real_zero(tmp_path, monkeypatch):
    def _cov(root, corpus):
        return {
            "literature": {"axis": "supports", "covered": 3, "total": 3, "uncovered": []},
            "validation": {"axis": "validates", "covered": 0, "total": 0, "uncovered": []},
            "demonstration": {"axis": "demonstrates", "covered": 0, "total": 4,
                              "uncovered": ["res:1"]},
        }
    monkeypatch.setattr(demand, "coverage_vector", _cov)
    # a covered axis: nothing to route.
    s1, o1 = storyboard.route_axis_gap(CORPUS, "literature", requested_by="x", root=tmp_path)
    assert s1 == 409 and "already covered" in o1["error"]
    # a real zero: no gap to route.
    s2, o2 = storyboard.route_axis_gap(CORPUS, "validation", requested_by="x", root=tmp_path)
    assert s2 == 409 and "real zero" in o2["error"]
    # nothing banked on a refusal.
    assert storyboard.load_work_orders(tmp_path) == []


# ============================================================ 3. the door — guard + fingerprint

def _routable_axis():
    """A live falqon coverage axis carrying a routing action, or None."""
    for row in growth_surface.coverage_rows(REPO, CORPUS):
        dec = (row.get("composed") or {}).get("decision") or {}
        if dec.get("actions"):
            return row["axis"], dec["actions"][0]
    return None, None


def test_door_refuses_an_unattributed_routing():
    axis, _ = _routable_axis()
    if axis is None:
        pytest.skip("no routable axis on the live corpus")
    status, obj = growth_surface._route_gap(REPO, {"corpus": CORPUS, "axis": axis})
    assert status == 422 and "by required" in obj["error"]


def test_door_refuses_an_empty_fingerprint():
    axis, _ = _routable_axis()
    if axis is None:
        pytest.skip("no routable axis on the live corpus")
    status, obj = growth_surface._route_gap(
        REPO, {"corpus": CORPUS, "axis": axis, "by": "gerard"})
    assert status == 422 and "fingerprint" in obj["error"]
    assert obj.get("server_fingerprint")


def test_door_refuses_a_mismatched_fingerprint():
    axis, _ = _routable_axis()
    if axis is None:
        pytest.skip("no routable axis on the live corpus")
    status, obj = growth_surface._route_gap(
        REPO, {"corpus": CORPUS, "axis": axis, "by": "gerard", "fingerprint": "deadbeef00"})
    assert status == 409 and "stale" in obj["error"]


def test_door_refuses_an_unknown_axis():
    status, obj = growth_surface._route_gap(
        REPO, {"corpus": CORPUS, "axis": "not-an-axis", "by": "gerard", "fingerprint": "x"})
    assert status == 400 and "unknown axis" in obj["error"]


def test_door_matching_fingerprint_delegates_to_the_router(monkeypatch):
    """A well-formed routing (by + the served fingerprint) passes the false-ruling gate and
    delegates to the router. The router is stubbed so no store is written — the door's job
    is the guard + the fingerprint match, then the hand-off."""
    axis, action = _routable_axis()
    if axis is None:
        pytest.skip("no routable axis on the live corpus")
    server_fp = _composed.action_fingerprint(action["verb"], action["consequence"])
    seen: dict = {}

    def _stub(corpus, ax, node_ids=None, requested_by="", root=None, note=""):
        seen.update(corpus=corpus, axis=ax, by=requested_by)
        return 200, {"ok": True, "work_order": {"id": "WO-stub"}, "glance": "stub"}

    monkeypatch.setattr(storyboard, "route_axis_gap", _stub)
    status, obj = growth_surface._route_gap(
        REPO, {"corpus": CORPUS, "axis": axis, "by": "gerard", "fingerprint": server_fp})
    assert status == 200 and obj["ok"] is True
    assert seen["axis"] == axis and seen["by"] == "gerard" and seen["corpus"] == CORPUS


# ============================================================ 4. the feedback fold

def _valid_block():
    return _composed.make_composed(
        glance="A reviewer flagged that this node's claim needs a validating derivation.",
        working="The claim is stated but nothing below it derives or simulates it yet.",
        minted_by="test", substrate_fingerprint=_composed.fingerprint("t"))


def test_feedback_door_keeps_a_valid_composed_block(tmp_path):
    led = tmp_path / "feedback.jsonl"
    res = mb.feedback_add(REPO, "proj", {
        "node_id": "claim:z", "comment": "needs validation", "composed": _valid_block()},
        ledger=led)
    assert res.get("ok") is True
    assert "composed" in res["record"]
    _composed.validate_composed(res["record"]["composed"])


def test_feedback_door_refuses_an_invalid_composed_block(tmp_path):
    led = tmp_path / "feedback.jsonl"
    res = mb.feedback_add(REPO, "proj", {
        "node_id": "claim:z", "comment": "bad block", "composed": {"glance": ""}},
        ledger=led)
    assert "error" in res and "composed block refused" in res["error"]
    assert not led.exists()  # a refused record banks nothing


def test_feedback_door_absent_block_mints_nothing(tmp_path):
    led = tmp_path / "feedback.jsonl"
    res = mb.feedback_add(REPO, "proj", {
        "node_id": "claim:z", "comment": "a plain note"}, ledger=led)
    assert res.get("ok") is True
    assert "composed" not in res["record"]  # unchanged behaviour, total backward compat


# ============================================================ 5. existing readers unbroken

def test_existing_work_order_readers_unbroken(tmp_path, monkeypatch):
    """The desk / dashboard read work_orders.jsonl through load_work_orders +
    open_work_orders; the additive axis / target_node_ids fields never trip them."""
    monkeypatch.setattr(demand, "coverage_vector", _cov_with_gaps)
    storyboard.route_axis_gap(CORPUS, "demonstration", requested_by="gerard", root=tmp_path)
    recs = storyboard.load_work_orders(tmp_path)
    opens = storyboard.open_work_orders(recs)
    assert len(opens) == 1
    o = opens[0]
    assert o["kind"] == "work-order" and o["status"] == "open"
    assert o["action"] == "figure-from-evidence"
    # the resolution readers tolerate the enriched record shape (no invalid resolutions).
    assert storyboard.invalid_work_order_resolutions(recs) == []


def test_reposting_a_routed_axis_refuses_with_the_open_order_named(tmp_path, monkeypatch):
    """Duplicate discipline (the e45 adversarial close's must-fix): one OPEN order per
    (corpus, action) — the second post refuses 409 and names the standing order instead
    of piling identical open orders."""
    monkeypatch.setattr(demand, "coverage_vector", _cov_with_gaps)
    s1, o1 = storyboard.route_axis_gap(CORPUS, "literature", requested_by="t", root=tmp_path)
    assert s1 == 200
    s2, o2 = storyboard.route_axis_gap(CORPUS, "literature", requested_by="t", root=tmp_path)
    assert s2 == 409
    assert o2["open_order_id"] == o1["work_order"]["id"]
    assert "already routed" in o2["error"]
    # exactly one order banked across both posts.
    assert len(storyboard.load_work_orders(tmp_path)) == 1
