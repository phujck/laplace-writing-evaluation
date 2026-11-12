"""The canonical account and the pickup door share one work-order state fold."""
from __future__ import annotations

import json

from laplace.engine import wake


def test_work_order_account_refuses_an_evidenceless_close(tmp_path):
    """Status prose is not state: a close without evidence retires nothing."""
    (tmp_path / "contract").mkdir(parents=True)
    store = tmp_path / "corpus_friction"
    store.mkdir(parents=True)
    (tmp_path / "contract" / "promises.jsonl").write_text("", encoding="utf-8")
    rows = [
        {"record": "work-order", "id": "WO-proof", "status": "open"},
        {"record": "resolution", "id": "RES-bare", "consumes": "WO-proof",
         "status": "resolved"},
    ]
    path = store / "work_orders.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    bare = wake.account(tmp_path)
    assert bare["work_orders"]["open"] == 1
    assert any(d["defect"] == "work-order-resolution-without-evidence"
               for d in bare["defects"])

    rows[1]["evidence"] = ["commit:proved"]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    assert wake.account(tmp_path)["work_orders"]["open"] == 0


def test_later_evidenced_close_cures_the_active_residual_without_rewriting_history():
    rows = [
        {"record": "work-order", "id": "WO-proof", "status": "open"},
        {"record": "resolution", "id": "RES-bare", "consumes": "WO-proof"},
        {"record": "resolution", "id": "RES-proof", "consumes": "WO-proof",
         "evidence": ["commit:proved"]},
    ]
    account = wake.ledger_account(rows, "work_order", "work_orders")
    assert account["open"] == 0
    assert not any(d["defect"] == "work-order-resolution-without-evidence"
                   for d in account["defects"])
    assert rows[1] == {"record": "resolution", "id": "RES-bare",
                       "consumes": "WO-proof"}


def test_evidenceless_reopen_changes_no_state_and_later_proof_cures_residual():
    rows = [
        {"record": "work-order", "id": "WO-proof", "status": "open"},
        {"record": "resolution", "id": "RES-close", "consumes": "WO-proof",
         "evidence": ["commit:close"]},
        {"record": "resolution", "id": "RES-bare-reopen", "target": "WO-proof",
         "text": "HELD OPEN"},
    ]
    refused = wake.ledger_account(rows, "work_order", "work_orders")
    assert refused["open"] == 0
    defect = next(d for d in refused["defects"]
                  if d["defect"] == "work-order-resolution-without-evidence")
    assert defect["attempted_disposition"] == "reopen"

    rows.append({"record": "resolution", "id": "RES-proved-reopen",
                 "target": "WO-proof", "text": "HELD OPEN",
                 "evidence": ["finding:reopen"]})
    reopened = wake.ledger_account(rows, "work_order", "work_orders")
    assert reopened["open"] == 1
    assert reopened["held_open_by_resolution"] == ["WO-proof"]
    assert not any(d["defect"] == "work-order-resolution-without-evidence"
                   for d in reopened["defects"])


def test_noncanonical_authenticated_hold_spelling_reopens_instead_of_discharging():
    rows = [
        {"record": "work-order", "id": "WO-hold", "status": "open"},
        {"record": "resolution", "id": "RES-hold", "target": "WO-hold",
         "note": "Held\n  Open pending the author walk",
         "evidence": ["finding:reopen"]},
    ]
    account = wake.ledger_account(rows, "work_order", "work_orders")
    assert account["open"] == 1
    assert account["held_open_by_resolution"] == ["WO-hold"]
    assert not account["defects"]


def test_malformed_latest_defer_is_unknown_not_immortal_or_older_fallback():
    rows = [
        {"record": "work-order", "id": "WO-date", "status": "open"},
        {"record": "defer", "id": "DEFER-old", "target": "WO-date",
         "defer_until": "2026-09-01", "deferred_by": "eigen"},
        {"record": "defer", "id": "DEFER-poison", "target": "WO-date",
         "defer_until": "2026-13-45", "deferred_by": "eigen"},
    ]
    account = wake.ledger_account(rows, "work_order", "work_orders", as_of="2026-08-25")
    assert account["open"] == 1 and account["deferred"] == 0
    assert any(d["defect"] == "invalid-defer-until" for d in account["defects"])


