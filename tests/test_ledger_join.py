"""tests/test_ledger_join.py — WO-20260820-ledger-semantics-hardening, cures (a)/(c)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from laplace.engine import engine_ledger
from laplace.manuscript import storyboard
from laplace.core.records.rows import load_records
from laplace.pipeline.ledger import integrity_projection, read_jsonl_diagnosed


def test_normalize_kind_hyphenates_underscore():
    assert engine_ledger.normalize_kind("work_order") == "work-order"
    assert engine_ledger.normalize_kind("work-order") == "work-order"


def test_normalize_kind_passthrough_on_non_string():
    assert engine_ledger.normalize_kind(None) is None
    assert engine_ledger.normalize_kind("") == ""


def test_row_kind_prefers_kind_field():
    row = {"kind": "work-order", "record": "resolution"}
    assert engine_ledger.row_kind(row) == "work-order"


def test_row_kind_falls_back_to_record_when_kind_absent():
    row = {"record": "work_order"}
    assert engine_ledger.row_kind(row) == "work-order"


def test_row_kind_falls_back_when_kind_empty_string():
    row = {"kind": "", "record": "resolution"}
    assert engine_ledger.row_kind(row) == "resolution"


def test_is_work_order_accepts_either_spelling():
    assert engine_ledger.is_work_order({"kind": "work-order"})
    assert engine_ledger.is_work_order({"record": "work_order"})
    assert not engine_ledger.is_work_order({"kind": "note"})


def test_work_order_record_class_wins_over_its_kind_subtype():
    assert engine_ledger.is_work_order({"record": "work_order", "kind": "instrument"})
    assert not engine_ledger.is_work_order({"record": "resolution", "kind": "work-order"})


def test_semantic_classifier_falls_through_unknown_record_and_typed_prefix():
    memo = {"record": "memo", "kind": "work-order", "id": "WO-memo"}
    prefix_only = {"id": "WO-prefix"}
    assert engine_ledger.classify_row(memo) == ("work_order", "kind")
    assert engine_ledger.is_work_order(memo)
    assert engine_ledger.classify_row(prefix_only) == ("work_order", "id-prefix")
    assert engine_ledger.is_work_order(prefix_only)


def test_atlas_evidence_classes_beat_misleading_id_prefixes():
    walked = {"record": "walk-verdict", "id": "RES-20260825-a-walk"}
    assert engine_ledger.classify_row(walked) == ("walk_verdict", "record")
    assert not engine_ledger.is_resolution(walked)
    for token in (
        "verdict", "finding", "walk-verdict-retraction", "shown-custody-link",
        "want", "synthesis",
    ):
        assert engine_ledger.record_class({"record": token, "id": "X-row"}) == (
            token.replace("-", "_")
        )


def test_resolution_class_prefers_record_and_accepts_kind_only_history():
    assert engine_ledger.is_resolution({"record": "resolution", "kind": "engineering"})
    assert engine_ledger.is_resolution({"kind": "resolution"})
    assert not engine_ledger.is_resolution({"record": "amendment", "kind": "resolution"})


def test_resolution_targets_fold_every_historical_link_once():
    row = {"record": "resolution", "consumes": "WO-a", "supersedes": "WO-a",
           "target": "WO-b", "consumed_by": "WO-c"}
    assert engine_ledger.resolution_targets(row) == ("WO-a", "WO-b", "WO-c")
    assert engine_ledger.resolution_targets({"record": "amendment", "target": "WO-a"}) == ()


def test_load_records_skips_malformed_lines(tmp_path: Path):
    p = tmp_path / "ledger.jsonl"
    p.write_text('{"id": "A"}\nnot json\n\n{"id": "B"}\n', encoding="utf-8")
    recs = load_records(p)
    assert [r["id"] for r in recs] == ["A", "B"]


def test_the_shared_reader_preserves_the_exact_integrity_residual(tmp_path: Path):
    """Tolerance is a partial projection, never permission to lose the wound."""
    p = tmp_path / "ledger.jsonl"
    p.write_text('{"id":"A"}\n{"id":\n{"id":"B"}\n', encoding="utf-8")
    rows, residuals = read_jsonl_diagnosed(p, store="the-ledger")
    assert [r["id"] for r in rows] == ["A", "B"]
    assert len(residuals) == 1
    assert residuals[0]["defect"] == "unparseable-row"
    assert residuals[0]["store"] == "the-ledger" and residuals[0]["line"] == 2
    assert residuals[0]["path"] == str(p)


def test_valid_json_with_the_wrong_row_shape_is_still_a_wound(tmp_path: Path):
    p = tmp_path / "ledger.jsonl"
    p.write_text('{"id":"A"}\n["not", "an", "object"]\n', encoding="utf-8")
    rows, residuals = read_jsonl_diagnosed(p, store="the-ledger")
    assert rows == [{"id": "A"}]
    assert residuals[0]["defect"] == "non-object-row" and residuals[0]["line"] == 2


def test_integrity_projection_is_bounded_but_commits_to_the_whole_residual_set():
    wounds = [{"defect": "unparseable-row", "store": "x", "line": n,
               "error": "bad"} for n in range(100)]
    projected = integrity_projection(wounds, cap=3)
    assert projected["residual_count"] == 100 and len(projected["residuals"]) == 3
    assert projected["residuals_truncated"] and projected["residuals_omitted"] == 97
    assert projected["residual_handle"].startswith("sha256:")
    changed = integrity_projection(wounds[:-1] + [{**wounds[-1], "line": 999}], cap=3)
    assert changed["residuals"] == projected["residuals"]
    assert changed["residual_handle"] != projected["residual_handle"]


def test_load_records_missing_file_returns_empty(tmp_path: Path):
    assert load_records(tmp_path / "nope.jsonl") == []


def test_shared_reader_distinguishes_optional_from_required_absence(tmp_path: Path):
    missing = tmp_path / "missing.jsonl"
    assert read_jsonl_diagnosed(missing) == ([], [])
    rows, residuals = read_jsonl_diagnosed(
        missing, store="required-ledger", required=True)
    assert rows == []
    assert residuals[0]["defect"] == "store-unreadable"
    assert residuals[0]["integrity_class"] == "physical-store-integrity"
    assert "missing path" in residuals[0]["error"]


def test_required_dangling_symlink_is_a_named_wound(tmp_path: Path):
    link = tmp_path / "ledger.jsonl"
    link.symlink_to(tmp_path / "absent-target.jsonl")
    _rows, residuals = read_jsonl_diagnosed(link, required=True)
    assert residuals[0]["defect"] == "store-unreadable"
    assert "dangling symlink" in residuals[0]["error"]


def test_poison_residual_handle_commits_to_exact_poison_bytes(tmp_path: Path):
    path = tmp_path / "ledger.jsonl"
    path.write_text('{"id":\n', encoding="utf-8")
    _rows, first = read_jsonl_diagnosed(path)
    path.write_text('{"id":   \n', encoding="utf-8")
    _rows, second = read_jsonl_diagnosed(path)
    assert first[0]["source_handle"] != second[0]["source_handle"]
    assert (integrity_projection(first)["residual_handle"]
            != integrity_projection(second)["residual_handle"])


def test_integrity_surface_bounds_long_strings_without_weakening_commitment():
    wound = {"defect": "store-unreadable", "path": "/" + "x" * 20_000,
             "error": "bad" * 20_000}
    projected = integrity_projection([wound])
    shown = projected["residuals"][0]
    assert len(shown["path"]) <= 240 and shown["path_truncated"]
    assert len(shown["error"]) <= 240 and shown["error_truncated"]
    assert len(json.dumps(projected).encode("utf-8")) < 4_000


def test_residual_handle_is_portable_across_clone_paths():
    common = {
        "integrity_class": "physical-store-integrity",
        "defect": "unparseable-row",
        "store": "work_orders",
        "line": 7,
        "source_handle": "sha256:poison",
        "error": "JSONDecodeError: broken row",
    }
    left = integrity_projection([{**common, "path": "/clone-a/work_orders.jsonl"}])
    right = integrity_projection([{**common, "path": "/clone-b/work_orders.jsonl"}])
    assert left["residual_handle"] == right["residual_handle"]
    assert left["residuals"][0]["path"] != right["residuals"][0]["path"]


def test_semantic_resolution_poison_cracks_the_typed_work_order_face(tmp_path: Path):
    store = tmp_path / "corpus_friction" / "work_orders.jsonl"
    store.parent.mkdir(parents=True)
    store.write_text(json.dumps({
        "record": "resolution", "id": "RES-poison",
        "target": {"id": "WO-victim"}, "supersedes": None,
    }) + "\n", encoding="utf-8")
    rows, residuals = storyboard.load_work_orders_diagnosed(tmp_path)
    assert rows[0]["id"] == "RES-poison"
    assert residuals[0]["integrity_class"] == "semantic-ledger-integrity"
    assert residuals[0]["defect"] == "invalid-resolution-link"
    assert residuals[0]["field"] == "target"
    assert residuals[0]["source_handle"].startswith("sha256:")

    status, body = storyboard.resolve_work_order(
        "WO-victim", evidence_refs=["commit:x"], by="test", root=tmp_path)
    assert status == 409 and body["cracked"]


def test_bench_resolver_refuses_every_physical_defect_class(tmp_path: Path):
    import reconstruction_bench_resolvers as resolvers

    store = tmp_path / "corpus_friction" / "work_orders.jsonl"
    store.parent.mkdir(parents=True)
    store.write_text('["valid JSON", "wrong row shape"]\n', encoding="utf-8")
    with pytest.raises(ValueError, match="work_orders ledger wounded"):
        resolvers._wo_open(tmp_path)


def test_build_consumption_index_keys_by_consumes():
    records = [
        {"record": "work_order", "id": "WO-1", "status": "open"},
        {"record": "resolution", "id": "RES-1", "consumes": "WO-1", "status": "resolved",
         "evidence": ["commit:proved"]},
    ]
    index = engine_ledger.build_consumption_index(records)
    assert "WO-1" in index
    assert index["WO-1"]["id"] == "RES-1"


def test_build_consumption_index_ignores_non_resolution_records():
    records = [{"record": "note", "id": "N-1", "consumes": "WO-1"}]
    index = engine_ledger.build_consumption_index(records)
    assert index == {}


def test_build_consumption_index_refuses_evidenceless_work_order_close():
    records = [
        {"record": "work_order", "id": "WO-proof", "status": "open"},
        {"record": "resolution", "id": "RES-bare", "consumes": "WO-proof"},
    ]
    assert engine_ledger.build_consumption_index(records) == {}


def test_build_consumption_index_refuses_evidenceless_work_order_reopen():
    records = [
        {"record": "work-order", "id": "WO-proof", "status": "open"},
        {"record": "resolution", "id": "RES-bare", "consumes": "WO-proof",
         "text": "HELD OPEN"},
    ]
    assert engine_ledger.build_consumption_index(records) == {}


def test_authenticated_reopen_is_last_disposition_and_reads_open():
    records = [
        {"record": "work-order", "id": "WO-proof", "status": "open"},
        {"record": "resolution", "id": "RES-close", "consumes": "WO-proof",
         "evidence": ["commit:close"]},
        {"record": "resolution", "id": "RES-reopen", "target": "WO-proof",
         "text": "HELD OPEN", "evidence": ["finding:reopen"]},
    ]
    index = engine_ledger.build_consumption_index(records)
    assert index["WO-proof"]["id"] == "RES-reopen"
    assert engine_ledger.effective_status("WO-proof", "open", index) == (
        "open", "reopened_by:RES-reopen")


@pytest.mark.parametrize("field,value", [
    ("text", "Held Open"),
    ("text", "HELD  OPEN"),
    ("text", "held open"),
    ("text", "HELD\nOPEN"),
    ("note", "held-open pending the judge"),
    ("reason", "[ OPEN ] until the author walk"),
])
def test_authenticated_legacy_hold_variants_cannot_invert_to_close(field, value):
    rows = [
        {"record": "work-order", "id": "WO-proof", "status": "open"},
        {"record": "resolution", "id": "RES-hold", "target": "WO-proof",
         field: value, "evidence": ["finding:hold"]},
    ]
    index = engine_ledger.build_consumption_index(rows)
    assert engine_ledger.resolution_disposition(rows[1]) == engine_ledger.RESOLUTION_REOPEN
    assert engine_ledger.effective_status("WO-proof", "open", index) == (
        "open", "reopened_by:RES-hold")


def test_unknown_typed_resolution_disposition_is_loud_and_changes_no_state():
    rows = [
        {"record": "work-order", "id": "WO-proof", "status": "open"},
        {"record": "resolution", "id": "RES-unknown", "target": "WO-proof",
         "disposition": "perhaps", "evidence": ["finding:unknown"]},
    ]
    assert engine_ledger.build_consumption_index(rows) == {}
    wounds = engine_ledger.obligation_semantic_diagnostics(rows, store="work_orders")
    assert wounds[0]["defect"] == "invalid-resolution-disposition"


def test_effective_status_overridden_by_resolution():
    index = {"WO-1": {"id": "RES-1", "status": "resolved"}}
    eff, reason = engine_ledger.effective_status("WO-1", "open", index)
    assert eff == "resolved"
    assert reason == "consumed_by:RES-1"


def test_effective_status_defaults_to_resolved_when_resolution_carries_no_status():
    index = {"WO-1": {"id": "RES-1"}}
    eff, reason = engine_ledger.effective_status("WO-1", "open", index)
    assert eff == "resolved"


def test_effective_status_stands_when_row_not_consumed():
    eff, reason = engine_ledger.effective_status("WO-2", "open", {})
    assert eff == "open"
    assert reason == "stored"


def test_effective_status_for_row_reads_id_and_status():
    index = {"WO-1": {"id": "RES-1", "status": "resolved"}}
    row = {"id": "WO-1", "status": "open"}
    eff, reason = engine_ledger.effective_status_for_row(row, index)
    assert eff == "resolved"


def test_effective_status_for_row_defaults_status_to_open():
    row = {"id": "WO-3"}
    eff, reason = engine_ledger.effective_status_for_row(row, {})
    assert eff == "open"


def test_against_live_ledger_the_stored_status_never_mutated(tmp_path: Path):
    """Sanity check against the real corpus shape: a RES row consuming a WO id must
    never change what's on disk, only what the join computes."""
    repo = Path(__file__).resolve().parent.parent
    ledger = repo / "corpus_friction" / "work_orders.jsonl"
    if not ledger.exists():
        return
    records = load_records(ledger)
    before = json.dumps(records[:5])
    index = engine_ledger.build_consumption_index(records)
    after = json.dumps(records[:5])
    assert before == after
    assert isinstance(index, dict)


