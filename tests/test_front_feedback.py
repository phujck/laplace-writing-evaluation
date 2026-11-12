from __future__ import annotations

import copy
import json
from pathlib import Path

from laplace.web import front_door, shared_ui
from laplace.engine import front_feedback as feedback


def _anchor(
    semantic_anchor: str = "work:walk:content-canvas", *,
    lens: str = "work", source: str = "source-v1", currentness: str = "CURRENT",
    route: dict | None = None,
) -> dict:
    return {
        "schema_version": feedback.ANCHOR_SCHEMA,
        "semantic_anchor": semantic_anchor,
        "kind": "object",
        "label": "Manuscript working canvas",
        "model_handle": "front-model:sha256:model",
        "shown_handle": "front-shown:sha256:shown",
        "selection": {
            "lens": lens,
            "focus": semantic_anchor,
            "edge": None,
            "grade": "detail",
            "exposition": "E3",
            "viewport": "wide",
        },
        "source": {"source_handle": source},
        "currentness": {"status": currentness},
        "selection_geometry": {"x": 10, "y": 20, "width": 240, "height": 90},
        "screenshot": {"content_handle": "sha256:screenshot", "media_type": "image/png"},
        "route": route,
    }


def _create(adapter: feedback.InMemoryFeedbackAdapter, *, command_id: str = "cmd-1") -> dict:
    command = feedback.create_command(
        command_id=command_id,
        actor="gerard",
        text="Keep the feedback close to the sentence it refers to.",
        anchor=_anchor(route={"owner": "Aisthesis", "surface": "Work"}),
    )
    result = feedback.execute(adapter, command, occurred_at="2026-08-28T12:00:00Z")
    assert result["ok"] is True
    return result


def test_missing_canonical_adapter_refuses_without_fallback_ledger():
    command = feedback.create_command(
        command_id="cmd", actor="gerard", text="A note", anchor=_anchor()
    )
    result = feedback.execute(None, command, occurred_at="2026-08-28T12:00:00Z")
    assert result == {
        "ok": False,
        "status": "REFUSED",
        "refusal": "CANONICAL_ADAPTER_UNAVAILABLE",
        "reason": "Atlas has no adopted semantic-annotation writer; no fallback ledger was used",
        "authority_effect": "none",
    }
    projection = feedback.read(None)
    assert projection["persistence"]["available"] is False
    assert projection["persistence"]["refusal"] == "CANONICAL_ADAPTER_UNAVAILABLE"


def test_create_append_receipt_and_current_cross_lens_marker():
    adapter = feedback.InMemoryFeedbackAdapter([])
    result = _create(adapter)
    assert result["status"] == "APPENDED"
    assert result["position_handle"].startswith("front-feedback-position:sha256:")
    # The current camera may differ: semantic identity + source roots carry the marker.
    catalogue = [_anchor(lens="conversation")]
    projection = feedback.read(
        adapter,
        anchor_catalog=catalogue,
        catalog_complete=True,
        visible_anchor_ids=["work:walk:content-canvas"],
    )
    annotation = projection["annotations"][0]
    assert projection["status"] == "CURRENT"
    assert annotation["anchor_currentness"]["status"] == "CURRENT"
    assert annotation["anchor_currentness"]["visibility"] == "VISIBLE"
    assert annotation["anchor"]["selection"]["lens"] == "work"
    assert annotation["anchor"]["model_handle"] == "front-model:sha256:model"
    assert annotation["anchor"]["shown_handle"] == "front-shown:sha256:shown"


def test_route_is_visible_derivation_and_never_authority():
    adapter = feedback.InMemoryFeedbackAdapter([])
    _create(adapter)
    annotation = feedback.read(adapter)["annotations"][0]
    assert annotation["routing"]["state"] == "DERIVED"
    assert annotation["routing"]["route"] == {"owner": "Aisthesis", "surface": "Work"}
    assert annotation["routing"]["authority_granted"] is False
    assert annotation["routing"]["authority_effect"] == "none"


def test_changed_source_preserves_annotation_as_stale_with_reconcile_candidate():
    adapter = feedback.InMemoryFeedbackAdapter([])
    _create(adapter)
    moved = _anchor(source="source-v2")
    projection = feedback.read(adapter, anchor_catalog=[moved], catalog_complete=True)
    annotation = projection["annotations"][0]
    assert annotation["state"] == "OPEN"
    assert annotation["anchor_currentness"]["status"] == "STALE"
    assert annotation["anchor_currentness"]["reconcile_available"] is True
    assert annotation["anchor_currentness"]["reconcile_candidates"][0]["source"] == {
        "source_handle": "source-v2"
    }


