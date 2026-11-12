"""The active writer guidance reaches prose without freezing its paragraph shape."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.manuscript import projection_viewer, writing_style
from laplace.engine import taste_retrieval
from laplace.pipeline import dispatch, document_model, node_index, schema


ROOT = Path(__file__).resolve().parents[1]


class _Project:
    name = "fixture"
    kind = "manuscript"
    target_dir = "manuscript"

    def __init__(self, root: Path):
        self.root = root
        (root / "spec").write_text(json.dumps({"manuscript": {"genre": "article"}}))

    def read_plan(self, _repo_root=None):
        return {"sections": [{"id": "S"}]}

    def resolved_target_dir(self, _repo_root=None):
        return self.root / "manuscript"

    def stage_path(self, stage: str, _repo_root=None):
        return self.root / stage


def _packet() -> dict:
    return {
        "contract": {"section_id": "S"},
        "paragraphs": [
            {"paragraph_id": "S-p1", "input_nodes": ["n1"]},
            {"paragraph_id": "S-p2", "input_nodes": ["n2"]},
        ],
        "objects": {"n1": {"essence": "one"}, "n2": {"essence": "two"}},
        "equation_ledger": {},
        "citations": {},
    }


def test_section_dispatch_consumes_writer_owned_exposition_guidance(tmp_path, monkeypatch):
    project = _Project(tmp_path)
    monkeypatch.setattr(dispatch.registry, "resolve", lambda name, **kwargs: project if name == "fixture" else None)
    monkeypatch.setattr(dispatch.narrative, "narrative_packet", lambda *args, **kwargs: _packet())
    out = dispatch._compile_dispatch_core("S", "write the section", "prose", "fixture", ROOT)
    assert "error" not in out, out
    prompt = out["prompt"]
    flat_prompt = " ".join(prompt.replace(">", " ").split())
    assert prompt.count("<!-- VOICE-PROFILE -->") == 1
    assert "You own the section's argument and may reorder, merge or split" in prompt
    assert "No paragraph pattern, sentence pattern or numerical style quota" in prompt
    assert "choose the expository order and paragraph boundaries" in prompt
    runtime = writing_style._runtime_content((ROOT / writing_style.DEFAULT_PROFILE).read_text())
    assert runtime in prompt
    assert "Write a connected explanation for an intelligent reader" in flat_prompt
    assert "Treat examples as part of the reasoning" in flat_prompt
    assert "Carry the argument confidently at the strength the evidence supports" in flat_prompt
    assert "one rendered paragraph per paragraph plan" not in prompt.casefold()
    assert "at most one sentence in five" not in prompt.casefold()
    assert "does not prove" not in prompt.casefold()


def test_paragraph_repair_receives_same_profile_but_keeps_its_narrow_scope(tmp_path, monkeypatch):
    project = _Project(tmp_path)
    monkeypatch.setattr(dispatch.registry, "resolve", lambda name, **kwargs: project if name == "fixture" else None)
    monkeypatch.setattr(dispatch.narrative, "narrative_packet", lambda *args, **kwargs: _packet())
    out = dispatch.compile_paragraph_dispatch("fixture", "S", "S-p1", ROOT)
    assert "error" not in out, out
    assert out["prompt"].count("<!-- VOICE-PROFILE -->") == 1
    assert writing_style._runtime_content((ROOT / writing_style.DEFAULT_PROFILE).read_text()) in out["prompt"]
    assert "Rewrite ONLY paragraph S-p1" in out["prompt"]


def test_taste_loader_extracts_current_runtime_block_case_insensitively():
    rows = taste_retrieval._profile_candidates(ROOT, {"writing"})
    voice = next(row for row in rows if row["ref"] == "gerard-technical-v1")
    assert voice["text"] == writing_style._runtime_content((ROOT / writing_style.DEFAULT_PROFILE).read_text())
    assert "Genre and authorship" not in voice["text"]
    assert "Supply and scope" not in voice["text"]
    assert not voice["text"].startswith("# Gerard McCaul")


def test_neutral_weld_carries_positive_common_guidance(tmp_path, monkeypatch):
    project = _Project(tmp_path)
    manuscript = project.resolved_target_dir()
    provenance = project.stage_path("provenance")
    manuscript.mkdir(parents=True)
    provenance.mkdir(parents=True)
    (manuscript / "S.tex").write_text(
        "% PLAN:S\n% NODES: n1\n% S-p1\n"
        "A complete technical paragraph explains the fixture without a rhetorical list.\n",
        encoding="utf-8",
    )
    (provenance / "S.json").write_text(json.dumps({
        "section_id": "S", "paragraphs": [{
            "spec_id": "S-p1", "spec_ids": ["S-p1"], "nodes_realised": ["n1"],
            "equations": [], "qualifications": [], "citations": [],
        }],
    }), encoding="utf-8")
    monkeypatch.setattr(dispatch.registry, "resolve", lambda name, **kwargs: project if name == "fixture" else None)
    out = dispatch.compile_weld_dispatch("fixture", tmp_path, voice_on=False)
    assert "error" not in out, out
    assert "Develop one connected explanation for the intended reader" in out["prompt"]
    assert "lead with the achieved result and its physical meaning" in out["prompt"]
    assert "keep the main comparison complete in one place" in out["prompt"]
    assert "Give completed work more space than pending work" in out["prompt"]
    assert "State scope and uncertainty once, where they change the inference" in out["prompt"]
    assert "Present a negative experiment as a finding with a causal consequence" in out["prompt"]
    assert "detector report is review evidence" in out["prompt"]
    assert "opposition flourishes" not in out["prompt"]
    assert "REGISTER-ORIENTATION" not in out["prompt"]


def test_fidelity_accepts_reordered_merged_plans_with_exact_provenance(tmp_path, monkeypatch):
    project = _Project(tmp_path)
    manuscript = project.resolved_target_dir()
    provenance = project.stage_path("provenance")
    manuscript.mkdir(parents=True)
    provenance.mkdir(parents=True)
    (manuscript / "S.tex").write_text(
        "% PLAN:S\n% NODES: n1 n2\n% S-p2\n% S-p1\n"
        "The second obligation and the first are explained together in this connected paragraph.\n",
        encoding="utf-8",
    )
    (provenance / "S.json").write_text(json.dumps({
        "section_id": "S",
        "paragraphs": [{
            "spec_id": "S-p2", "spec_ids": ["S-p2", "S-p1"],
            "nodes_realised": ["n2", "n1"], "equations": [],
            "qualifications": [], "citations": [],
        }],
    }), encoding="utf-8")
    monkeypatch.setattr(document_model.registry, "resolve", lambda name, **kwargs: project if name == "fixture" else None)
    monkeypatch.setattr(document_model.narrative, "narrative_packet", lambda *args, **kwargs: _packet())
    result = document_model.validate_fidelity("fixture", "S", tmp_path)
    assert result["pass"], result


def _fidelity_result(tmp_path, monkeypatch, *, packet, fragment, records):
    project = _Project(tmp_path)
    manuscript = project.resolved_target_dir()
    provenance = project.stage_path("provenance")
    manuscript.mkdir(parents=True)
    provenance.mkdir(parents=True)
    (manuscript / "S.tex").write_text(fragment, encoding="utf-8")
    (provenance / "S.json").write_text(json.dumps({
        "section_id": "S", "paragraphs": records,
    }), encoding="utf-8")
    monkeypatch.setattr(document_model.registry, "resolve", lambda name, **kwargs: project if name == "fixture" else None)
    monkeypatch.setattr(document_model.narrative, "narrative_packet", lambda *args, **kwargs: packet)
    return document_model.validate_fidelity("fixture", "S", tmp_path)


def test_fidelity_rejects_sidecar_that_fabricates_a_missing_marker(tmp_path, monkeypatch):
    result = _fidelity_result(
        tmp_path, monkeypatch, packet=_packet(),
        fragment=("% PLAN:S\n% NODES: n1 n2\n% S-p1\n"
                  "Only the first planned paragraph exists in the rendered fragment.\n"),
        records=[{
            "spec_id": "S-p1", "spec_ids": ["S-p1", "S-p2"],
            "nodes_realised": ["n1", "n2"], "equations": [],
            "qualifications": [], "citations": [],
        }],
    )
    assert not result["pass"]
    assert any("markers differ" in issue["issue"] for issue in result["issues"])


def test_fidelity_rejects_merged_plan_with_dropped_node_obligation(tmp_path, monkeypatch):
    result = _fidelity_result(
        tmp_path, monkeypatch, packet=_packet(),
        fragment=("% PLAN:S\n% NODES: n1 n2\n% S-p2\n% S-p1\n"
                  "Both plans share one rendered paragraph but one node is absent.\n"),
        records=[{
            "spec_id": "S-p2", "spec_ids": ["S-p2", "S-p1"],
            "nodes_realised": ["n2"], "equations": [],
            "qualifications": [], "citations": [],
        }],
    )
    assert not result["pass"]
    assert any("input node 'n1' absent" in issue["issue"] for issue in result["issues"])


def test_fidelity_rejects_split_plan_with_dropped_qualification(tmp_path, monkeypatch):
    packet = _packet()
    packet["paragraphs"] = [{
        "paragraph_id": "S-p1", "input_nodes": ["n1"], "qualification": "scope-q",
    }]
    result = _fidelity_result(
        tmp_path, monkeypatch, packet=packet,
        fragment=("% PLAN:S\n% NODES: n1\n% S-p1\n"
                  "The first half of the split explains enough words for a paragraph.\n\n"
                  "% S-p1\nThe second half completes the explanation without its scope.\n"),
        records=[
            {"spec_id": "S-p1", "spec_ids": ["S-p1"], "nodes_realised": ["n1"],
             "equations": [], "qualifications": [], "citations": []},
            {"spec_id": "S-p1", "spec_ids": ["S-p1"], "nodes_realised": [],
             "equations": [], "qualifications": [], "citations": []},
        ],
    )
    assert not result["pass"]
    assert any("required qualification absent" in issue["issue"] for issue in result["issues"])


def test_fidelity_rejects_reordered_plan_with_dropped_citation(tmp_path, monkeypatch):
    packet = _packet()
    packet["paragraphs"][1]["citations"] = ["required-key"]
    result = _fidelity_result(
        tmp_path, monkeypatch, packet=packet,
        fragment=("% PLAN:S\n% NODES: n1 n2\n% S-p2\n"
                  "The second plan is deliberately rendered before the first plan here.\n\n"
                  "% S-p1\nThe first plan follows in a separate connected paragraph.\n"),
        records=[
            {"spec_id": "S-p2", "spec_ids": ["S-p2"], "nodes_realised": ["n2"],
             "equations": [], "qualifications": [], "citations": []},
            {"spec_id": "S-p1", "spec_ids": ["S-p1"], "nodes_realised": ["n1"],
             "equations": [], "qualifications": [], "citations": []},
        ],
    )
    assert not result["pass"]
    assert any("required citation 'required-key' absent" in issue["issue"]
               for issue in result["issues"])


def test_split_plan_consumers_accumulate_every_record(tmp_path, monkeypatch):
    pdir = tmp_path / "prose_provenance"
    pdir.mkdir()
    records = [
        {"spec_id": "S-p1", "spec_ids": ["S-p1"], "nodes_realised": ["claim:a"],
         "equations": ["eq:a"], "qualifications": ["q:a"], "citations": ["c:a"]},
        {"spec_id": "S-p1", "spec_ids": ["S-p1"], "nodes_realised": ["claim:b"],
         "equations": ["eq:b"], "qualifications": ["q:b"], "citations": ["c:b"]},
    ]
    (pdir / "S.json").write_text(json.dumps({
        "section_id": "S", "paragraphs": records,
    }), encoding="utf-8")
    para_of, eq_prose = node_index._load_prose(tmp_path)
    assert para_of["S-p1"]["nodes_realised"] == ["claim:a", "claim:b"]
    assert para_of["S-p1"]["equations"] == ["eq:a", "eq:b"]
    assert eq_prose == {"eq:a": ["claim:a"], "eq:b": ["claim:b"]}

    fragment = tmp_path / "S.tex"
    fragment.write_text(
        "% PLAN:S\n% S-p1\nFirst split paragraph carries enough explanatory words.\n\n"
        "% S-p1\nSecond split paragraph carries enough explanatory words.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(projection_viewer, "_safe_path", lambda _value: fragment)
    monkeypatch.setattr(document_model, "load_provenance", lambda *_args, **_kwargs: records)
    monkeypatch.setattr(document_model, "load_decisions", lambda *_args, **_kwargs: [])
    out = projection_viewer.forks(str(fragment), "fixture")
    assert len(out["paragraphs"]) == 2
    first, second = out["paragraphs"]
    assert first["nodes_realised"] == ["claim:a"]
    assert first["qualifications"] == ["q:a"]
    assert first["citations"] == ["c:a"]
    assert second["nodes_realised"] == ["claim:b"]
    assert second["qualifications"] == ["q:b"]
    assert second["citations"] == ["c:b"]


def test_operational_method_amendment_replaces_the_paragraph_template():
    rows = {row["id"]: row for row in dispatch.method_rows_for(
        "manuscript", ROOT, include_all=False
    )}
    paragraph = rows["M-expose-support-explore"]
    assert paragraph["law"].startswith("Paragraph structure follows the connected argument")
    assert "compulsory prose mould" in paragraph["forbids"]
    assert any(note.startswith("AMEND-20260920-writer-owns-exposition")
               for note in paragraph["amended"])
    assert "memory://law/09" in paragraph["refs"]
    assert any(item["amendment"] == "AMEND-20260920-writer-owns-exposition"
               and "memory://law/09" in item["refs"]
               for item in paragraph["amendment_refs"])
    assert "one paragraph per plan" not in schema.PROSE_STAGE_PREAMBLE.casefold()