# ---------------------------------------------------------------------------
# WO-20260820-ledger-semantics-hardening, second pass: the link-field fallback
# (cure a, completed), the strikes definition (cure b), and the read-time kind
# normalization wired into the shared readers (cure c, completed).
# ---------------------------------------------------------------------------


def test_index_falls_back_to_supersedes_when_consumes_absent():
    """23 live resolutions carry supersedes+target and no consumes; a consumes-only
    index read every one of their targets as still open."""
    rows = [{"record": "work-order", "id": "WO-a", "status": "open"},
            {"record": "resolution", "id": "RES-a", "supersedes": "WO-a",
             "target": "WO-a", "evidence": ["commit:a"]}]
    index = engine_ledger.build_consumption_index(rows)
    eff, reason = engine_ledger.effective_status_for_row(rows[0], index)
    assert eff == "resolved"
    assert reason == "consumed_by:RES-a"


def test_index_falls_back_to_target_when_it_is_the_only_link():
    rows = [{"record": "work-order", "id": "WO-b", "status": "open"},
            {"record": "resolution", "id": "RES-b", "target": "WO-b",
             "evidence": ["commit:b"]}]
    index = engine_ledger.build_consumption_index(rows)
    assert engine_ledger.effective_status_for_row(rows[0], index)[0] == "resolved"