def test_absent_anchor_is_stale_only_when_catalogue_is_complete():
    adapter = feedback.InMemoryFeedbackAdapter([])
    _create(adapter)
    partial = feedback.read(adapter, anchor_catalog=[], catalog_complete=False)
    complete = feedback.read(adapter, anchor_catalog=[], catalog_complete=True)
    assert partial["annotations"][0]["anchor_currentness"]["status"] == "UNKNOWN"
    assert complete["annotations"][0]["anchor_currentness"]["status"] == "STALE"


def test_reconcile_is_append_only_and_preserves_anchor_lineage():
    adapter = feedback.InMemoryFeedbackAdapter([])
    created = _create(adapter)
    command = feedback.reconcile_command(
        command_id="cmd-2",
        actor="gerard",
        annotation_id=created["annotation_id"],
        anchor=_anchor(source="source-v2"),
    )
    result = feedback.execute(adapter, command, occurred_at="2026-08-28T12:01:00Z")
    assert result["ok"] is True
    assert len(adapter.events) == 2
    annotation = feedback.read(
        adapter, anchor_catalog=[_anchor(source="source-v2")], catalog_complete=True
    )["annotations"][0]
    assert annotation["state"] == "OPEN"
    assert len(annotation["anchor_lineage"]) == 2
    assert annotation["anchor_currentness"]["status"] == "CURRENT"


def test_all_four_lifecycle_states_fold_without_rewriting_history():
    for state in ("RESOLVED", "WITHDRAWN"):
        adapter = feedback.InMemoryFeedbackAdapter([])
        created = _create(adapter)
        command = feedback.transition_command(
            command_id=f"cmd-{state}", actor="gerard",
            annotation_id=created["annotation_id"], state=state,
        )
        assert feedback.execute(
            adapter, command, occurred_at="2026-08-28T12:02:00Z"
        )["ok"] is True
        projection = feedback.read(adapter)
        assert projection["annotations"][0]["state"] == state
        assert len(adapter.events) == 2

    adapter = feedback.InMemoryFeedbackAdapter([])
    first = _create(adapter)
    second = _create(adapter, command_id="cmd-new")
    command = feedback.transition_command(
        command_id="cmd-super",
        actor="gerard",
        annotation_id=first["annotation_id"],
        state="SUPERSEDED",
        replacement_annotation_id=second["annotation_id"],
    )
    assert feedback.execute(
        adapter, command, occurred_at="2026-08-28T12:03:00Z"
    )["ok"] is True
    by_id = {row["annotation_id"]: row for row in feedback.read(adapter)["annotations"]}
    assert by_id[first["annotation_id"]]["state"] == "SUPERSEDED"
    assert by_id[first["annotation_id"]]["replacement_annotation_id"] == second["annotation_id"]


def test_duplicate_command_is_idempotent_not_duplicate_action():
    adapter = feedback.InMemoryFeedbackAdapter([])
    command = feedback.create_command(
        command_id="same", actor="gerard", text="one", anchor=_anchor()
    )
    first = feedback.execute(adapter, command, occurred_at="2026-08-28T12:00:00Z")
    second = feedback.execute(adapter, command, occurred_at="2026-08-28T12:09:00Z")
    assert first["status"] == "APPENDED"
    assert second["status"] == "IDEMPOTENT"
    assert second["annotation_id"] == first["annotation_id"]
    assert len(adapter.events) == 1


def test_forged_event_handle_or_event_id_refuses_projection():
    adapter = feedback.InMemoryFeedbackAdapter([])
    _create(adapter)
    forged_handle = copy.deepcopy(adapter.events[0])
    forged_handle["payload"]["text"] = "forged"
    projection = feedback.project([forged_handle])
    assert projection["status"] == "REFUSED"
    assert projection["annotations"] == []
    assert "does not match" in projection["defects"][0]

    forged_id = copy.deepcopy(adapter.events[0])
    forged_id["event_id"] = "front-feedback-event-id:sha256:forged"
    # Recompute the outer handle cannot launder the forged event id.
    without_handle = {k: v for k, v in forged_id.items() if k != "event_handle"}
    forged_id["event_handle"] = feedback.canonical_handle(
        without_handle, kind="front-feedback-event"
    )
    projection = feedback.project([forged_id])
    assert projection["status"] == "REFUSED"
    assert "event id" in projection["defects"][0]


def test_dom_location_and_authority_bearing_route_are_refused():
    dom = _anchor()
    dom["dom_path"] = "main > div:nth-child(2)"
    try:
        feedback.normalize_anchor(dom)
    except feedback.FeedbackRefused as exc:
        assert "DOM-location" in str(exc)
    else:
        raise AssertionError("DOM path was accepted")

    authority = _anchor(route={"owner": "Aisthesis", "authority": True})
    try:
        feedback.normalize_anchor(authority)
    except feedback.FeedbackRefused as exc:
        assert "cannot grant authority" in str(exc)
    else:
        raise AssertionError("authority-bearing route was accepted")