def test_declared_condition_sentinel_uses_the_named_trigger():
    rows = [
        {"record": "work-order", "id": "WO-condition", "status": "open"},
        {"record": "defer", "id": "DEFER-condition", "target": "WO-condition",
         "defer_until": "condition", "trigger": "when the sample arrives",
         "deferred_by": "eigen"},
    ]
    account = wake.ledger_account(rows, "work_order", "work_orders")
    assert account["open"] == 0 and account["deferred"] == 1
    assert not any(d["defect"] == "invalid-defer-until" for d in account["defects"])


def test_promise_resolution_links_receive_the_same_semantic_diagnostics():
    rows = [
        {"record": "promise", "id": "PRM-victim", "status": "open"},
        {"record": "resolution", "id": "RES-poison",
         "target": {"id": "PRM-victim"}, "evidence": ["finding:poison"]},
    ]
    account = wake.ledger_account(rows, "promise", "promises")
    assert account["open"] == 1
    wound = next(d for d in account["defects"]
                 if d["defect"] == "invalid-resolution-link")
    assert wound["store"] == "promises" and wound["field"] == "target"


def test_account_and_shared_classifier_admit_memo_kind_and_prefix_only_orders():
    rows = [
        {"record": "memo", "kind": "work-order", "id": "WO-memo", "status": "open"},
        {"id": "WO-prefix", "status": "open"},
    ]
    account = wake.ledger_account(rows, "work_order", "work_orders")
    assert {row["id"] for row in account["open_rows"]} == {"WO-memo", "WO-prefix"}
    assert not any(d["defect"] == "unclassifiable-row" for d in account["defects"])


def test_defer_cannot_resurrect_an_evidence_discharged_order(tmp_path):
    (tmp_path / "contract").mkdir(parents=True)
    store = tmp_path / "corpus_friction"
    store.mkdir(parents=True)
    (tmp_path / "contract" / "promises.jsonl").write_text("", encoding="utf-8")
    rows = [
        {"record": "work-order", "id": "WO-done", "status": "open"},
        {"record": "resolution", "id": "RES-done", "consumes": "WO-done",
         "evidence": ["commit:done"]},
        {"record": "defer", "id": "DEFER-stale", "target": "WO-done",
         "defer_until": "2099-01-01", "deferred_by": "eigen"},
    ]
    (store / "work_orders.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    account = wake.account(tmp_path)
    assert account["work_orders"]["open"] == account["work_orders"]["deferred"] == 0
    assert any(d["defect"] == "defer-after-resolution" for d in account["defects"])


def test_past_defer_reopens_and_surfaces_as_lapsed():
    rows = [
        {"record": "work-order", "id": "WO-due", "status": "open"},
        {"record": "defer", "id": "DEFER-due", "target": "WO-due",
         "defer_until": "2026-08-24", "deferred_by": "eigen"},
    ]
    account = wake.ledger_account(rows, "work_order", "work_orders", as_of="2026-08-25")
    assert account["open"] == 1 and account["deferred"] == 0
    assert account["lapsed_deferred"] == 1
    assert account["lapsed_deferred_rows"][0]["id"] == "WO-due"
    assert any(d["defect"] == "lapsed-defer" for d in account["defects"])


def test_later_future_defer_supersedes_an_historical_lapse():
    rows = [
        {"record": "work-order", "id": "WO-later", "status": "open"},
        {"record": "defer", "id": "DEFER-old", "target": "WO-later",
         "defer_until": "2026-08-24", "deferred_by": "eigen"},
        {"record": "defer", "id": "DEFER-new", "target": "WO-later",
         "defer_until": "2026-09-01", "deferred_by": "eigen"},
    ]
    account = wake.ledger_account(rows, "work_order", "work_orders", as_of="2026-08-25")
    assert account["open"] == account["lapsed_deferred"] == 0
    assert account["deferred"] == 1
