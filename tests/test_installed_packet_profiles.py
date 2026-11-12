"""Default resource precedence without installed interpreter-ancestor borrowing."""
import json
from pathlib import Path

import pytest

from laplace.pipeline import workflow

NAMES = ('packet-return.schema.json', 'packet-return.v2.schema.json',
         'packet-judgement.schema.json', 'packet-judgement.v2.schema.json')


def profiles(directory):
    directory.mkdir(parents=True)
    for index, name in enumerate(NAMES):
        (directory / name).write_text(json.dumps({'$id': 'fixture/' + str(index)}))
    return directory


def test_source_checkout_defaults_and_explicit_directory_are_preserved(tmp_path):
    assert workflow.packet_schema_directory() == Path(__file__).resolve().parents[1] / 'profiles/workflows'
    override = profiles(tmp_path / 'profiles/workflows')
    assert workflow.packet_schema_directory(tmp_path) == override
    assert len(workflow.packet_schemas(override)) == 4
    for path in override.iterdir():path.unlink()
    assert workflow.packet_schema_directory(tmp_path) == override
    assert workflow.packet_schemas(override) == {}


def test_package_resources_win_over_source_defaults_but_not_workspace(tmp_path, monkeypatch):
    package = tmp_path / 'src/laplace'
    packaged = profiles(package / 'pipeline/packet_profiles')
    monkeypatch.setattr(workflow, 'package_root', lambda: package)
    monkeypatch.setattr(workflow, 'source_tree', lambda: pytest.fail('Packaged defaults need no source lookup'))
    assert workflow.packet_schema_directory(tmp_path / 'data') == packaged
    override = profiles(tmp_path / 'data/profiles/workflows')
    assert workflow.packet_schema_directory(tmp_path / 'data') == override


def test_installed_missing_defaults_refuse_without_interpreter_ancestor_fallback(tmp_path, monkeypatch):
    package = tmp_path / 'lib/python3.12/site-packages/laplace'
    profiles(tmp_path / 'lib/python3.12/profiles/workflows')  # tempting old installed fallback
    monkeypatch.setattr(workflow, 'package_root', lambda: package)
    monkeypatch.setattr(workflow, 'source_tree', lambda: pytest.fail('Installed ancestry is not a source tree'))
    with pytest.raises(workflow.WorkflowRefused, match='PACKET-DEFAULTS-UNAVAILABLE'):
        workflow.packet_schema_directory(tmp_path / 'fresh')


def test_incomplete_packaged_defaults_do_not_borrow_source(tmp_path, monkeypatch):
    package = tmp_path / 'src/laplace'
    packaged = profiles(package / 'pipeline/packet_profiles')
    (packaged / NAMES[0]).unlink()
    profiles(tmp_path / 'profiles/workflows')
    monkeypatch.setattr(workflow, 'package_root', lambda: package)
    monkeypatch.setattr(workflow, 'source_tree', lambda: pytest.fail('Incomplete package cannot borrow source'))
    with pytest.raises(workflow.WorkflowRefused, match='PACKET-DEFAULTS-UNAVAILABLE'):
        workflow.packet_schema_directory()
