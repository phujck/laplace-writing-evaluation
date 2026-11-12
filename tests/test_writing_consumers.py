"""End-to-end consumer regressions for the connected writing workspace.

These tests deliberately use only temporary repositories and planted local
adapters.  They exercise whether a producer's durable output is found and
honestly interpreted by its downstream consumer.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from laplace.manuscript import document_style
from laplace.work import project_work
from laplace.research import references_surface
from laplace.web import research_surface
from laplace.research import research_runs
from laplace.research import research_catalogue
from laplace.research import research_records
from laplace.research import research_context   # the owner the code path reads (research family R1)
from test_project_work import guarded_transition


def test_workspace_module_imports_are_served_recursively():
    import re
    from laplace.web import shared_ui
    pending=['/shared/workspace.mjs'];seen=set()
    while pending:
        path=pending.pop()
        if path in seen:continue
        seen.add(path)
        response=shared_ui.handle(path,{})
        assert response and response[0]==200,path
        assert 'javascript' in response[1],path
        source=response[2].decode()
        pending.extend(re.findall(r"(?:from\s*|import\s*)['\"](/shared/[^'\"]+\.mjs)['\"]",source))
    assert '/shared/concept-explorer.mjs' in seen
    assert '/shared/research-card.mjs' in seen
from laplace.projects import library as writing_projects
from laplace.native import tools as writing_tools
from laplace.writing import reads
from laplace.pipeline import authoring, formal_verification, visual_production


def _import(root: Path, name: str = "fixture", *, editable: bool = True,
            body: str = "Text with a citation \\cite{source_one}.") -> tuple[Path, dict]:
    (root / "contract").mkdir(parents=True, exist_ok=True)
    source = root / "sources" / name
    source.mkdir(parents=True)
    (source / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\n" + body + "\n\\end{document}\n",
        encoding="utf-8")
    status, result = writing_projects.import_source({
        "name": name, "title": name.title(), "root": f"sources/{name}/main.tex",
        "editable": editable}, root)
    assert status == 201, result
    from laplace.manuscript import manuscript_source
    return source, manuscript_source.resolve(name, repo_root=root)


def _plain_project(root: Path, name: str = "plain") -> Path:
    manuscript = root / "synthetics papers" / name / "manuscript"
    manuscript.mkdir(parents=True)
    (manuscript / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}text\\end{document}\n", encoding="utf-8")
    (root / "registry_projects.json").write_text(json.dumps({"projects": [{
        "name": name, "kind": "conceptric",
        "tex_root": f"synthetics papers/{name}/manuscript"
    }]}), encoding="utf-8")
    return manuscript


def test_research_producer_handler_passes_explicit_repo_root(tmp_path):
    manuscript = _plain_project(tmp_path)
    (manuscript / "produce.py").write_text("print('fixture')\n", encoding="utf-8")
    payload = {"project": "plain", "producer": {"id": "p", "executable": "produce.py",
               "scope": "manuscript", "modes": ["smoke"], "allowed_args": {}}}

    status, _, raw = research_surface.handle(
        "/research/producer", {}, "POST", json.dumps(payload).encode(), repo_root=tmp_path)

    assert status == 201, json.loads(raw)
    assert (manuscript / "research_producers.json").is_file()


def test_research_cancel_and_artifact_handlers_pass_explicit_repo_root(tmp_path):
    manuscript = _plain_project(tmp_path)
    runs = manuscript / "research_runs"
    runs.mkdir()
    (runs / "run-1.json").write_text(json.dumps({"id": "run-1", "state": "RUNNING"}), encoding="utf-8")
    artifact = manuscript / "result.json"
    artifact.write_text('{"value": 1}\n', encoding="utf-8")

    cancel_status, _, _ = research_surface.handle(
        "/research/cancel", {}, "POST", b'{"project":"plain","id":"run-1"}', repo_root=tmp_path)
    artifact_status, _, body = research_surface.handle(
        "/research/artifact", {"project": ["plain"], "path": ["result.json"]}, "GET", b"",
        repo_root=tmp_path)

    assert cancel_status == 202
    assert (runs / "run-1.cancel").read_text(encoding="utf-8") == "cancelled"
    assert artifact_status == 200 and b'"value": 1' in body


def test_project_scope_producer_requires_a_declared_project_directory(tmp_path, monkeypatch):
    manuscript = _plain_project(tmp_path)
    (tmp_path / "unrelated.py").write_text("print('outside project')\n", encoding="utf-8")

    class _LegacyProject:
        project_dir = ""

    monkeypatch.setattr(research_context, "project",
                        lambda project, root: (_LegacyProject(), manuscript))
    monkeypatch.setattr("laplace.manuscript.manuscript_source.resolve",
                        lambda project, repo_root=None: {"read_only": False})

    status, result = research_runs.register_producer("plain", {
        "id": "outside", "executable": "unrelated.py", "scope": "project",
        "modes": ["smoke"], "allowed_args": {}}, root=tmp_path)

    assert status == 422
    assert "project" in result["error"].lower() or "scope" in result["error"].lower()
    assert not (manuscript / "research_producers.json").exists()


def test_provider_tool_exposes_research_producer_registration(tmp_path):
    manuscript, _ = _import(tmp_path)
    project_root = tmp_path / "writing_projects" / "fixture"
    (project_root / "research").mkdir(parents=True)
    (project_root / "research" / "produce.py").write_text("print('fixture')\n", encoding="utf-8")

    assert "research_producer" in reads.WRITES
    result = writing_tools.execute(tmp_path, "fixture", "work", "research_producer", {
        "id": "p", "executable": "research/produce.py", "scope": "project",
        "modes": ["smoke"], "allowed_args": {}})

    assert result["producer"]["id"] == "p"
    assert (manuscript / "research_producers.json").is_file()


def test_native_experiment_launch_is_compact_and_exactly_attributed(tmp_path):
    manuscript,_=_import(tmp_path)
    project_root=tmp_path/"writing_projects"/"fixture";(project_root/"research").mkdir(parents=True)
    script=project_root/"research"/"produce.py"
    script.write_text("import argparse,json\np=argparse.ArgumentParser();p.add_argument('--mode');p.add_argument('--args-json');p.add_argument('--result');a=p.parse_args();open(a.result,'w').write(json.dumps({'ok':True}))\n")
    from laplace.writing import records as writing_records
    writing_records.bank(tmp_path,{"record":"writing-session","id":"WS-run",
        "project":"fixture","provider":"codex","model":"m","effort":"low"})
    writing_records.bank(tmp_path,{"record":"writing-turn","id":"WT-run",
        "session_id":"WS-run","project":"fixture"})
    writing_tools.execute(tmp_path,"fixture","work","research_producer",{
        "id":"p","executable":"research/produce.py","scope":"project",
        "modes":["smoke"],"allowed_args":{},"dependencies":["research/produce.py"]},turn_id="WT-run")
    launched=writing_tools.execute(tmp_path,"fixture","work","experiment_run",{
        "producer_id":"p","mode":"smoke","args":{}},turn_id="WT-run")
    assert launched["full_response_omitted"] is True
    assert launched["run"]["id"] and launched["next_read"]=={
        "operation":"run_status","payload":{"id":launched["run"]["id"]}}
    assert launched["action_receipt"]["mutation_attribution"]["exact"] is True


def test_research_state_reports_imported_source_read_only(tmp_path):
    _import(tmp_path, editable=False)

    state = research_catalogue.state_payload("fixture", root=tmp_path)

    assert state["read_only"] is True


def test_complete_run_with_missing_result_is_not_current(tmp_path):
    manuscript = _plain_project(tmp_path)
    runs = manuscript / "research_runs"
    runs.mkdir()
    job = {"id": "run-missing", "state": "RUNNING",
           "result_absolute": str(runs / "missing.result.json")}
    (runs / "run-missing.json").write_text(json.dumps(job), encoding="utf-8")
    (runs / "run-missing.receipt.json").write_text(json.dumps({
        "state": "COMPLETE", "exit_code": 0, "result_sha256": "deadbeef"}), encoding="utf-8")

    status = research_runs._run_status(manuscript, "run-missing")

    assert status["state"] in {"STALE", "FAILED"}
    assert "result" in status["reason"].lower()


def test_experiment_declaration_without_result_is_not_complete(tmp_path):
    manuscript = _plain_project(tmp_path)
    (manuscript / "source.py").write_text("VALUE = 1\n", encoding="utf-8")
    status, result = research_records.record(
        "plain", {"kind": "experiment", "id": "experiment:declared", "source": "source.py"},
        root=tmp_path)
    assert status == 201, result

    state = research_catalogue.state_payload("plain", root=tmp_path)

    assert state["currentness"]["status"] == "CURRENT"
    assert state["state"] != "COMPLETE"


def test_result_bound_to_missing_run_is_refused_before_a_false_record_is_saved(tmp_path):
    manuscript = _plain_project(tmp_path)
    (manuscript / "result.json").write_text('{"value": 1}\n', encoding="utf-8")
    status, result = research_records.record(
        "plain", {"kind": "result", "id": "result:orphan", "result": "result.json",
                  "run_id": "run-does-not-exist"}, root=tmp_path)
    assert status == 422 and "run_status" in result["error"]

    state = research_catalogue.state_payload("plain", root=tmp_path)

    assert state["state"] != "COMPLETE"
    assert state["results"] == []


def test_figure_binding_requires_existing_result_and_figure(tmp_path):
    _plain_project(tmp_path)

    status, result = research_records.record("plain", {
        "kind": "figure_binding", "id": "binding:orphan",
        "result_id": "result:missing", "figure_id": "figure:missing"}, root=tmp_path)

    assert status == 422
    assert "result" in result["error"].lower() or "figure" in result["error"].lower()


class _Library:
    def item(self, key):
        return "fixture", {"key": key, "version": "2", "modified": "later"}


def test_reference_refresh_refuses_to_mutate_read_only_source(tmp_path):
    manuscript, _ = _import(tmp_path, editable=False)
    associations = manuscript / "references.json"
    original = json.dumps({"associations": [{"key": "ABCDEFGH", "state": "CURRENT",
        "source": {"revision": {"version": "1", "modified": "before"}}}]}, indent=2) + "\n"
    associations.write_text(original, encoding="utf-8")

    status, result = references_surface.refresh("fixture", root=tmp_path, library=_Library())
    update_status, update_result = references_surface.update(
        "fixture", {"key": "ABCDEFGH"}, root=tmp_path, library=_Library())

    assert status == 403
    assert "read-only" in result["error"]
    assert update_status == 403
    assert "read-only" in update_result["error"]
    assert associations.read_text(encoding="utf-8") == original


def test_reference_notes_are_consumed_by_selected_authoring_context(tmp_path):
    manuscript, _ = _import(tmp_path, editable=True)
    (manuscript / "references.json").write_text(json.dumps({"associations": [{
        "key": "ABCDEFGH", "citekey": "source_one", "claim_id": "claim:one",
        "note": "Use only for the finite-size caveat.", "state": "CURRENT",
        "source": {"identity": "sha256:item", "revision": {"version": "1", "modified": "now"}}
    }]}), encoding="utf-8")

    context = authoring.build_context(
        "fixture", {"files": ["main.tex"], "line_start": 3, "line_end": 3}, repo_root=tmp_path)

    assert "source_one" in context["prompt"]
    assert "finite-size caveat" in context["prompt"]
    assert context["consumed"]["references"][0]["key"] == "ABCDEFGH"


def test_direct_edit_feedback_stays_history_without_becoming_unresolved_context(tmp_path):
    manuscript, _ = _import(tmp_path, editable=True, body="Author wording.")
    ledger = manuscript / "feedback" / "feedback.jsonl"
    ledger.parent.mkdir()
    ledger.write_text(json.dumps({
        "id": "FB-author-edit", "record": "author-rewrite", "by": "author", "status": "open",
        "file": "main.tex", "comment": "Preserve this local qualification.",
        "before": "Old wording.", "after": "Author wording.",
        "anchor": {"file": "main.tex", "line_start": 3, "line_end": 3,
                   "before": "Old wording.", "after": "Author wording."}
    }) + "\n", encoding="utf-8")

    context = authoring.build_context(
        "fixture", {"files": ["main.tex"], "line_start": 3, "line_end": 3}, repo_root=tmp_path)
    history = authoring.history("fixture", {"id": "FB-author-edit"}, repo_root=tmp_path)

    assert "FB-author-edit" not in context["consumed"]["corrections"]
    assert "Preserve this local qualification" not in context["prompt"]
    assert history["item"]["applied"] is True
    assert history["item"]["text"] == "Preserve this local qualification."
    assert "AUTHOR'S EDIT: Author wording." not in context["prompt"]
    assert "Old wording." not in context["prompt"]


def test_read_only_source_feedback_status_is_not_mutated(tmp_path):
    manuscript, _ = _import(tmp_path, editable=False, body="Author wording.")
    ledger = manuscript / "feedback" / "feedback.jsonl"
    ledger.parent.mkdir()
    ledger.write_text(json.dumps({
        "id": "FB-external", "kind": "note", "by": "author", "status": "open",
        "node_id": "main.tex", "comment": "External source comment.",
        "anchor": {"file": "main.tex"}}) + "\n", encoding="utf-8")
    before = ledger.read_bytes()
    state = authoring.load("fixture", repo_root=tmp_path)

    with pytest.raises(ValueError, match="linked feedback correction is unavailable"):
        authoring.correction_status("fixture", {
            "id": "FB-external", "status": "resolved", "base_revision": state["revision"]},
            repo_root=tmp_path)

    assert ledger.read_bytes() == before


def test_concept_glossary_change_stales_an_existing_context(tmp_path, monkeypatch):
    _import(tmp_path, editable=True, body="The active concept matters.")
    glossary = [{"id": "def:active", "term": "Active concept", "aliases": []}]
    monkeypatch.setattr(authoring, "_glossary", lambda project, root: [dict(row) for row in glossary])
    context = authoring.build_context(
        "fixture", {"files": ["main.tex"], "line_start": 3, "line_end": 3}, repo_root=tmp_path)
    glossary[0]["term"] = "Renamed concept"

    inspected = authoring.inspect(
        "fixture", {"files": ["main.tex"], "line_start": 3, "line_end": 3}, repo_root=tmp_path)
    stale = next(row for row in inspected["stale"] if row["context_id"] == context["context_id"])

    assert "concept-glossary-changed" in stale["reasons"]


def test_model_formal_artifacts_land_where_formal_verifier_reads(tmp_path):
    _manuscript, source = _import(tmp_path, editable=False)
    state = tmp_path / source["storage_dir"]
    formal = state / "formal"
    formal.mkdir(parents=True)
    (formal / "Proof.lean").write_text("theorem answer : True := by trivial\n", encoding="utf-8")
    (formal / "lean-toolchain").write_text("leanprover/lean4:v4.34.1\n", encoding="utf-8")
    (formal / "lake-manifest.json").write_text("{}\n", encoding="utf-8")
    (formal / "results.json").write_text(json.dumps({"results": [{"id": "r1", "revision": "v1"}]}),
                                         encoding="utf-8")
    (formal / "manifest.json").write_text(json.dumps({
        "lean_toolchain": "formal/lean-toolchain", "lake_manifest": "formal/lake-manifest.json",
        "results": "formal/results.json"}), encoding="utf-8")

    posture = formal_verification.state("fixture", repo_root=tmp_path)

    assert posture["proof_status"] != "UNCONFIGURED", posture


def test_formal_check_does_not_bank_receipt_in_read_only_source(tmp_path, monkeypatch):
    manuscript, _ = _import(tmp_path, editable=False)
    formal = manuscript / "formal"
    formal.mkdir()
    (formal / "Proof.lean").write_text("theorem answer : True := by trivial\n", encoding="utf-8")
    (formal / "lean-toolchain").write_text("leanprover/lean4:v4.34.1\n", encoding="utf-8")
    (formal / "lake-manifest.json").write_text("{}\n", encoding="utf-8")
    (formal / "results.json").write_text(json.dumps({"results": [{"id": "r1", "revision": "v1"}]}),
                                         encoding="utf-8")
    (formal / "manifest.json").write_text(json.dumps({
        "lean_toolchain": "formal/lean-toolchain", "lake_manifest": "formal/lake-manifest.json",
        "results": "formal/results.json"}), encoding="utf-8")
    monkeypatch.setattr(formal_verification, "_tool_state", lambda root=None, lean_version=None: {
        "available": False, "command": None, "source": None, "reason": "fixture"})

    result = formal_verification.check(
        "fixture", file="formal/Proof.lean", declaration="answer", result_id="r1",
        result_revision="v1", repo_root=tmp_path)

    assert result["proof_status"] == "UNAVAILABLE"
    assert "read-only" in result["reason"]
    assert not (formal / "check_receipts.json").exists()


def test_formal_result_content_change_stales_receipt_even_when_revision_label_is_reused(tmp_path, monkeypatch):
    manuscript = _plain_project(tmp_path, "proof")
    formal = manuscript / "formal"
    formal.mkdir()
    proof = formal / "Proof.lean"
    proof.write_text("theorem answer : True := by trivial\n", encoding="utf-8")
    (formal / "lean-toolchain").write_text("leanprover/lean4:v4.34.1\n", encoding="utf-8")
    (formal / "lake-manifest.json").write_text("{}\n", encoding="utf-8")
    results = formal / "results.json"
    results.write_text(json.dumps({"results": [{"id": "r1", "revision": "v1", "value": 1}]}),
                       encoding="utf-8")
    manifest = {"lean_toolchain": "formal/lean-toolchain",
                "lake_manifest": "formal/lake-manifest.json", "results": "formal/results.json"}
    (formal / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    pin = formal_verification._pin(manuscript, manifest)
    bound = formal_verification._result(manuscript, manifest, "r1", "v1")
    formal_verification._write_receipt(manuscript, {
        "proof_status": "CHECKED", "file": "formal/Proof.lean",
        "file_digest": formal_verification._sha(proof), "declaration": "answer",
        "result": bound, "pin": pin, "dependencies": {}, "tool_version_number": "4.34.1"})
    monkeypatch.setattr(formal_verification, "_tool_state", lambda root=None, lean_version=None: {
        "available": True, "command": "/fixture/lake", "source": "fixture", "reason": None})
    monkeypatch.setattr(formal_verification, "_tool_version", lambda command, root: {
        "version": "4.34.1", "output": "Lean (version 4.34.1, fixture)"})
    assert formal_verification.state("proof", repo_root=tmp_path)["proof_status"] == "CHECKED"

    results.write_text(json.dumps({"results": [{"id": "r1", "revision": "v1", "value": 2}]}),
                       encoding="utf-8")
    state = formal_verification.state("proof", repo_root=tmp_path)

    assert state["proof_status"] == "STALE"
    assert state["receipts"][0]["stale"] is True


def _no_private_compiler(monkeypatch):
    def refused(*args, **kwargs):
        raise AssertionError("the retired style door must not start a compiler")
    monkeypatch.setattr(document_style.subprocess, "Popen", refused)


def _tree(root: Path) -> dict:
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*")) if path.is_file()}


@pytest.mark.parametrize("editable", [False, True])
def test_document_style_refuses_read_only_source_before_writing(tmp_path, monkeypatch, editable):
    # The legacy preview door is retired for every source: it refuses before any settings,
    # preview or compiler write, and names the exact read that replaces it.
    from laplace.manuscript.document_templates import TemplateRefused
    manuscript, _ = _import(tmp_path, editable=editable)
    _no_private_compiler(monkeypatch)
    before = _tree(tmp_path)
    with pytest.raises(TemplateRefused, match="Preview no longer saves settings or starts a private compiler") as refused:
        document_style.preview("fixture", {"profile": "article"}, root=tmp_path, wait=True)
    assert refused.value.details["code"] == "TEMPLATE_INSPECTION_REQUIRED" and refused.value.details["next_reads"]
    assert _tree(tmp_path) == before
    assert not (manuscript / "document_style.json").exists()
    assert not (manuscript / "style_preview").exists()


def test_document_style_ui_values_reach_tex_preview(tmp_path, monkeypatch):
    # Style values reach TeX only through the guarded template candidate -> exact build -> reviewed
    # proof -> Apply flow (positive cases: tests/test_document_templates.py,
    # tests/test_legC_template_gate.py). The old dual save and private compile write nothing.
    from laplace.manuscript.document_templates import TemplateRefused
    manuscript, _ = _import(tmp_path, editable=True)
    _no_private_compiler(monkeypatch)
    before = _tree(tmp_path)
    values = {"profile": "article", "font_size": "11pt", "margins": "25mm", "line_spacing": "1.15", "columns": "2"}
    with pytest.raises(TemplateRefused, match="Prepare an exact template candidate"):
        document_style.preview("fixture", values, root=tmp_path, wait=True)
    with pytest.raises(TemplateRefused, match="Use the guarded template candidate source flow"):
        document_style.save("fixture", values, root=tmp_path)
    assert _tree(tmp_path) == before
    assert document_style.status("fixture", root=tmp_path)["status"] == "RETIRED"


def test_saved_visual_overrides_reach_visual_renderer(tmp_path):
    # Figure defaults are read from the canonical defaults owner (manuscript.presentation in
    # manuscript_spec.json); a per-spec style still wins and an unknown key is refused.
    from laplace.manuscript.document_templates import TemplateRefused
    _, source = _import(tmp_path, editable=True)
    manuscript = tmp_path / source["manuscript_dir"]
    with pytest.raises(TemplateRefused):
        document_style.save("fixture", {"visual_overrides": {"font_size": 17}}, root=tmp_path)
    assert not (manuscript / "document_style.json").exists()
    spec_path = manuscript / "manuscript_spec.json"
    spec = json.loads(spec_path.read_text()) if spec_path.is_file() else {}
    spec.setdefault("manuscript", {})["presentation"] = {"visuals": {"font_size": 17}}
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    (manuscript / "document_style.json").write_text(json.dumps({"visuals": {"font_size": 5}}), encoding="utf-8")

    style = visual_production.house_style(manuscript, {}, tmp_path)

    assert style["font_size"] == 17
    consumed = style["document_defaults_input"]
    assert consumed["effective_origin"] == "canonical-spec"
    assert consumed["consumed_source"]["field"] == "manuscript.presentation"
    assert consumed["consumed_source"]["path"] == spec_path.relative_to(tmp_path).as_posix()
    assert visual_production.house_style(manuscript, {"style": {"font_size": 9}}, tmp_path)["font_size"] == 9
    with pytest.raises(ValueError, match="Unsupported figure style override: typeface"):
        visual_production.house_style(manuscript, {"style": {"typeface": "serif"}}, tmp_path)


def test_project_style_ui_consumes_async_preview_status():
    from workspace_source import workspace_source
    workspace = workspace_source()   # the shell and its domain controllers (M5 S2 F1)
    assert "mountOutput" in workspace and "workspace-output.mjs" in workspace
    module = Path("src/laplace/web/static_shared/workspace-output.mjs").read_text(encoding="utf-8")

    # The retired style preview/export doors have no caller; Output opens Document setup instead.
    assert "/work/style/preview" not in module and "/work/style/export" not in module
    assert "button('Open document setup',onDocumentSetup)" in module
    # The asynchronous status the Output consumes is the owner build job.
    assert "request('/authoring/build',{project})" in module and "if(receipt?.build_job)await buildControls.follow(receipt)" in module
    assert "build.running?'Building…'" in module and "current.status==='READY'?'Read PDF'" in module
    template = Path("src/laplace/web/static_shared/document-template.mjs").read_text(encoding="utf-8")
    assert "url.pathname!=='/work/style'" in template and "url.pathname!=='/work/style/pdf'" in template


def test_research_renewal_is_discoverable_to_tool_and_evidence_ui():
    evidence = Path("src/laplace/web/static_shared/writing-evidence.mjs").read_text(encoding="utf-8")
    card = Path("src/laplace/web/static_shared/research-card.mjs").read_text(encoding="utf-8")
    from workspace_source import workspace_source
    workspace = workspace_source()   # the shell and its domain controllers (M5 S2 F1)

    from laplace.native import declarations as writing_declarations
    assert "Exact help" in writing_tools.DESCRIPTION
    detail = writing_declarations.help_payload('research_reconcile',permitted=True,with_tokens=False)
    assert detail['input']['properties']['records']['items']['required']==['id','expected_revision']
    assert "Record uncovered provenance" in evidence and "expected_revision:r.revision" in evidence
    assert "/research/reconcile" in evidence
    assert "Rerun calculation" in evidence and "r.run.args||{}" in evidence
    assert "targetReceipts" in evidence and "row=>!row.superseded" in evidence
    assert "receipt.stale?'STALE':receipt.proof_status" in evidence
    assert "Check current target again" in evidence
    assert "concept_revision:target.revision" in evidence and "source_revision:target.source_revision" in evidence
    assert "Superseded proof checks" in evidence
    assert "Where this result is used" in card
    assert "Measured values" in card and "not stated" in card
    assert "Inspect evidence trail" in card and "Recorded and current file identities" in card
    assert "prior recorded" in card and "current_dependencies" in card
    assert "scientific truth" in card
    assert "JSON.stringify(record" not in card
    assert "view==='numerics'?new Set(['figures','numerics'])" in evidence
    assert "Back to formal targets" in evidence and "scientificText" in evidence
    assert "Filter formal targets by statement, origin or status" in evidence
    assert "formalAssumptionPosture" in evidence
    assert "Successful elaboration establishes only this Lean declaration" in evidence
    assert "Inspect Lean declaration" in evidence
    assert "visualsByResult" in evidence and "spec.result_ids" in evidence
    assert "linked_visuals:visualsByResult.get(r.id)" in evidence
    assert "Figure provenance" in card and "render pending" in card
    assert "Calculation code" in card and "Diagram source" in card and "Outputs" in card
    assert "declared_artifact:true" in card and "customArtifacts" in card
    assert "research-index-row" in evidence and "Back to results" in evidence
    assert "/formal/targets?project=" in evidence and "concept_id:target.id" in evidence
    assert "focusResearchResult" in evidence and "matchedIds" in evidence
    assert "pagination?.next_offset" in evidence and "targets.length<500" in evidence
    assert "originLabel" in evidence and "formalTargetIndex" in evidence
    assert "file.identity||scope+':'+file.path" in card and "input_files" in card
    assert "views.current()==='research'&&changedViews.has('research')" in workspace


def test_project_work_transitive_dependencies_ignore_raw_done_bypass(tmp_path, monkeypatch):
    _import(tmp_path)
    monkeypatch.setattr("laplace.manuscript.document_style.load", lambda *args, **kwargs: {})
    first = project_work.task("fixture", {"id": "A", "title": "A", "goal": "first"}, tmp_path)
    project_work.task("fixture", {"id": "B", "title": "B", "goal": "second",
                                           "depends_on": [first["id"]]}, tmp_path)
    project_work.task("fixture", {"id": "C", "title": "C", "goal": "third",
                                           "depends_on": ["B"]}, tmp_path)
    # Plant a historical/foreign transition that claims B done while A is open.
    project_work._append(tmp_path, {"record": "project-work-transition", "kind": "work-order",
        "id": "B", "task_id": "B", "project": "fixture", "status": "done",
        "evidence": ["claim-only"], "supersedes": "B"})

    state = project_work.state("fixture", tmp_path)
    rows = {row["id"]: row for row in state["tasks"]}

    assert rows["B"]["status"] == "blocked" and "A" in rows["B"]["blocked_by"]
    assert rows["C"]["status"] == "blocked" and "B" in rows["C"]["blocked_by"]
    with pytest.raises(ValueError, match="blocked"):
        guarded_transition("fixture", {"id": "C", "status": "done",
                                             "evidence": ["claim-only"]}, tmp_path)


def test_project_work_evidence_digest_invalidates_completion_and_dependents(tmp_path, monkeypatch):
    _import(tmp_path)
    monkeypatch.setattr("laplace.manuscript.document_style.load", lambda *args, **kwargs: {})
    evidence = tmp_path / "evidence" / "result.json"
    evidence.parent.mkdir()
    evidence.write_text('{"value": 1}\n', encoding="utf-8")
    project_work.task("fixture", {"id": "A", "title": "A", "goal": "measure"}, tmp_path)
    project_work.task("fixture", {"id": "B", "title": "B", "goal": "write",
                                           "depends_on": ["A"]}, tmp_path)

    with pytest.raises(ValueError, match="does not exist"):
        guarded_transition("fixture", {"id": "A", "status": "done",
                                             "evidence": ["evidence/missing.json"]}, tmp_path)

    transition = guarded_transition("fixture", {"id": "A", "status": "done",
        "evidence": ["evidence/result.json"]}, tmp_path)
    expected = hashlib.sha256(evidence.read_bytes()).hexdigest()
    assert transition["evidence_receipts"] == [{"path": "evidence/result.json", "sha256": expected}]
    assert {row["id"]: row for row in project_work.state("fixture", tmp_path)["tasks"]}["B"]["status"] == "ready"

    evidence.write_text('{"value": 2}\n', encoding="utf-8")
    rows = {row["id"]: row for row in project_work.state("fixture", tmp_path)["tasks"]}
    assert rows["A"]["evidence_currentness"]["status"] == "STALE"
    assert rows["A"]["status"] != "done"
    assert rows["B"]["status"] == "blocked"
    continued = project_work.context("fixture", "A", tmp_path)
    assert continued["evidence_currentness"]["status"] == "STALE"
    assert "STALE" in continued["prompt"]
