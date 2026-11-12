from __future__ import annotations

import json

from laplace.research import visuals_surface
from laplace.manuscript import writing_pipeline
from laplace.projects import library as writing_projects
from laplace.research import research_runs
from laplace.research import research_records


def _book(tmp_path):
    status, result = writing_projects.create({
        "name": "pipeline-book", "title": "Pipeline Book", "kind": "book",
        "purpose": "Explain the measured construction.", "audience": "researchers"}, tmp_path)
    assert status == 201, result
    return tmp_path / "synthetics papers" / "pipeline-book" / "manuscript"


def _stage(state, name):
    return next(row for row in state["stages"] if row["id"] == name)


def test_pipeline_is_seven_derived_stages_and_reads_do_not_launch_producers(tmp_path):
    manuscript = _book(tmp_path)
    producer = manuscript / "research" / "producer.py"
    producer.parent.mkdir()
    producer.write_text("raise SystemExit('must not run on inspect')\n")
    status, result = research_runs.register_producer("pipeline-book", {
        "id": "declared", "executable": "research/producer.py", "scope": "manuscript",
        "modes": ["smoke"], "allowed_args": {}}, root=tmp_path)
    assert status == 201, result

    state = writing_pipeline.inspect("pipeline-book", tmp_path)

    assert [row["id"] for row in state["stages"]] == [
        "framing", "concepts", "research", "argument", "manuscript", "review", "presentation"]
    assert _stage(state, "research")["status"] == "DRAFT"
    assert not (manuscript / "research_runs").exists()
    assert state["schema_version"] == "laplace.writing-pipeline/1"


def test_pipeline_research_and_visual_readiness_follows_actual_outputs(tmp_path):
    manuscript = _book(tmp_path)
    source = manuscript / "research" / "source.py"
    source.parent.mkdir()
    source.write_text("VALUE = 1\n")
    status, result = research_records.record("pipeline-book", {
        "kind": "experiment", "id": "experiment:one", "source": "research/source.py"}, root=tmp_path)
    assert status == 201, result
    experiment_only = writing_pipeline.inspect("pipeline-book", tmp_path)
    assert _stage(experiment_only, "research")["status"] == "DRAFT"

    output = manuscript / "research" / "result.json"
    output.write_text('{"value": 1}\n')
    status, result = research_records.record("pipeline-book", {
        "kind": "result", "id": "result:one", "result": "research/result.json"}, root=tmp_path)
    assert status == 201, result
    with_result = writing_pipeline.inspect("pipeline-book", tmp_path)
    assert _stage(with_result, "research")["status"] == "AVAILABLE"

    project = tmp_path / "synthetics papers" / "pipeline-book"
    (project / "data.csv").write_text("x,y\n1,2\n2,3\n")
    spec = {"id": "pipeline-plot", "title": "Pipeline plot", "question": "Does y rise?",
            "kind": "plot", "caption": "Fixture output.", "source_data": "data.csv",
            "x": "x", "series": ["y"]}
    assert visuals_surface.handle("/visuals/create", {}, "POST", json.dumps({
        "project": "pipeline-book", "spec": spec}).encode(), repo_root=tmp_path)[0] == 201
    specified = writing_pipeline.inspect("pipeline-book", tmp_path)
    assert _stage(specified, "presentation")["status"] == "DRAFT"

    assert visuals_surface.handle("/visuals/render", {}, "POST", json.dumps({
        "project": "pipeline-book", "id": "pipeline-plot"}).encode(), repo_root=tmp_path)[0] == 200
    rendered = writing_pipeline.inspect("pipeline-book", tmp_path)
    assert _stage(rendered, "presentation")["status"] == "AVAILABLE"
    (project / "data.csv").write_text("x,y\n1,9\n")
    stale = writing_pipeline.inspect("pipeline-book", tmp_path)
    assert _stage(stale, "presentation")["status"] == "STALE"


def test_review_stage_folds_historic_contexts_to_unapplied_stale_proposals(tmp_path):
    from laplace.writing import records as writing_records
    from laplace.pipeline import authoring

    manuscript = _book(tmp_path)
    main = manuscript / "Pipeline-Book.tex"
    context = authoring.build_context(
        "pipeline-book", {"files": ["Pipeline-Book.tex"]}, repo_root=tmp_path)
    main.write_text(main.read_text() + "\nChanged after the conversation.\n")
    audit = authoring.inspect("pipeline-book", repo_root=tmp_path)["stale"]
    assert any(row["context_id"] == context["context_id"] for row in audit)

    discussion_only = writing_pipeline.inspect("pipeline-book", tmp_path)
    assert _stage(discussion_only, "review")["status"] == "OPEN"
    assert discussion_only["historical_stale_context_count"] >= 1

    session_id, turn_id = "WS-fixture", "WT-fixture"
    writing_records.bank(tmp_path, {"record": "writing-session", "id": session_id,
        "project": "pipeline-book", "provider": "codex", "model": "fixture"})
    writing_records.bank(tmp_path, {"record": "writing-turn", "id": turn_id,
        "session_id": session_id, "project": "pipeline-book", "mode": "revise",
        "context_id": context["context_id"]})
    writing_records.bank(tmp_path, {"record": "writing-reply", "id": "WR-fixture",
        "turn_id": turn_id, "session_id": session_id, "project": "pipeline-book",
        "status": "completed", "proposal": {"edits": [{"file": "Pipeline-Book.tex"}]}})
    outstanding = writing_pipeline.inspect("pipeline-book", tmp_path)
    assert _stage(outstanding, "review")["status"] == "STALE"
    assert len(outstanding["stale_contexts"]) == 1

    writing_records.bank(tmp_path, {"record": "writing-application", "id": "WA-fixture",
        "turn_id": turn_id, "project": "pipeline-book", "complete": True})
    accepted = writing_pipeline.inspect("pipeline-book", tmp_path)
    assert _stage(accepted, "review")["status"] == "OPEN"
    assert accepted["stale_contexts"] == []
    assert any(row["context_id"] == context["context_id"]
               for row in authoring.inspect("pipeline-book", repo_root=tmp_path)["stale"])


def test_pipeline_shared_programme_is_additive_honest_and_provider_free(tmp_path, monkeypatch):
    from laplace.writing import stages, provider
    from laplace.pipeline import authoring
    _book(tmp_path)
    monkeypatch.setattr(provider, "WritingTurn", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("pipeline must not launch a model")))
    monkeypatch.setattr(authoring, "inspect", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("summary must not replay historical context audit")))
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*.tex")}
    state = writing_pipeline.inspect("pipeline-book", tmp_path, include_history=False)
    programme = state["programme"]
    catalogue = stages.inspect("pipeline-book", {}, tmp_path)
    assert [p["id"] for p in programme["phases"]] == [
        p["id"] for p in catalogue["programme"]["phases"]]
    assert programme["revision"] == catalogue["programme"]["revision"]
    assert programme["create_action"]["operation"] == "task"
    assert programme["create_action"]["payload"]["kind"] == "programme"
    for row in programme["phases"]:
        assert row["observation"]["acceptance"] == "NOT_ASSESSED"
    assert programme["phases"][1]["observation"]["status"] == "NOT_OBSERVED"
    assert programme["phases"][-1]["observation"]["status"] == "NOT_OBSERVED"
    assert before == {str(p): p.read_bytes() for p in tmp_path.rglob("*.tex")}
    assert state["historical_stale_context_count"] is None