def test_index_falls_back_to_consumed_by_and_kind_only_resolution():
    rows = [{"record": "work-order", "id": "WO-by", "status": "open"},
            {"kind": "resolution", "id": "RES-by", "consumed_by": "WO-by",
             "evidence": ["commit:by"]}]
    index = engine_ledger.build_consumption_index(rows)
    assert engine_ledger.effective_status_for_row(rows[0], index)[0] == "resolved"


def test_consumes_wins_over_supersedes_for_the_same_id():
    """Precedence, not first-writer-wins: `consumes` is the schema's join field."""
    rows = [{"record": "resolution", "id": "RES-super", "supersedes": "WO-c",
             "evidence": ["commit:super"]},
            {"record": "resolution", "id": "RES-consumes", "consumes": "WO-c",
             "status": "deferred", "evidence": ["commit:consumes"]}]
    index = engine_ledger.build_consumption_index(rows)
    eff, reason = engine_ledger.effective_status("WO-c", "open", index)
    assert (eff, reason) == ("deferred", "consumed_by:RES-consumes")


def test_prose_annotated_consumes_still_resolves_through_supersedes():
    """The live RES-20260820-dreamer-freeze-flag shape: a prose-annotated `consumes`
    plus a clean `supersedes`. BOTH ids index, so neither reading is lost."""
    rows = [{"record": "resolution", "id": "RES-d",
             "consumes": "WO-d (leg 1 only)", "supersedes": "WO-d", "target": "WO-d",
             "evidence": ["commit:d"]}]
    index = engine_ledger.build_consumption_index(rows)
    assert engine_ledger.effective_status("WO-d", "open", index)[0] == "resolved"
    assert engine_ledger.effective_status("WO-d (leg 1 only)", "open", index)[0] == "resolved"


