"""The independently found chapter, bibliography and legacy-dispatch joins."""

import json
from pathlib import Path

import pytest

from laplace.research import references_surface as references
from laplace.manuscript import storyboard
from laplace.writing import operations
from laplace.manuscript import source_effects
from test_literature_operations import project, call, crossref


def test_reference_import_and_update_share_actual_source_effect_and_read_handles(
    tmp_path, crossref
):
    manuscript = project(tmp_path)
    imported = call(
        tmp_path, "literature_import", {"doi": "10.1234/test", "citekey": "Fixture2024"}
    )
    assert (
        imported["source_effect"]["state"] == "COMMITTED" and imported["source_effect"]["complete"]
    )
    metadata, _calls = crossref
    metadata["title"] = ["Updated fixture title"]
    updated = call(tmp_path, "reference_update", {"key": imported["association"]["key"]})
    assert updated["source_effect"]["state"] == "COMMITTED" and updated["source_effect"]["complete"]
    assert "Updated fixture title" in (manuscript / "sources.bib").read_text()
    for value in (imported, updated):
        assert value["source_effect"]["files"][0]["path"].endswith("sources.bib")
        for handle in value["source_effect"]["impact"]["reads"]:
            call(tmp_path, handle["operation"], handle["payload"])


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_reference_attach_required_metadata_failure_retains_exact_bib_fate(
    tmp_path, crossref, monkeypatch, cleanup_fails
):
    manuscript = project(tmp_path)
    bib = manuscript / "sources.bib"
    before = bib.read_bytes()

    def fail(*args, **kwargs):
        raise OSError("controlled association publication failure")

    monkeypatch.setattr(references, "_write_associations", fail)
    if cleanup_fails:
        monkeypatch.setattr(source_effects, "replace", fail)
    with pytest.raises(operations.OwnerError) as error:
        call(tmp_path, "literature_import", {"doi": "10.1234/test", "citekey": "Fixture2024"})
    effect = error.value.details["source_effect"]
    assert effect["state"] == ("COMMITTED" if cleanup_fails else "ROLLED_BACK")
    assert not effect["complete"]
    assert (bib.read_bytes() != before) is cleanup_fails
    assert error.value.details["retryable"] is False


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_reference_update_required_association_swap_failure_keeps_common_effect(
    tmp_path, crossref, monkeypatch, cleanup_fails
):
    manuscript = project(tmp_path)
    imported = call(
        tmp_path, "literature_import", {"doi": "10.1234/test", "citekey": "Fixture2024"}
    )
    bib, assoc = manuscript / "sources.bib", manuscript / "references.json"
    before = bib.read_bytes()
    crossref[0]["title"] = ["New metadata title"]
    replace = Path.replace

    def fail_association(path, destination):
        if Path(destination) == assoc:
            raise OSError("controlled association swap failure")
        return replace(path, destination)

    monkeypatch.setattr(Path, "replace", fail_association)
    if cleanup_fails:

        def fail_cleanup(*args, **kwargs):
            raise OSError("controlled bibliography cleanup failure")

        monkeypatch.setattr(source_effects, "replace", fail_cleanup)
    with pytest.raises(operations.OwnerError) as error:
        call(tmp_path, "reference_update", {"key": imported["association"]["key"]})
    effect = error.value.details["source_effect"]
    assert effect["state"] == ("COMMITTED" if cleanup_fails else "ROLLED_BACK")
    assert not effect["complete"] and (bib.read_bytes() != before) is cleanup_fails
    assert error.value.details["retryable"] is False


def test_optional_literature_support_read_failure_keeps_acknowledged_binding(tmp_path, monkeypatch):
    from laplace.research import literature_support
    from test_literature_joined_workflow import project as joined_project, execute, bind

    manuscript, source, _key, _original = joined_project(tmp_path, monkeypatch)
    main = tmp_path / source["root"]
    main.write_text(main.read_text().replace(r"\bibliography{refs}", ""))
    source_file = tmp_path / "additional.txt"
    source_file.write_text("The first controlled claim holds only under the stated conditions.\n")
    imported = execute(
        tmp_path,
        "literature_import",
        {
            "metadata": {
                "title": "Additional fixture source",
                "creators": ["Fixture"],
                "year": "2026",
            },
            "provenance": {"description": "Explicit local fixture", "path": str(source_file)},
            "citekey": "Additional",
        },
    )

    def fail(*args, **kwargs):
        raise OSError("controlled optional support read failure")

    monkeypatch.setattr(literature_support, "for_node", fail)
    result = bind(tmp_path, imported["association"]["key"])
    assert result["ok"] and result["association"]["binding_state"] == "BOUND"
    assert result["source_effect"]["state"] == "COMMITTED" and result["source_effect"]["complete"]
    assert result["support"]["status"] == "UNAVAILABLE"
    assert result["source_effect"]["follow_through"]["maintenance_warnings"]
    assert "Additional" in (manuscript / "refs.bib").read_text()


