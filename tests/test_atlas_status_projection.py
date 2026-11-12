import json
from pathlib import Path

from laplace.representation.atlas_status_projection import project_atlas_current_status


def _write(root: Path, relative: str, value: object) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_projection_derives_coverage_and_visible_work_from_the_worklist(tmp_path: Path) -> None:
    project, base = "demo", "synthetics papers/demo"
    _write(tmp_path, f"{base}/spec/manuscript_spec.json", {"benchmarks": [{"results": f"{base}/numerics/results/B1.json"}]})
    _write(tmp_path, f"{base}/spec/worklist.json", {"worklist_version": 7, "items": [{"id": "A", "item": "first", "discharge": "evidence"}, {"id": "B", "item": "second", "discharge": "evidence"}, {"id": "C", "item": "third", "discharge": "evidence"}]})
    _write(tmp_path, f"{base}/spec/conceptric_v1.json", {"nodes": [{"id": "work:A"}]})
    _write(tmp_path, f"{base}/numerics/results/B1.json", {"record": "result"})
    (tmp_path / "corpus_friction").mkdir()
    (tmp_path / f"corpus_friction/{project}.jsonl").write_text(json.dumps({"id": "A"}) + "\n")
    (tmp_path / "corpus_friction/campaign.jsonl").write_text(json.dumps({"record": "stage", "id": "ATLAS-S0", "stage": 0, "gate": {"cmd": "false"}}) + "\n")
    status = project_atlas_current_status(tmp_path, project=project, work_cap=2)
    assert [row["id"] for row in status["worklist"]["visible_items"]] == ["B", "C"]
    assert status["coverage"]["generated_graph"]["missing_ids"] == ["B", "C"]
    assert status["coverage"]["project_ledger"]["missing_ids"] == ["B", "C"]
    assert status["campaign"]["currentness"] == "CURRENT-AT-OBSERVATION"
    assert status["campaign"]["effective"]["stages"][0]["status"] == "UNRUN"
    assert status["result_records"]["visible"][0]["source"]["status"] == "REFERENCED"