def test_optional_geometry_and_screenshot_are_exactly_bound():
    normalized = feedback.normalize_anchor(_anchor())
    assert normalized["selection_geometry"] == {
        "x": 10.0, "y": 20.0, "width": 240.0, "height": 90.0,
    }
    assert normalized["screenshot"] == {
        "content_handle": "sha256:screenshot", "media_type": "image/png",
    }
    changed = copy.deepcopy(normalized)
    changed.pop("anchor_handle")
    changed["selection_geometry"]["width"] = 241
    renormalized = feedback.normalize_anchor(changed)
    assert renormalized["anchor_handle"] != normalized["anchor_handle"]


def test_bad_adapter_receipt_cannot_claim_a_write():
    class BadAdapter(feedback.InMemoryFeedbackAdapter):
        def append_event(self, event):
            self.events.append(dict(event))
            return {"accepted": True, "event_handle": "wrong", "position_handle": "pos"}

    adapter = BadAdapter([])
    command = feedback.create_command(
        command_id="cmd", actor="gerard", text="one", anchor=_anchor()
    )
    result = feedback.execute(adapter, command, occurred_at="2026-08-28T12:00:00Z")
    assert result["status"] == "REFUSED"
    assert "does not bind" in result["reason"]


def test_live_front_feedback_door_is_honest_until_atlas_adapter_exists():
    status, content_type, body = front_door.handle("/front/feedback", {}, "GET", b"")
    projection = json.loads(body)
    assert status == 200
    assert content_type == "application/json; charset=utf-8"
    assert projection["status"] == "REFUSED"
    assert projection["persistence"] == {
        "required_adapter_schema": feedback.ADAPTER_SCHEMA,
        "available": False,
        "status": "REFUSED",
        "refusal": "CANONICAL_ADAPTER_UNAVAILABLE",
        "authority_effect": "none",
    }

    status, _, body = front_door.handle(
        "/front/feedback", {}, "POST",
        json.dumps(feedback.create_command(
            command_id="live-refusal", actor="gerard", text="Do not lose this thought",
            anchor=_anchor(),
        )).encode("utf-8"),
    )
    refusal = json.loads(body)
    assert status == 503
    assert refusal["refusal"] == "CANONICAL_ADAPTER_UNAVAILABLE"
    assert "canonical adapter read refused" in refusal["reason"]


def test_live_front_feedback_door_uses_the_injected_canonical_adapter(monkeypatch):
    adapter = feedback.InMemoryFeedbackAdapter([])
    monkeypatch.setattr(front_door, "_front_feedback_adapter", lambda: adapter)
    command = feedback.create_command(
        command_id="live-canonical-append",
        actor="gerard",
        text="Do not lose this thought",
        anchor=_anchor(),
    )

    status, content_type, body = front_door.handle(
        "/front/feedback", {}, "POST", json.dumps(command).encode("utf-8")
    )
    appended = json.loads(body)
    assert status == 200
    assert content_type == "application/json; charset=utf-8"
    assert appended["status"] == "APPENDED"
    assert len(adapter.events) == 1

    status, _, body = front_door.handle(
        "/front/feedback",
        {"visible_anchor": [_anchor()["semantic_anchor"]]},
        "GET",
        b"",
    )
    projection = json.loads(body)
    assert status == 200
    assert projection["status"] == "UNKNOWN"
    assert projection["persistence"] == {
        "required_adapter_schema": feedback.ADAPTER_SCHEMA,
        "available": True,
        "status": "CURRENT",
        "authority_effect": "none",
    }
    assert projection["annotations"][0]["text"] == "Do not lose this thought"
    assert projection["annotations"][0]["anchor_currentness"]["visibility"] == "VISIBLE"


def test_live_shell_serves_and_mounts_the_one_feedback_module():
    status, content_type, body = shared_ui.handle("/shared/front_feedback.mjs", {})
    assert status == 200
    assert content_type == "text/javascript; charset=utf-8"
    assert b"mountFrontFeedback" in body

    status, content_type, body = front_door.handle("/front", {}, "GET", b"")
    assert status == 200
    assert content_type == "text/html; charset=utf-8"
    assert b'data-feedback-actor="gerard"' in body
    carrier_source = (
        Path(front_door.__file__).resolve().parent / "static_shared" / "front_carrier.mjs"
    ).read_bytes()
    assert b'import { mountFrontFeedback } from "/shared/front_feedback.mjs"' in carrier_source
    assert b"bindFeedbackAnchors(els.carrier)" in carrier_source
