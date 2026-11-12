"""W5.3 — THE PICKUP LOOP: open work-orders surface at wake + on the desk, and
consumption is an EVIDENCE-carrying resolution through an actor-attributed door.

W5.2 banks a model-heavy launch as a ``kind="work-order"`` record the server never
runs. W5.3 closes the loop:

  * SURFACE — an open order rides the WAKE (self_corpus._grade0) and the DESK
    (desk work-orders class) as bounded, refs-only HANDLES; the wake never inlines
    a body.
  * CONSUME — a work-order closes ONLY through a resolution carrying EVIDENCE refs
    (the run's artifacts / a commit / round evidence), written through an actor-
    attributed door. No evidence ⇒ REFUSED, the order stays OPEN and rides the next
    wake. No auto-consumption; the server never fires the work.

The FAIL-CLOSED contract these tests hold (the stage's list, verbatim):
  * an open order appears in the wake payload (bounded) + the desk class;
  * resolving without evidence refs ⇒ refused (the order stays open);
  * resolving with refs ⇒ closed with the evidence banked;
  * the wake never inlines bodies (refs only).
"""
from __future__ import annotations

import json

import pytest

from laplace.web import desk
from laplace.engine import self_corpus as sc
from laplace.manuscript import storyboard as sb

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# the reader — open/consumed queries + bounded, refs-only handles.
# ---------------------------------------------------------------------------

def test_open_work_orders_query(tmp_path) -> None:
    a = sb.bank_work_order("eigenengine", "harnessed-round", "gerard", root=tmp_path)
    b = sb.bank_work_order("subset-sum-itqde", "dream", "gerard", root=tmp_path)
    open_ = sb.open_work_orders(sb.load_work_orders(tmp_path))
    assert {o["id"] for o in open_} == {a["id"], b["id"]}
    assert sb.consumed_work_orders(sb.load_work_orders(tmp_path)) == []


def test_every_current_mint_uses_the_canonical_record_spelling(tmp_path) -> None:
    rec = sb.bank_work_order("eigenengine", "dream", "gerard", root=tmp_path)
    assert rec["record"] == "work-order" and rec["kind"] == "work-order"


def test_consumes_only_resolution_retires_through_the_shared_join() -> None:
    order = {"record": "work-order", "id": "WO-consumes", "status": "open"}
    resolution = {"record": "resolution", "id": "RES-consumes",
                  "consumes": "WO-consumes", "evidence": ["commit:abc"]}
    assert sb.open_work_orders([order, resolution]) == []
    assert sb.consumed_work_orders([order, resolution]) == [order]


def test_kind_only_resolution_and_held_open_resolution_are_not_misread() -> None:
    a = {"record": "work-order", "id": "WO-kind-only", "status": "open"}
    b = {"record": "work-order", "id": "WO-held", "status": "open"}
    kind_only = {"kind": "resolution", "id": "RES-kind-only",
                 "target": "WO-kind-only", "status": "closed", "evidence": ["run:1"]}
    held = {"record": "resolution", "id": "RES-held", "target": "WO-held",
            "status": "closed", "text": "HELD OPEN pending author walk",
            "evidence": ["run:2"]}
    assert sb.open_work_orders([a, b, kind_only, held]) == [b]


def test_evidenceless_consumes_is_invalid_and_retires_nothing() -> None:
    order = {"record": "work-order", "id": "WO-bare", "status": "open"}
    bare = {"record": "resolution", "id": "RES-bare", "consumes": "WO-bare"}
    assert sb.invalid_work_order_resolutions([order, bare]) == [bare]
    assert sb.open_work_orders([order, bare]) == [order]


def test_deferred_order_is_live_but_not_in_the_actionable_open_partition() -> None:
    order = {"record": "work-order", "id": "WO-later", "status": "open"}
    defer = {"record": "defer", "id": "DEFER-later", "target": "WO-later",
             "defer_until": "2099-01-01", "deferred_by": "eigen"}
    parts = sb.work_order_partitions([order, defer])
    assert parts["open"] == 0 and parts["deferred"] == 1
    assert sb.open_work_orders([order, defer]) == []
    assert sb.live_work_orders([order, defer]) == [order]


