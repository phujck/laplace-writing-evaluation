from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.writing import stages as writing_stages
from laplace.manuscript import writing_style


def fixture(root):
    home = root / "independent/manuscript"
    home.mkdir(parents=True)
    (home / "draft.tex").write_text(r"\documentclass{book}\begin{document}First.\end{document}")
    (home / "manuscript_spec.json").write_text(json.dumps({"manuscript": {"genre": "book"}}))
    (root / "registry_projects.json").write_text(json.dumps({"projects": [{
        "name": "different-project", "project_dir": "independent", "tex_root": "independent/manuscript",
        "manifest": {"document": {"root": "independent/manuscript/draft.tex"}}}]}))
    profile = root / "profiles/voice/gerard-technical-v1.md"
    profile.parent.mkdir(parents=True)
    profile.write_text("# Another author\n\n## Current runtime prompt\nExplain through a measured example.\n")
    return home, profile


def test_catalogue_is_read_only_and_materialises_only_selected_stage(tmp_path, monkeypatch):
    fixture(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError("catalogue should not load voice bodies")
    monkeypatch.setattr(writing_style, "context", forbidden)
    before = set(tmp_path.rglob("*"))
    result = writing_stages.inspect("different-project", {}, tmp_path)
    assert len(result["stages"]) == 7
    assert all(row["open"]["operation"] == "writing_stage" for row in result["stages"])
    assert "materials" not in result and "guidance" not in result
    assert result["autonomous_execution"] is False
    repeated = writing_stages.inspect("different-project", result["reentry_action"]["payload"], tmp_path)
    assert repeated["unchanged"] is True and "stages" not in repeated
    assert set(tmp_path.rglob("*")) == before


@pytest.mark.parametrize("stage", [None, "voice_integration"])
@pytest.mark.parametrize("spelling", ["prefixed", "bare", "upper-hex"])
def test_stage_reentry_agrees_through_name_and_verb_doors(tmp_path, stage, spelling):
    from laplace.native import tools as writing_tools, verbs as writing_verbs
    fixture(tmp_path)
    project = "different-project"
    payload = {"stage": stage} if stage else {}
    current = writing_tools.execute(tmp_path, project, "work", "writing_stage", payload)
    digest = current["revision"].removeprefix("sha256:")
    known = {"prefixed": "sha256:" + digest, "bare": digest,
             "upper-hex": "sha256:" + digest.upper()}[spelling]
    payload = {**payload, "known_revision": known}
    named = writing_tools.execute(tmp_path, project, "work", "writing_stage", payload)
    _route, request = writing_verbs.from_owner_call("writing_stage", payload, project=project)
    through_verb = writing_tools.request(tmp_path, project, "work", request)
    assert through_verb["outcome"] == "read"
    assert through_verb["owner_response"] == named
    assert named["unchanged"] is True and named["delta"] == []
    assert not {"stages", "guidance", "materials"}.intersection(named)
    stale = writing_tools.execute(tmp_path, project, "work", "writing_stage",
                                  {**payload, "known_revision": "0" * 64})
    assert stale["unchanged"] is False


def test_voice_stage_uses_project_selection_and_does_not_replay_sources(tmp_path):
    _home, profile = fixture(tmp_path)
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    result = writing_stages.inspect("different-project", {"stage": "voice_integration"}, tmp_path)
    assert "measured example" in result["materials"]["voice"]["guidance"]
    assert result["materials"]["selected_source"]["root"] == "independent/manuscript/draft.tex"
    assert result["materials"]["selected_source_read"]["operation"] == "source"
    assert result["materials"]["voice"]["source_catalogue"]["payload"] == {"view": "provenance"}
    assert "apply_revision" in result["apply"]
    assert result["acceptance"] == "NOT_ASSESSED"
    assert result == writing_stages.inspect("different-project", {"stage": "voice_integration", "view": "full"}, tmp_path)
    assert not any("synthetics" in str(v).lower() for v in result.values())
    assert {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before
    repeated = writing_stages.inspect("different-project", result["reentry_action"]["payload"], tmp_path)
    assert repeated["unchanged"] is True and repeated["delta"] == []
    assert "guidance" not in repeated and "materials" not in repeated
    profile.write_text(profile.read_text() + "\nUse clear local contrasts.\n")
    changed = writing_stages.inspect("different-project", {
        "stage": "voice_integration", "known_revision": result["revision"]}, tmp_path)
    assert changed["unchanged"] is False
    assert changed["revision"] != result["revision"]


def test_project_guidance_changes_stage_revision_without_global_mutation(tmp_path):
    _home, profile = fixture(tmp_path)
    original = profile.read_bytes()
    prior = writing_stages.inspect("different-project", {"stage": "voice_integration"}, tmp_path)
    style = writing_style.state("different-project", tmp_path)
    writing_style.save("different-project", {"expected_revision": style["revision"],
                       "guidance": "Follow this project's experimental question."}, tmp_path)
    current = writing_stages.inspect("different-project", {
        "stage": "voice_integration", "known_revision": prior["revision"]}, tmp_path)
    assert current["unchanged"] is False
    assert "experimental question" in current["materials"]["voice"]["project_guidance"]
    assert profile.read_bytes() == original


@pytest.mark.parametrize("stage", ["build_acceptance", "engine_acceptance", "ui_acceptance", "provider_context"])
def test_acceptance_profile_is_callable_without_historical_measurement_claim(tmp_path, stage):
    fixture(tmp_path)
    result = writing_stages.inspect("different-project", {"stage": stage, "view": "materials"}, tmp_path)
    profile = result["materials"]["acceptance_profile"]
    assert profile["measure"]
    assert not any(k.startswith("reference_observations") for k in profile)
    assert result["acceptance"] == "NOT_ASSESSED"
    assert "voice" not in result["materials"]


def test_presentation_revision_follows_settings_not_other_profiles(tmp_path):
    home, _profile = fixture(tmp_path)
    before = writing_stages.inspect("different-project", {"stage": "presentation"}, tmp_path)
    (home / "document_style.json").write_text(json.dumps({"font_size": "12pt"}))
    after = writing_stages.inspect("different-project", {
        "stage": "presentation", "known_revision": before["revision"]}, tmp_path)
    assert after["unchanged"] is False
    assert after["materials"]["presentation"]["document_settings"]["values"]["font_size"] == "12pt"
    assert after["materials"]["presentation"]["document_settings"]["effective_origin"] == "legacy-read-only-fallback"


def test_invalid_requests_and_escaped_profile_are_refused(tmp_path):
    fixture(tmp_path)
    for payload in [{"stage": "fictional"}, {"stage": ["voice_integration"]},
                    {"view": "everything"}, {"history": True}]:
        with pytest.raises(ValueError):
            writing_stages.inspect("different-project", payload, tmp_path)
    with pytest.raises(ValueError, match="Unknown project"):
        writing_stages.inspect("not-registered", {}, tmp_path)
    (tmp_path / "profiles/writing").mkdir()
    (tmp_path / writing_stages.CATALOGUE).symlink_to(Path(__file__))
    with pytest.raises(ValueError, match="owned file"):
        writing_stages.inspect("different-project", {}, tmp_path)


def test_engine_cli_uses_the_same_stage_owner(tmp_path, capsys):
    fixture(tmp_path)
    assert writing_stages.main(["different-project", "--repo-root", str(tmp_path),
                                "--stage", "engine_acceptance"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result == writing_stages.inspect("different-project", {"stage": "engine_acceptance"}, tmp_path)
    assert writing_stages.main(["unregistered", "--repo-root", str(tmp_path)]) == 2
    assert "Unknown project" in capsys.readouterr().out


def test_programme_is_shared_ordered_data_not_new_maintenance_stage_enum(tmp_path):
    fixture(tmp_path)
    catalogue = writing_stages.inspect("different-project", {}, tmp_path)
    programme = writing_stages.programme(tmp_path)
    assert [p["id"] for p in catalogue["programme"]["phases"]] == [
        "results", "literature", "improvement", "draft", "judgement", "synthesis", "export"]
    assert catalogue["programme"]["revision"] == catalogue["revision"] == programme["revision"]
    assert len(catalogue["stages"]) == 7
    repeated = writing_stages.inspect("different-project", catalogue["reentry_action"]["payload"], tmp_path)
    assert repeated["unchanged"] and "programme" not in repeated
    assert programme["phases"][1]["work_kind"] != "literature-acquisition"
    assert "repeated human" in programme["phases"][3]["guidance"]
    assert programme["phases"][4]["review_obligations"][0]["independent"]


@pytest.mark.parametrize("mutation", ["duplicate", "cycle", "dangling", "missing"])
def test_invalid_programme_cannot_publish_misleading_route(tmp_path, mutation):
    fixture(tmp_path)
    data, ref = writing_stages._profile(tmp_path, writing_stages.CATALOGUE)
    phases = data["programme"]["phases"]
    if mutation == "duplicate":
        phases[1]["id"] = phases[0]["id"]
    elif mutation == "cycle":
        phases[0]["depends_on"] = [phases[-1]["id"]]
    elif mutation == "dangling":
        phases[1]["depends_on"] = ["missing"]
    else:
        del phases[0]["completion"]
    with pytest.raises(ValueError):
        writing_stages.programme(tmp_path, catalogue=data, reference=ref)


@pytest.mark.parametrize("kind", ["source-not-qualified", "unsupported", "own-evidence-stale",
                                  "engineering-support-not-current"])
def test_literature_projection_does_not_upgrade_missing_or_stale_support(kind):
    scope = {"revision": "fixture", "claims": [{"id": "claim"}],
             "pagination": {"offset": 0, "total": 1, "next_offset": None},
             "gaps": [{"kind": kind}], "ready_for_completion": False}
    seen = writing_stages.literature_observation(scope)
    assert not seen["support_usable"] and not seen["ready_for_completion"]
    assert seen["support_gaps"][0]["kind"] == kind


def test_qualified_support_precedes_citation_build_without_claiming_final_completion():
    scope = {"revision": "fixture", "claims": [{"id": "claim"}],
             "pagination": {"offset": 0, "total": 1, "next_offset": None},
             "gaps": [{"kind": "not-yet-cited"}, {"kind": "bibliography-build-not-current"}],
             "ready_for_completion": False}
    seen = writing_stages.literature_observation(scope)
    assert seen["support_usable"] and not seen["ready_for_completion"]
    assert not seen["support_gaps"] and len(seen["citation_build_gaps"]) == 2
    for changes in [{"pagination": {"offset": 1, "total": 2, "next_offset": None}},
                    {"pagination": {"offset": 0, "total": 2, "next_offset": 1}},
                    {"gaps_omitted": 1}, {"claims": []}]:
        assert not writing_stages.literature_observation({**scope, **changes})["support_usable"]