def test_non_resolution_rows_never_link_even_with_target():
    """Amendments carry `target` constantly; they must never close their target."""
    rows = [{"record": "amendment", "id": "AMEND-e", "target": "WO-e"}]
    index = engine_ledger.build_consumption_index(rows)
    assert engine_ledger.effective_status("WO-e", "open", index) == ("open", "stored")


def test_strikes_exempt_reads_a_declared_string():
    assert engine_ledger.strikes_exempt({"strikes": engine_ledger.STRIKES_EXEMPLAR})
    assert engine_ledger.row_strikes({"strikes": "  "}) is None
    assert not engine_ledger.strikes_exempt({})
    assert not engine_ledger.strikes_exempt({"strikes": True})  # not a declaration


def test_strikes_exemplar_matches_the_live_promise_ledger():
    """Cure (b): the exemplar in the schema docstring is the promise ledger's own
    live value, not a paraphrase of it."""
    repo = Path(__file__).resolve().parent.parent
    promises = repo / "contract" / "promises.jsonl"
    if not promises.exists():
        return
    values = {r["strikes"] for r in load_records(promises) if r.get("strikes")}
    if values:
        assert engine_ledger.STRIKES_EXEMPLAR in values


def test_storyboard_open_orders_see_record_only_work_orders(tmp_path: Path):
    """Cure (c) with its bite: a row written `record: "work_order"` with no `kind`
    field is a work-order and must ride the wake's open list."""
    from laplace.manuscript import storyboard

    store = tmp_path / "corpus_friction"
    store.mkdir()
    (store / "work_orders.jsonl").write_text(
        json.dumps({"record": "work_order", "id": "WO-hidden", "status": "open"}) + "\n"
        + json.dumps({"kind": "work-order", "id": "WO-visible", "status": "open"}) + "\n",
        encoding="utf-8")
    rows = storyboard.load_work_orders(tmp_path)
    assert {r["id"] for r in storyboard.open_work_orders(rows)} == {"WO-hidden", "WO-visible"}