def test_handles_are_bounded_and_refs_only(tmp_path) -> None:
    for i in range(15):
        sb.bank_work_order(f"corpus-{i}", "dream", "gerard", root=tmp_path)
    h = sb.open_work_order_handles(tmp_path)             # default wake cap (12)
    assert h["count"] == 15
    assert len(h["handles"]) == 12 and h["truncated"] is True
    one = h["handles"][0]
    # exactly the handle fields — id, what, cost, requested + (corpus, action) for the
    # pickup; NO body fields (why / provenance / status / reason).
    assert set(one) == {"id", "action", "corpus", "what", "cost_class", "requested"}
    for leaked in ("why", "provenance", "status", "reason", "record"):
        assert leaked not in one


def test_what_is_capped_never_a_body(tmp_path) -> None:
    sb.bank_work_order("eigenengine", "harnessed-round", "gerard", root=tmp_path)
    h = sb.open_work_order_handles(tmp_path)["handles"][0]
    assert len(h["what"]) <= sb._WO_WHAT_CAP


def test_poisoned_store_serves_a_lower_bound_with_the_exact_residual(tmp_path) -> None:
    rec = sb.bank_work_order("eigenengine", "dream", "gerard", root=tmp_path)
    store = tmp_path / sb._WORK_ORDER_STORE
    with store.open("a", encoding="utf-8") as fh:
        fh.write('{"record":"resolution","id":\n')
    h = sb.open_work_order_handles(tmp_path)
    assert h["count"] == 1 and h["handles"][0]["id"] == rec["id"]
    assert h["cracked"] is True and h["count_is_lower_bound"] is True
    assert len(h["residuals"]) == 1 and h["residuals"][0]["line"] == 2


def test_poisoned_store_refuses_consumption_without_appending(tmp_path) -> None:
    rec = sb.bank_work_order("eigenengine", "dream", "gerard", root=tmp_path)
    store = tmp_path / sb._WORK_ORDER_STORE
    with store.open("a", encoding="utf-8") as fh:
        fh.write("not-json\n")
    before = store.read_bytes()
    st, obj = sb.resolve_work_order(rec["id"], evidence_refs=["commit:proved"],
                                    by="eigen", root=tmp_path)
    assert st == 409 and obj["cracked"] is True and obj["still_open"] is None
    assert obj["residuals"][0]["line"] == 2
    assert store.read_bytes() == before, "a partial-history mutation appended a disposition"


# ---------------------------------------------------------------------------
# SURFACE #1 — the WAKE. an open order rides self_corpus._grade0, bounded, refs-only.
# ---------------------------------------------------------------------------

def _force_substrate(monkeypatch) -> None:
    # make the fixed-point substrate non-empty so the (substrate-gated) work-orders
    # shard is reached, without standing up a whole fake repo.
    monkeypatch.setattr(sc, "_substrate", lambda r: {
        "fixed_point": ["HANDOFF.md", "OPEN_STACK.md"],
        "map": [], "protocol": [], "handoffs": [], "meta": []})


def test_open_order_rides_the_wake(monkeypatch, tmp_path) -> None:
    rec = sb.bank_work_order("eigenengine", "harnessed-round", "gerard", root=tmp_path)
    _force_substrate(monkeypatch)
    out = sc._grade0(tmp_path)
    wo = [s for s in out["shards"] if s["shard"] == "work-orders"]
    assert len(wo) == 1
    body = wo[0]["body"]
    assert rec["id"] in body                            # the handle rides
    assert "model-heavy" in body
    assert wo[0]["source"] == sb._WORK_ORDER_STORE      # refs the store, not the body


