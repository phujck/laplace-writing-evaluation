from __future__ import annotations

import json

from laplace.web import project_work_surface
from laplace.native import contracts as writing_contracts, tools as writing_tools
from laplace.writing import operating as writing_operating
from laplace.projects import library as writing_projects


def fixture(tmp_path):
    status,result=writing_projects.create({"name":"stage-contract-book","title":"Stage Contract Book",
        "kind":"book","purpose":"Explain the measured construction.","audience":"researchers"},tmp_path)
    assert status==201,result


def test_native_stage_catalogue_and_guidance_use_owner(tmp_path):
    fixture(tmp_path)
    catalogue=writing_tools.execute(tmp_path,"stage-contract-book","work","writing_stage",{})
    assert catalogue["schema_version"]=="laplace.writing-stage/1"
    assert any(row["id"]=="voice_integration" for row in catalogue["stages"])
    guidance=writing_tools.execute(tmp_path,"stage-contract-book","work","writing_stage",{
        "stage":"voice_integration","view":"guidance"})
    assert guidance["stage"]=="voice_integration" and guidance["autonomous_execution"] is False
    assert guidance["materials"]["voice"]["full_profile"]["operation"]=="writing_style"


def test_native_known_stage_revision_returns_no_repeated_body(tmp_path):
    fixture(tmp_path)
    first=writing_tools.execute(tmp_path,"stage-contract-book","work","writing_stage",{
        "stage":"voice_integration"})
    unchanged=writing_tools.execute(tmp_path,"stage-contract-book","work","writing_stage",{
        "stage":"voice_integration","known_revision":first["revision"]})
    assert unchanged["unchanged"] is True and unchanged["delta"]==[]
    assert "guidance" not in unchanged and "materials" not in unchanged


def test_stage_exact_help_exposes_only_frozen_inputs():
    contract=writing_contracts.exact_contract("writing_stage",permitted=True)
    assert set(contract["input"]["properties"])=={"stage","view","known_revision"}
    assert contract["input"]["properties"]["view"]["enum"]==["summary","guidance","materials","full"]


def test_stage_http_route_materialises_selected_view(tmp_path):
    fixture(tmp_path)
    code,_,raw=project_work_surface.handle("/work/writing-stage",{
        "project":["stage-contract-book"],"stage":["engine_acceptance"],"view":["summary"]},
        "GET",repo_root=tmp_path)
    result=json.loads(raw)
    assert code==200 and result["stage"]=="engine_acceptance" and "guidance" not in result


def test_pipeline_and_initial_brief_discover_stage_owner_without_materialising_bodies(tmp_path):
    fixture(tmp_path)
    pipeline=writing_tools.execute(tmp_path,"stage-contract-book","work","pipeline",{})
    assert pipeline["writing_stage"]["operation"]=="writing_stage"
    assert any(row["id"]=="provider_context" for row in pipeline["writing_stage"]["stages"])
    brief=writing_operating.build("stage-contract-book","work",tmp_path)
    assert "writing_stage" in brief["permissions"]
    assert isinstance(brief["capability_guidance"]["stages"],str)


def test_programme_bootstrap_action_executes_through_existing_native_and_http_work(tmp_path):
    fixture(tmp_path)
    project = "stage-contract-book"
    view = writing_tools.execute(tmp_path, project, "work", "pipeline", {})
    action = view["programme"]["create_action"]
    native = writing_tools.execute(tmp_path, project, "work", action["operation"], action["payload"])
    assert native["task_kind"] == "programme"
    assert native["logical_target"] == {"kind": "writing-programme"}
    assert len(native["manuscript_programme"]["required_stages"]) == 7
    assert len(native["review_obligations"]) == 7
    from laplace.writing import prepared_work
    http_action = prepared_work.programme_create_action(project, tmp_path)
    code, _, raw = project_work_surface.handle("/work/task", {}, "POST",
        json.dumps({"project": project, **http_action["payload"]}).encode(), tmp_path)
    assert code == 201
    assert json.loads(raw)["task_kind"] == native["task_kind"]
    assert len(json.loads(raw)["manuscript_programme"]["required_stages"]) == 7
    # Existing frozen maintenance enum remains unchanged. Programme phases are
    # response data and ordinary Work actions, not fictional writing_stage IDs.
    contract = writing_contracts.exact_contract("writing_stage", permitted=True)
    assert "literature" not in contract["input"]["properties"]["stage"]["enum"]
