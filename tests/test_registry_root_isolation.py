"""Compatibility projects belong to their actual checkout, not every root."""
import dataclasses,json
from pathlib import Path
from laplace.pipeline import registry
from laplace.projects import library as writing_projects
from laplace.core import checkout


def test_isolated_root_has_only_explicit_even_unmaterialized_projects(tmp_path):
    (tmp_path/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'empty-new','tex_root':'projects/empty/manuscript','project_dir':'projects/empty'}]}))
    assert list(registry.all_projects(tmp_path))==['empty-new']
    assert [row['name'] for row in writing_projects._library(tmp_path)['projects']]==['empty-new']
    assert registry.resolve('paper_eigen',tmp_path) is None


def test_explicit_row_wins_a_present_compatibility_layout(tmp_path):
    (tmp_path/'paper_eigen').mkdir()
    assert registry.resolve('paper_eigen',tmp_path).kind=='loop'
    (tmp_path/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'paper_eigen','tex_root':'my/new/manuscript','project_dir':'my/new'}]}))
    projects,provenance=registry._build_registry(tmp_path)
    assert projects['paper_eigen'].project_dir=='my/new'
    assert projects['paper_eigen'].tex_root=='my/new/manuscript'
    assert provenance['paper_eigen']=='registry-row'


def test_compatibility_home_presence_preserves_its_specialized_layout(tmp_path):
    assert registry.all_projects(tmp_path)=={}
    (tmp_path/'paper_eigen').mkdir()
    value=registry.resolve('paper_eigen',tmp_path)
    assert value.kind=='loop' and value.loop_dir=='paper_eigen/_loop'
    assert set(registry.all_projects(tmp_path))=={'paper_eigen'}


def test_production_compatibility_snapshot_is_unchanged_read_only():
    root=Path(__file__).resolve().parents[1]
    path=root/'evidence/WRITING_INTEGRATION_2026-09-29/registry-root-isolation.json'
    snapshot=json.loads(path.read_text())
    actual,provenance=registry._build_registry(root)
    for name,origin in snapshot['before_provenance'].items():
        if origin!='hardcoded-block':continue
        assert dataclasses.asdict(actual[name])==snapshot['before'][name]
        assert provenance[name]==origin
    assert snapshot['production_unchanged'] is True