def legacy_fixture(root, monkeypatch, *, canonical):
    manuscript = project(root)
    registry = root / "registry_projects.json"
    data = json.loads(registry.read_text())
    data["projects"][0]["manifest"] = {"document": {"root": "main.tex"}}
    registry.write_text(json.dumps(data))
    target = manuscript / "main.tex" if canonical else root / "derived/main.tex"
    target.parent.mkdir(exist_ok=True)
    if not canonical:
        target.write_text("\\input{b}\n\\input{a}\n")
    plan = {
        "meta": {"target_dir": target.parent.relative_to(root).as_posix()},
        "sections": [{"id": "a"}, {"id": "b"}],
        "appendices": [],
    }
    plan_path = manuscript / "projection_plan.json"
    plan_path.write_text(json.dumps(plan))
    monkeypatch.setattr(storyboard, "_repo_root", lambda: root)
    monkeypatch.setattr(storyboard, "_load_plan", lambda corpus: (plan_path, plan))
    monkeypatch.setattr(storyboard, "dirty_report", lambda corpus: [])
    return manuscript, target, plan


def test_legacy_cheap_rebuild_refuses_canonical_root_and_keeps_prior_plan(tmp_path, monkeypatch):
    manuscript, target, plan = legacy_fixture(tmp_path, monkeypatch, canonical=True)
    before, plan_before = target.read_bytes(), (manuscript / "projection_plan.json").read_bytes()
    monkeypatch.setattr(
        storyboard, "_try_compile", lambda *a, **k: pytest.fail("refused source compiled")
    )
    result = storyboard.rebuild("fixture", "cheap")
    assert not result["ok"] and result["reason"] == "canonical-source-rebuild-refused"
    assert (
        target.read_bytes() == before
        and (manuscript / "projection_plan.json").read_bytes() == plan_before
    )
    assert "source_effect" not in result and "retained" in result["error"]


def test_legacy_cheap_rebuild_preserves_declared_derived_rendering(tmp_path, monkeypatch):
    _manuscript, target, _plan = legacy_fixture(tmp_path, monkeypatch, canonical=False)
    monkeypatch.setattr(
        storyboard, "_try_compile", lambda *a, **k: {"ok": True, "fixture": "compiler not invoked"}
    )
    result = storyboard.rebuild("fixture", "cheap")
    assert result["ok"] and result["reordered"]
    assert target.read_text() == "\\input{a}\n\\input{b}\n"


def test_legacy_bibliography_source_write_is_refused_before_stage(tmp_path, monkeypatch):
    from laplace.pipeline import bibliography_stage

    _manuscript, target, _plan = legacy_fixture(tmp_path, monkeypatch, canonical=True)
    before = target.read_bytes()
    monkeypatch.setattr(
        bibliography_stage,
        "run",
        lambda *a, **k: pytest.fail("canonical source reached legacy stage"),
    )
    status, result = storyboard.run_launch("fixture", "bibliography-run", "fixture", armed=True)
    assert status == 409 and result["reason"] == "canonical-source-rebuild-refused"
    assert target.read_bytes() == before


def test_legacy_rebuild_cannot_overwrite_selected_include(tmp_path, monkeypatch):
    manuscript, target, _plan = legacy_fixture(tmp_path, monkeypatch, canonical=False)
    main = manuscript / "main.tex"
    main.write_text(
        main.read_text().replace(r"\end{document}", "\\input{../../derived/main}\n\\end{document}")
    )
    before = target.read_bytes()
    monkeypatch.setattr(
        storyboard, "_try_compile", lambda *a, **k: pytest.fail("selected include compiled")
    )
    result = storyboard.rebuild("fixture", "cheap")
    assert result["reason"] == "canonical-source-rebuild-refused"
    assert target.read_bytes() == before


def test_legacy_bibliography_preserves_proven_derived_target(tmp_path, monkeypatch):
    from laplace.pipeline import bibliography_stage

    manuscript = project(tmp_path)
    authored = manuscript / "authored.tex"
    (manuscript / "main.tex").replace(authored)
    derived = manuscript / "main.tex"
    derived.write_text(
        "\\documentclass{article}\n\\begin{document}\nDerived output.\n\\end{document}\n"
    )
    registry = tmp_path / "registry_projects.json"
    data = json.loads(registry.read_text())
    data["projects"][0]["manifest"] = {"document": {"root": "authored.tex"}}
    registry.write_text(json.dumps(data))
    plan = {"meta": {"target_dir": manuscript.relative_to(tmp_path).as_posix()}, "sections": []}
    monkeypatch.setattr(storyboard, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        storyboard, "_load_plan", lambda corpus: (manuscript / "projection_plan.json", plan)
    )
    original = bibliography_stage.run
    monkeypatch.setattr(
        bibliography_stage, "run", lambda path, **kwargs: original(path, **kwargs, probe=False)
    )
    before = authored.read_bytes()
    status, result = storyboard.run_launch("fixture", "bibliography-run", "fixture", armed=True)
    assert status == 200 and result["wired"]
    assert r"\bibliography{refs}" in derived.read_text() and authored.read_bytes() == before
    assert (manuscript / "bibliography_manifest.json").exists()
