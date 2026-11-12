"""C application regressions for the human research revision loop: refused visual_create.

A refused visual_create reports every validator issue of the spec as it would be saved, the owner's own
required fields and example for its kind (visual_production.authoring_contract), and saves nothing.
"""
from __future__ import annotations

import json

from laplace.pipeline import visual_production as vp
from laplace.research import visuals_surface as vs

PLOT = {"id": "fig-c", "kind": "plot", "title": "T", "question": "Q?", "caption": "C",
        "source_data": "data.csv", "x": "x", "series": ["y"]}


def _refusal(spec, prior=()):
    return vs._create_refusal({"specs": list(prior)}, spec)


def test_missing_kind_reports_kinds_and_the_issue_without_a_kind_example():
    out = _refusal({"id": "fig-a", "title": "T", "question": "Q?", "caption": "C"})
    assert out["saved"] is False
    assert any(issue["field"] == "kind" for issue in out["issues"])
    assert out["kinds"] == list(vp.authoring_contract()["variants"])
    assert "required" not in out and "example" not in out
    assert out["note"].startswith("Nothing was saved. Correct every listed field")


def test_plot_missing_fields_reports_every_issue_with_owner_required_and_example():
    out = _refusal({"id": "fig-b", "kind": "plot", "title": "T", "question": "Q?", "caption": "C"})
    assert {"source_data", "x", "series"} <= {issue["field"] for issue in out["issues"]}
    contract = vp.authoring_contract()
    assert out["required"] == list(contract["variants"]["plot"]["required"])
    assert out["example"] == contract["examples"]["plot"]


def test_prior_row_is_merged_as_upsert_merges_it_and_read_fields_are_dropped():
    prior = {**PLOT, "spec_revision": "read-view echo"}
    out = _refusal({"id": "fig-c", "caption": ""}, prior=[prior])
    assert [issue["field"] for issue in out["issues"]] == ["caption"]


def test_owner_managed_change_has_no_field_issue_and_the_note_says_so():
    out = _refusal({**PLOT, "render": {"renderer": "matplotlib"}}, prior=[PLOT])
    assert out["issues"] == []
    assert "fields are valid" in out["note"]


def test_non_object_spec_refusal_is_still_typed():
    out = vs._create_refusal({"specs": []}, {})
    assert out["saved"] is False and {"id", "kind"} <= {issue["field"] for issue in out["issues"]}


def test_create_handler_refuses_with_all_issues_and_saves_nothing(tmp_path, monkeypatch):
    from laplace.manuscript import manuscript_source
    monkeypatch.setattr(vs, "_m", lambda project, repo_root=None: tmp_path)
    monkeypatch.setattr(manuscript_source, "resolve", lambda project, repo_root=None: {})
    spec = {"id": "fig-d", "kind": "plot", "title": "T", "question": "Q?", "caption": "C"}
    status, _content_type, encoded = vs._handle("/visuals/create", {"project": ["p"]}, "POST",
                                                json.dumps({"project": "p", "spec": spec}), repo_root=str(tmp_path))
    value = json.loads(encoded)
    assert status == 422 and value["saved"] is False and value["error"]
    assert {"source_data", "x", "series"} <= {issue["field"] for issue in value["issues"]}
    assert value["required"] == list(vp.authoring_contract()["variants"]["plot"]["required"])
    spec_file = tmp_path / "manuscript_spec.json"
    if spec_file.exists():
        rows = json.loads(spec_file.read_text()).get("figure_specs") or []
        assert all(row.get("id") != "fig-d" for row in rows)
