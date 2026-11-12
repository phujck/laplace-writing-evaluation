from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from laplace.web import project_work_surface
from laplace.manuscript import writing_style
from laplace.native import tools as writing_tools
from laplace.pipeline import authoring


def _fixture(root: Path):
    profile = root / "profiles/voice/gerard-technical-v1.md"
    profile.parent.mkdir(parents=True); profile.write_text("# Voice v1\nWrite precisely.\n")
    manuscript = root / "book/manuscript"; manuscript.mkdir(parents=True)
    (manuscript / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}Text.\\end{document}\n")
    (manuscript / "manuscript_spec.json").write_text(json.dumps({"manuscript": {"genre": "article"}}))
    (root / "registry_projects.json").write_text(json.dumps({"projects": [{
        "name": "book", "project_dir": "book", "tex_root": "book/manuscript",
        "manifest": {"document": {"root": "book/manuscript/main.tex"}}}]}))
    return manuscript, profile


def _calibrated_fixture(root: Path):
    manuscript, profile = _fixture(root)
    source = root / "voice_sources/example.tex"
    source.parent.mkdir(parents=True)
    source.write_text("First line.\nA concrete derivation.\nLast line.\n", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    ledger = root / "evidence/voice/reading.json"
    ledger.parent.mkdir(parents=True)
    ledger.write_text(json.dumps({"schema": "laplace.author-reading/1", "reader": "author",
        "purpose": "Calibrate a technical profile.", "read": [{"path": "voice_sources/example.tex",
        "sha256": digest, "coverage": "complete source", "register": "technical paper"}],
        "working_observations": ["Concrete derivations carry the explanation."],
        "boundaries": ["Do not infer scientific truth from style."], "requested_remaining": [],
        "verification_limit": "Style calibration only."}, indent=2) + "\n", encoding="utf-8")
    profile.write_text("# Voice v2\n\nVersion: v2.0 (2026-09-30).\n\n## Current runtime prompt\n\nExplain the derivation.\n\n"
        "## Confirmed surface and terminology preferences\n\n- British English.\n\n"
        "Exact source identities are in `evidence/voice/reading.json`.\n", encoding="utf-8")
    return manuscript, profile, source, ledger, digest


def test_context_returns_selected_versioned_profile_and_project_guidance(tmp_path):
    _fixture(tmp_path)
    state = writing_style.state("book", tmp_path)
    context = writing_style.context("book", tmp_path)

    assert context["schema_version"] == "laplace.writing-style/2"
    assert context["revision"] == state["revision"]
    assert context["selected_profile"] == "profiles/voice/gerard-technical-v1.md"
    assert context["profile_revision"] == state["profile_revision"]
    assert context["profile_origin"] == "project"
    # the provider instructions name a profile by identity, never by a host path
    assert "resolved_path" not in context
    assert context["profile_read"] == {"operation": "writing_style", "payload": {"view": "profile"}}
    assert context["content"] == "# Voice v1\nWrite precisely.\n"
    assert context["content_scope"].endswith("full profile is lazy")
    assert context["guidance"] == "" and context["genre"] == "article"
    assert context["provenance"]["status"] == "UNRECORDED_LEGACY"
    assert context["read_more"]["operation"] == "writing_style"


def test_save_is_revision_guarded_and_never_edits_global_profile(tmp_path):
    manuscript, profile = _fixture(tmp_path); before = profile.read_bytes()
    current = writing_style.state("book", tmp_path)
    saved = writing_style.save("book", {"profile": current["profile"],
        "guidance": "Prefer the constructive order used in this book.",
        "expected_revision": current["revision"]}, tmp_path)

    assert saved["guidance"] == "Prefer the constructive order used in this book."
    spec = json.loads((manuscript / "manuscript_spec.json").read_text())
    assert spec["manuscript"]["voice_profile"] == current["profile"]
    assert spec["manuscript"]["style_guidance"] == saved["guidance"]
    assert profile.read_bytes() == before
    with pytest.raises(ValueError, match="revision conflict"):
        writing_style.save("book", {"profile": current["profile"], "guidance": "stale",
            "expected_revision": current["revision"]}, tmp_path)
    with pytest.raises(ValueError, match="profiles/voice"):
        writing_style.save("book", {"profile": "../../secret.md", "guidance": "",
            "expected_revision": saved["revision"]}, tmp_path)


def test_route_and_model_tool_share_canonical_style_and_action_receipt(tmp_path):
    _fixture(tmp_path)
    code, _, raw = project_work_surface.handle(
        "/work/writing-style", {"project": ["book"]}, "GET", repo_root=tmp_path)
    current = json.loads(raw); assert code == 200
    result = writing_tools.execute(tmp_path, "book", "work", "writing_style_change", {
        "profile": current["profile"], "guidance": "Book-local guidance.",
        "expected_revision": current["revision"]}, turn_id="WT-style")
    assert result["guidance"] == "Book-local guidance."
    assert result["action_receipt"]["views"] == ["writing_style", "manuscript"]
    rows = [json.loads(line) for line in (tmp_path / "contract/talk.jsonl").read_text().splitlines()]
    intent = next(row for row in rows if row.get("record") == "writing-style-change-intent")
    completed = next(row for row in rows if row.get("record") == "writing-style-change")
    assert intent["by"] == completed["by"] == "eigen:session"
    assert intent["before"]["revision"] == current["revision"]
    assert completed["after"]["revision"] == result["revision"]
    assert completed["after"]["content"] == result["content"]
    code, _, raw = project_work_surface.handle("/work/writing-style/change", {}, "POST",
        json.dumps({"project": "book", "profile": result["profile"], "guidance": "Route guidance.",
                    "expected_revision": result["revision"]}).encode(), tmp_path)
    assert code == 200 and json.loads(raw)["guidance"] == "Route guidance."


def test_save_preserves_each_omitted_field_and_journals_exact_before_after(tmp_path):
    _manuscript, original_profile = _fixture(tmp_path)
    original_bytes = original_profile.read_bytes()
    initial = writing_style.state("book", tmp_path)

    guidance_only = writing_style.save("book", {
        "guidance": "Only this project guidance changes.",
        "genre": "technical book",
        "expected_revision": initial["revision"]}, tmp_path)
    assert guidance_only["profile"] == initial["profile"]
    assert guidance_only["content"] == initial["content"]
    assert guidance_only["genre"] == "technical book"

    alternate = tmp_path / "profiles/voice/alternate.md"
    alternate.write_text("# Alternate\nKeep the derivation explicit.\n", encoding="utf-8")
    profile_only = writing_style.save("book", {
        "profile": "profiles/voice/alternate.md",
        "expected_revision": guidance_only["revision"]}, tmp_path)
    assert profile_only["guidance"] == guidance_only["guidance"]
    assert profile_only["content"] == alternate.read_text(encoding="utf-8")
    assert original_profile.read_bytes() == original_bytes

    rows = [json.loads(line) for line in (tmp_path / "contract/talk.jsonl").read_text().splitlines()]
    changes = [row for row in rows if row.get("record") == "writing-style-change"]
    assert len(changes) == 2
    assert changes[0]["before"]["revision"] == initial["revision"]
    assert changes[0]["after"]["revision"] == guidance_only["revision"]
    assert changes[1]["before"]["revision"] == guidance_only["revision"]
    assert changes[1]["after"]["revision"] == profile_only["revision"]


def test_default_profile_falls_back_only_to_deployed_house_and_is_bounded(tmp_path):
    manuscript = tmp_path / "book/manuscript"; manuscript.mkdir(parents=True)
    (manuscript / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}Text.\\end{document}\n")
    (manuscript / "manuscript_spec.json").write_text(json.dumps({"manuscript": {"genre": "article"}}))
    (tmp_path / "registry_projects.json").write_text(json.dumps({"projects": [{
        "name": "book", "project_dir": "book", "tex_root": "book/manuscript",
        "manifest": {"document": {"root": "book/manuscript/main.tex"}}}]}))
    deployed = Path(writing_style.__file__).resolve().parents[3] / writing_style.DEFAULT_PROFILE
    before = deployed.read_bytes()
    assert writing_style.MAX_PROFILE_BYTES == 64 * 1024

    value = writing_style.state("book", tmp_path)
    assert value["profile_origin"] == "deployed-house"
    assert value["resolved_path"] == str(deployed)
    assert any(row["path"] == writing_style.DEFAULT_PROFILE and row["origin"] == "deployed-house"
               for row in value["profiles"])
    saved = writing_style.save("book", {"profile": writing_style.DEFAULT_PROFILE,
        "guidance": "Local only.", "expected_revision": value["revision"]}, tmp_path)
    assert saved["profile_origin"] == "deployed-house" and deployed.read_bytes() == before
    custom = tmp_path / "profiles/voice/oversized.md"; custom.parent.mkdir(parents=True)
    custom.write_bytes(b"x" * (writing_style.MAX_PROFILE_BYTES + 1))
    with pytest.raises(ValueError, match="bounded"):
        writing_style.save("book", {"profile": "profiles/voice/oversized.md",
            "guidance": "", "expected_revision": saved["revision"]}, tmp_path)


def test_style_guidance_change_stales_context_and_prompt_labels_precedence(tmp_path):
    manuscript, _profile_path = _fixture(tmp_path)
    context = authoring.build_context("book", {"files": ["main.tex"]}, tmp_path)
    assert "PROSE-ONLY WRITING STYLE" in context["prompt"]
    assert "Current manuscript genre: article" in context["prompt"]
    assert context["consumed"]["writing_style"]["selected_profile"] == writing_style.DEFAULT_PROFILE
    current = writing_style.state("book", tmp_path)
    writing_style.save("book", {"profile": current["profile"],
        "guidance": "A historical project note.", "expected_revision": current["revision"]}, tmp_path)
    stale = authoring.inspect("book", repo_root=tmp_path)["stale"]
    row = next(item for item in stale if item["context_id"] == context["context_id"])
    assert "writing-style-profile-or-guidance-changed" in row["reasons"]


def test_inspection_is_summary_first_and_descends_to_profile_or_provenance(tmp_path):
    _calibrated_fixture(tmp_path)
    summary = writing_style.inspect("book", {}, tmp_path)
    assert "content" not in summary
    assert summary["genre"] == "article"
    assert summary["provenance"]["status"] == "RECORDED"
    assert summary["profile_title"] == "Voice v2" and summary["profile_version"] == "v2.0"
    assert summary["profile_editable"] is True
    assert summary["provenance"]["sources"] == 1
    assert {row["payload"]["view"] for row in summary["read_more"]} == {"profile", "provenance"}

    profile = writing_style.inspect("book", {"view": "profile"}, tmp_path)
    assert "Explain the derivation." in profile["content"]
    provenance = writing_style.inspect("book", {"view": "provenance"}, tmp_path)
    assert provenance["sources"][0]["coverage"] == "complete source"
    assert provenance["working_observations"] == ["Concrete derivations carry the explanation."]
    assert provenance["boundaries"] == ["Do not infer scientific truth from style."]

    alternate = tmp_path / "profiles/voice/alternate.md"
    alternate.write_text("# Alternate voice\n\nVersion: v3.1.\n\nWrite briefly.\n", encoding="utf-8")
    preview = writing_style.inspect("book", {"view": "profile",
        "profile": "profiles/voice/alternate.md"}, tmp_path)
    assert preview["selected_profile"] == writing_style.DEFAULT_PROFILE
    assert preview["inspected_profile"] == "profiles/voice/alternate.md"
    assert preview["profile_title"] == "Alternate voice" and preview["profile_version"] == "v3.1."
    assert preview["content"].endswith("Write briefly.\n")
    assert writing_style.state("book", tmp_path)["profile"] == writing_style.DEFAULT_PROFILE


def test_calibration_reads_only_explicit_ledger_handles_and_returns_no_score(tmp_path):
    _manuscript, _profile, source, _ledger, digest = _calibrated_fixture(tmp_path)
    bundle = writing_style.calibration("book", {"purpose": "Check explanatory cadence.",
        "sources": [{"path": "voice_sources/example.tex", "line_start": 2, "line_end": 2}]}, tmp_path)
    assert bundle["sources"] == [{"path": "voice_sources/example.tex", "sha256": digest,
        "coverage": "complete source", "register": "technical paper",
        "current_sha256": digest, "currentness": "CURRENT", "line_start": 2,
        "line_end": 2, "text": "A concrete derivation."}]
    assert bundle["excerpt_bytes"] == len("A concrete derivation.".encode())
    assert bundle["autonomous_analysis"] is False and bundle["voice_score"] is None
    assert bundle["judgement_template"]["summary"] == ""
    with pytest.raises(ValueError, match="explicit ledger source"):
        writing_style.calibration("book", {"sources": []}, tmp_path)
    with pytest.raises(ValueError, match="ledger handles"):
        writing_style.calibration("book", {"sources": ["unlisted.tex"]}, tmp_path)
    source.write_text("Changed bytes.\n", encoding="utf-8")
    stale = writing_style.calibration("book", {"sources": [{"path": "voice_sources/example.tex",
        "line_start": 1, "line_end": 1}]}, tmp_path)
    assert stale["sources"][0]["currentness"] == "STALE"
    assert stale["sources"][0]["text"] is None


def test_direct_author_preference_can_update_a_legacy_profile_without_fake_sources(tmp_path):
    _manuscript, profile = _fixture(tmp_path)
    current = writing_style.state("book", tmp_path)
    revised = "# Voice v1.1\nPrefer direct constructions.\n"
    result = writing_style.update_profile("book", {"profile": current["profile"],
        "content": revised, "expected_profile_revision": current["profile_revision"],
        "basis": "author_preference", "reason": "The author prefers direct constructions.",
        "provenance_kind": "direct-author-instruction"}, tmp_path)
    assert profile.read_text(encoding="utf-8") == revised
    assert result["scope_changed"] == "global-profile"
    assert result["provenance"]["status"] == "UNRECORDED_LEGACY"
    rows = [json.loads(line) for line in (tmp_path / "contract/talk.jsonl").read_text().splitlines()]
    intent = next(row for row in rows if row.get("record") == "voice-profile-change-intent")
    assert intent["basis"] == "author_preference" and intent["source_handles"] == []
    assert intent["judgement"]["author_instruction"] == "The author prefers direct constructions."
    with pytest.raises(ValueError, match="revision conflict"):
        writing_style.update_profile("book", {"profile": current["profile"], "content": revised,
            "expected_profile_revision": current["profile_revision"], "basis": "author_preference",
            "reason": "Stale.", "provenance_kind": "direct-author-instruction"}, tmp_path)


def test_source_calibrated_profile_update_requires_current_ledger_hashes_and_judgement(tmp_path):
    _manuscript, profile, _source, _ledger, digest = _calibrated_fixture(tmp_path)
    current = writing_style.state("book", tmp_path)
    revised = profile.read_text(encoding="utf-8") + "\nUse examples as reasoning.\n"
    common = {"profile": current["profile"], "content": revised,
        "expected_profile_revision": current["profile_revision"],
        "expected_provenance_revision": current["provenance"]["revision"],
        "basis": "source_calibration", "reason": "Apply the completed reading.",
        "judgement": {"summary": "Examples carry the derivation.", "retained": ["Direct explanation"],
            "changed": ["Give examples a logical job"], "genre_boundary": "Technical prose only.",
            "authorship_boundary": "Use the recorded authorship weights.",
            "verification_limit": "Style only.", "author_instruction": "Recalibrate after reading."}}
    with pytest.raises(ValueError, match="does not match recorded"):
        writing_style.update_profile("book", {**common,
            "source_handles": [{"path": "voice_sources/example.tex", "sha256": "0" * 64}]}, tmp_path)
    result = writing_style.update_profile("book", {**common,
        "source_handles": [{"path": "voice_sources/example.tex", "sha256": digest}]}, tmp_path)
    assert result["profile_revision"] != current["profile_revision"]
    assert result["provenance"]["revision"] == current["provenance"]["revision"]


def test_native_tools_expose_bounded_inspection_calibration_and_profile_update(tmp_path):
    _manuscript,profile,_source,_ledger,digest=_calibrated_fixture(tmp_path)
    summary=writing_tools.execute(tmp_path,"book","work","writing_style",{"view":"summary"})
    assert "content" not in summary and summary["profile_title"]=="Voice v2"
    calibration=writing_tools.execute(tmp_path,"book","work","writing_style_calibration",{
        "sources":[{"path":"voice_sources/example.tex","line_start":2,"line_end":2}]})
    assert calibration["autonomous_analysis"] is False and calibration["sources"][0]["sha256"]==digest
    revised=profile.read_text()+"\nPrefer the constructive order.\n"
    changed=writing_tools.execute(tmp_path,"book","work","writing_style_profile_change",{
        "profile":summary["profile"],"content":revised,
        "expected_profile_revision":summary["profile_revision"],
        "basis":"author_preference","reason":"The author requested constructive order.",
        "provenance_kind":"direct-author-instruction"},turn_id="WT-style-profile")
    assert changed["scope_changed"]=="global-profile"
    assert changed["action_receipt"]["views"]==["writing_style","manuscript"]
    help_read=writing_tools.execute(tmp_path,"book","work","help",{"operation":"writing_style_calibration"})
    help_write=writing_tools.execute(tmp_path,"book","work","help",{"operation":"writing_style_profile_change"})
    assert help_read["action"]["operation"]=="writing_style_calibration"
    assert help_write["action"]["operation"]=="writing_style_profile_change"


def test_http_style_routes_are_summary_first_with_explicit_calibration_and_profile_change(tmp_path):
    _manuscript,profile,_source,_ledger,digest=_calibrated_fixture(tmp_path)
    code,_,raw=project_work_surface.handle("/work/writing-style",{
        "project":["book"],"view":["summary"]},"GET",repo_root=tmp_path)
    summary=json.loads(raw);assert code==200 and "content" not in summary
    code,_,raw=project_work_surface.handle("/work/writing-style/calibration",{},"POST",
        json.dumps({"project":"book","sources":["voice_sources/example.tex"]}).encode(),tmp_path)
    assert code==200 and json.loads(raw)["sources"][0]["sha256"]==digest
    revised=profile.read_text()+"\nUse the constructive order.\n"
    code,_,raw=project_work_surface.handle("/work/writing-style/profile-change",{},"POST",
        json.dumps({"project":"book","profile":summary["profile"],"content":revised,
            "expected_profile_revision":summary["profile_revision"],"basis":"author_preference",
            "reason":"Direct author preference.","provenance_kind":"direct-author-instruction"}).encode(),tmp_path)
    assert code==200 and json.loads(raw)["scope_changed"]=="global-profile"