def test_wake_never_inlines_bodies(monkeypatch, tmp_path) -> None:
    rec = sb.bank_work_order("eigenengine", "harnessed-round", "gerard", root=tmp_path)
    _force_substrate(monkeypatch)
    out = sc._grade0(tmp_path)
    body = [s for s in out["shards"] if s["shard"] == "work-orders"][0]["body"]
    # the 'why' body never rides the wake (refs only) — only id/what/cost/ts handles.
    assert rec["why"] not in body
    assert "launched from the run panel" not in body


def test_no_open_orders_no_shard(monkeypatch, tmp_path) -> None:
    store = tmp_path / sb._WORK_ORDER_STORE
    store.parent.mkdir(parents=True)
    store.touch()
    _force_substrate(monkeypatch)
    out = sc._grade0(tmp_path)
    assert [s for s in out["shards"] if s["shard"] == "work-orders"] == []


def test_missing_order_authority_surfaces_a_blind_shard(monkeypatch, tmp_path) -> None:
    _force_substrate(monkeypatch)
    out = sc._grade0(tmp_path)
    shard = next(s for s in out["shards"] if s["shard"] == "work-orders")
    assert "WORK-ORDERS BLIND" in shard["title"]
    assert shard["source"] == sb._WORK_ORDER_STORE


def test_consumed_order_drops_off_the_wake(monkeypatch, tmp_path) -> None:
    rec = sb.bank_work_order("eigenengine", "dream", "gerard", root=tmp_path)
    sb.resolve_work_order(rec["id"], evidence_refs=["commit:abc1234"],
                          by="eigen", root=tmp_path)
    _force_substrate(monkeypatch)
    out = sc._grade0(tmp_path)
    assert [s for s in out["shards"] if s["shard"] == "work-orders"] == []


def test_grade0_folds_the_canonical_account_once_for_all_shards(monkeypatch, tmp_path) -> None:
    from laplace.engine import wake

    sb.bank_work_order("eigenengine", "dream", "gerard", root=tmp_path)
    promises = tmp_path / "contract" / "promises.jsonl"
    promises.parent.mkdir(parents=True)
    promises.write_text(json.dumps({
        "record": "promise", "id": "PRM-one-fold", "status": "open",
        "date": "2026-08-25", "owner": "Eigen", "ask": "fold me once",
    }) + "\n", encoding="utf-8")
    _force_substrate(monkeypatch)
    original = wake.account
    calls = 0

    def counted(root):
        nonlocal calls
        calls += 1
        return original(root)

    monkeypatch.setattr(wake, "account", counted)
    sc._grade0(tmp_path)
    assert calls == 1, "work-orders, promises and seats must share one canonical fold"


# ---------------------------------------------------------------------------
# SURFACE #2 — the DESK. the work-orders class + row.
# ---------------------------------------------------------------------------

def test_desk_surfaces_open_work_order(tmp_path) -> None:
    rec = sb.bank_work_order("eigenengine", "dream", "gerard", root=tmp_path)
    d = desk._desk(tmp_path)
    strata = {s["class"]: s for s in d["classes"]}
    assert "work-orders" in strata
    assert strata["work-orders"]["count"] == 1
    assert strata["work-orders"]["verbs"] == ["consume"]
    rows = [r for r in d["rows"] if r["class"] == "work-orders"]
    assert len(rows) == 1
    assert rows[0]["id"] == rec["id"]
    assert rows[0]["verbs"] == ["consume"]
    assert rows[0]["fields"]["id"] == rec["id"]        # door-ready target


def test_desk_work_orders_are_engine_owned_not_his_badge(tmp_path) -> None:
    sb.bank_work_order("eigenengine", "dream", "gerard", root=tmp_path)
    d = desk._desk(tmp_path)
    meta = {s["class"]: s for s in d["classes"]}["work-orders"]
    assert meta["owner"] == "engine"                   # picked up by a session, not him


# ---------------------------------------------------------------------------
# CONSUME — the direct executor: fail-closed on no evidence / no actor / re-consume.
# ---------------------------------------------------------------------------

