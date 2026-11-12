"""load_spec: corrupt-vs-absent (P4) - a corrupt file warns, an absent one is silent."""

from __future__ import annotations

import logging
from types import SimpleNamespace

from laplace.pipeline import projection_spec


def test_load_spec_corrupt_file_warns_and_returns_none(tmp_path, monkeypatch, caplog):
    p = tmp_path / "manuscript_spec.json"
    p.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(projection_spec, "spec_path", lambda project, repo_root=None: p)

    with caplog.at_level(logging.WARNING):
        result = projection_spec.load_spec("whatever")

    assert result is None
    assert any(str(p) in r.getMessage() for r in caplog.records)


def test_load_spec_absent_file_returns_none_silently(tmp_path, monkeypatch, caplog):
    p = tmp_path / "manuscript_spec.json"
    assert not p.exists()
    monkeypatch.setattr(projection_spec, "spec_path", lambda project, repo_root=None: p)

    with caplog.at_level(logging.WARNING):
        result = projection_spec.load_spec("whatever")

    assert result is None
    assert caplog.records == []


def test_strict_nomenclature_requires_evidence_for_coinage(monkeypatch):
    spec = {
        "schema": "laplace-manuscript-spec/0.2",
        "manuscript": {
            "manuscript_id": "p",
            "working_title": "T",
            "purpose": "P",
            "primary_contribution": "C",
            "scope": ["S"],
            "non_claims": ["N"],
            "target_reader": "R",
            "genre": "technical journal paper",
            "notation": {"x": "input"},
            "nomenclature_policy": {"topic_field": "nonlinear optics"},
            "terminology": {
                "new name": {
                    "definition": "a new object",
                    "status": "coined-here",
                    "field": "nonlinear optics",
                    "alternatives": [],
                }
            },
        },
        "figures": {},
    }
    monkeypatch.setattr(
        projection_spec.registry,
        "resolve",
        lambda project, repo_root=None: SimpleNamespace(
            kind="tex", read_plan=lambda repo_root=None: {"sections": []}
        ),
    )
    monkeypatch.setattr(projection_spec, "load_spec", lambda project, repo_root=None: spec)

    result = projection_spec.validate_spec("p")

    assert not result["pass"]
    messages = {issue["issue"] for issue in result["issues"]}
    assert "coinage missing 'novel_concept'" in messages
    assert "coinage missing 'introduced_after'" in messages


def test_strict_nomenclature_accepts_field_terms_and_earned_coinage(monkeypatch):
    spec = {
        "schema": "laplace-manuscript-spec/0.2",
        "manuscript": {
            "manuscript_id": "p",
            "working_title": "T",
            "purpose": "P",
            "primary_contribution": "C",
            "scope": ["S"],
            "non_claims": ["N"],
            "target_reader": "R",
            "genre": "technical journal paper",
            "notation": {"x": "input"},
            "nomenclature_policy": {"topic_field": "nonlinear optics"},
            "terminology": {
                "integral controller": {
                    "definition": "a controller that integrates an error signal",
                    "status": "field-standard",
                    "field": "control theory",
                    "alternatives": [],
                },
                "twinning tree": {
                    "definition": "a hierarchy of twinning residuals",
                    "status": "coined-here",
                    "field": "nonlinear optics",
                    "alternatives": [],
                    "novel_concept": "hierarchical composition of material twinning residuals",
                    "introduced_after": "the shared-reference construction and product residual",
                },
            },
        },
        "figures": {},
    }
    monkeypatch.setattr(
        projection_spec.registry,
        "resolve",
        lambda project, repo_root=None: SimpleNamespace(
            kind="tex", read_plan=lambda repo_root=None: {"sections": []}
        ),
    )
    monkeypatch.setattr(projection_spec, "load_spec", lambda project, repo_root=None: spec)

    result = projection_spec.validate_spec("p")

    assert result["pass"], result["issues"]