def test_resolve_without_evidence_refused_stays_open(tmp_path) -> None:
    rec = sb.bank_work_order("eigenengine", "re-projection", "gerard", root=tmp_path)
    st, obj = sb.resolve_work_order(rec["id"], evidence_refs=[], by="eigen", root=tmp_path)
    assert st == 422 and obj["ok"] is False and obj["still_open"] is True
    # NOTHING written on the evidence-less path — the order stays OPEN, rides next wake.
    recs = sb.load_work_orders(tmp_path)
    assert len(recs) == 1
    assert len(sb.open_work_orders(recs)) == 1


def test_resolve_empty_string_evidence_refused(tmp_path) -> None:
    rec = sb.bank_work_order("eigenengine", "dream", "gerard", root=tmp_path)
    st, obj = sb.resolve_work_order(rec["id"], evidence_refs="   ", by="eigen", root=tmp_path)
    assert st == 422 and obj["ok"] is False
    assert len(sb.open_work_orders(sb.load_work_orders(tmp_path))) == 1


def test_resolve_nonstring_evidence_refused_stays_open(tmp_path) -> None:
    """The W5.3 judge's fail-closed hole: str(None) is a truthy "None", so an
    evidence list of [null] would coerce to ['None'], pass the presence gate,
    and close the order with a FABRICATED ref. Non-string elements are absent
    evidence — every one of these must refuse and leave the order open."""
    rec = sb.bank_work_order("eigenengine", "harnessed-round", "gerard", root=tmp_path)
    for bad in ([None], [0], [[]], [None, ""], [{}]):
        st, obj = sb.resolve_work_order(rec["id"], evidence_refs=bad, by="eigen", root=tmp_path)
        assert st == 422 and obj["ok"] is False, bad
        assert len(sb.open_work_orders(sb.load_work_orders(tmp_path))) == 1, bad
    # a real string ref mixed with junk keeps ONLY the string — and may close.
    st, obj = sb.resolve_work_order(rec["id"], evidence_refs=[None, "rounds/harnessed/mech_r1.json"],
                                    by="eigen", root=tmp_path)
    assert st == 200 and obj["resolution"]["evidence"] == ["rounds/harnessed/mech_r1.json"]


def test_resolve_with_evidence_closes_and_banks(tmp_path) -> None:
    rec = sb.bank_work_order("eigenengine", "harnessed-round", "gerard", root=tmp_path)
    refs = ["commit:deadbee", "rounds/harnessed/detect_post_r2.json"]
    st, obj = sb.resolve_work_order(rec["id"], evidence_refs=refs, by="eigen",
                                    reason="ran r2 remote", root=tmp_path)
    assert st == 200 and obj["ok"] is True and obj["consumed"] == rec["id"]
    assert obj["evidence"] == refs
    recs = sb.load_work_orders(tmp_path)
    assert len(recs) == 2                               # order + its resolution
    res = recs[1]
    assert res["record"] == "resolution"
    assert res["supersedes"] == rec["id"] and res["consumes"] == rec["id"]
    assert res["evidence"] == refs                      # the evidence is BANKED
    assert res["source"] == "eigen"                     # actor-attributed
    # the order is now consumed, off the open set.
    assert sb.open_work_orders(recs) == []
    assert [t["id"] for t in sb.consumed_work_orders(recs)] == [rec["id"]]


def test_resolve_accepts_a_single_string_ref(tmp_path) -> None:
    rec = sb.bank_work_order("eigenengine", "dream", "gerard", root=tmp_path)
    st, obj = sb.resolve_work_order(rec["id"], evidence_refs="commit:abc1234",
                                    by="eigen", root=tmp_path)
    assert st == 200 and obj["evidence"] == ["commit:abc1234"]


def test_resolve_unattributed_refused(tmp_path) -> None:
    rec = sb.bank_work_order("eigenengine", "dream", "gerard", root=tmp_path)
    st, obj = sb.resolve_work_order(rec["id"], evidence_refs=["x"], by="", root=tmp_path)
    assert st == 422 and "by required" in obj["error"]
    assert len(sb.load_work_orders(tmp_path)) == 1      # nothing written


def test_resolve_missing_order_404(tmp_path) -> None:
    store = tmp_path / sb._WORK_ORDER_STORE
    store.parent.mkdir(parents=True)
    store.touch()
    st, obj = sb.resolve_work_order("WO-nope", evidence_refs=["x"], by="eigen", root=tmp_path)
    assert st == 404 and obj["ok"] is False


def test_resolve_refuses_when_the_authoritative_store_is_missing(tmp_path) -> None:
    st, obj = sb.resolve_work_order("WO-nope", evidence_refs=["x"], by="eigen", root=tmp_path)
    assert st == 409 and obj["ok"] is False and obj["cracked"] is True
    assert obj["still_open"] is None


def test_reconsume_already_closed_409(tmp_path) -> None:
    rec = sb.bank_work_order("eigenengine", "dream", "gerard", root=tmp_path)
    sb.resolve_work_order(rec["id"], evidence_refs=["x"], by="eigen", root=tmp_path)
    st, obj = sb.resolve_work_order(rec["id"], evidence_refs=["y"], by="eigen", root=tmp_path)
    assert st == 409 and obj["ok"] is False


# ---------------------------------------------------------------------------
# CONSUME — through the DESK ACT DOOR (the adjudicate idiom, actor-guarded).
# ---------------------------------------------------------------------------

def _act(payload: dict) -> tuple[int, dict]:
    st, _ct, raw = desk.handle("/desk/act", {}, "POST",
                                json.dumps(payload).encode("utf-8"))
    return st, json.loads(raw)


def test_consume_through_door_without_evidence_refused(monkeypatch, tmp_path) -> None:
    import laplace.web.scanner as scanner
    monkeypatch.setattr(scanner, "_repo_root", lambda: tmp_path)
    rec = sb.bank_work_order("eigenengine", "dream", "gerard", root=tmp_path)
    st, obj = _act({"class": "work-orders", "verb": "consume",
                    "id": rec["id"], "by": "eigen"})
    assert st == 422 and obj["ok"] is False
    assert len(sb.open_work_orders(sb.load_work_orders(tmp_path))) == 1


def test_consume_through_door_with_evidence_closes(monkeypatch, tmp_path) -> None:
    import laplace.web.scanner as scanner
    monkeypatch.setattr(scanner, "_repo_root", lambda: tmp_path)
    rec = sb.bank_work_order("eigenengine", "harnessed-round", "gerard", root=tmp_path)
    refs = ["commit:abc123", "rounds/harnessed/mech_r2.json"]
    st, obj = _act({"class": "work-orders", "verb": "consume", "id": rec["id"],
                    "by": "eigen", "evidence_refs": refs})
    assert st == 200 and obj["ok"] is True
    assert obj["evidence"] == refs
    assert sb.open_work_orders(sb.load_work_orders(tmp_path)) == []


def test_consume_through_door_unattributed_refused(monkeypatch, tmp_path) -> None:
    import laplace.web.scanner as scanner
    monkeypatch.setattr(scanner, "_repo_root", lambda: tmp_path)
    rec = sb.bank_work_order("eigenengine", "dream", "gerard", root=tmp_path)
    # no `by` — the actor guard refuses BEFORE any executor runs, 422, zero delta.
    st, obj = _act({"class": "work-orders", "verb": "consume",
                    "id": rec["id"], "evidence_refs": ["x"]})
    assert st == 422 and "by" in obj["error"]
    assert len(sb.open_work_orders(sb.load_work_orders(tmp_path))) == 1


def test_consume_through_door_missing_id(monkeypatch, tmp_path) -> None:
    import laplace.web.scanner as scanner
    monkeypatch.setattr(scanner, "_repo_root", lambda: tmp_path)
    st, obj = _act({"class": "work-orders", "verb": "consume",
                    "by": "eigen", "evidence_refs": ["x"]})
    assert st == 422 and "id required" in obj["error"]
