"""The system description (laplace.system): one owner map for everything the repository owns, measured.

The real tree must satisfy every claim; a tiny synthetic tree shows each claim actually bites (an upward import, an
unowned file, a retained edge that no longer exists, a new facade consumer); the affected cone of a real change
names its owners, consumers, evaluators and capability and leaves unrelated subsystems current."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace import system

ROOT = Path(__file__).resolve().parents[1]


def test_the_repository_satisfies_its_own_description():
    result = system.check(ROOT)
    assert result['ok'], json.dumps(result['problems'][:10], indent=1)
    assert result['owned_files'] > 1000 and result['source_modules'] > 500


def _fixture(root: Path) -> dict:
    files = {
        'src/laplace/__init__.py': '',
        'src/laplace/core_thing.py': 'VALUE = 1\n',
        'src/laplace/domain_thing.py': 'from laplace import core_thing\n',
        'src/laplace/door.py': 'from laplace import domain_thing\nfrom laplace.domain_thing import core_thing as forwarded\n',
        'pyproject.toml': '[project]\nname = "laplace-engine"\n[tool.setuptools.packages.find]\ninclude = ["laplace*"]\n',
        'docs/writing-code-overview.md': '# x\n',
    }
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    description = {
        'schema_version': system.SCHEMA, 'summary': 'fixture',
        'subsystems': [
            {'id': 'core.x', 'kind': 'core', 'summary': 'core', 'modules': ['laplace', 'laplace.core_thing'], 'files': []},
            {'id': 'domain.x', 'kind': 'domain', 'summary': 'domain', 'modules': ['laplace.domain_thing'], 'files': []},
            {'id': 'adapter.x', 'kind': 'adapter', 'summary': 'door', 'modules': ['laplace.door'], 'files': ['pyproject.toml', 'docs/**']},
        ],
        'retained': [], 'distributions': [{'name': 'laplace-engine', 'declaration': 'pyproject.toml', 'packages': ['laplace']}],
        'capabilities': [],
    }
    assert not system.shape_problems(description)
    return description


def _kinds(result, *, without=('front-door',)):
    return sorted({problem['kind'] for problem in result['problems'] if problem['kind'] not in without})


def test_each_claim_bites_on_a_synthetic_tree(tmp_path):
    description = _fixture(tmp_path)
    assert _kinds(system.check(tmp_path, description)) == []
    # an upward import: a core module importing the door
    (tmp_path / 'src/laplace/core_thing.py').write_text('from laplace import door\nVALUE = 1\n')
    system._graph.cache_clear()
    result = system.check(tmp_path, description)
    assert [p for p in result['problems'] if p['kind'] == 'layer-violation'][0]['importer'] == 'laplace.core_thing'
    # retaining it exactly makes it a named boundary; once the consumer is converted the stale entry fails
    description['retained'] = [{'id': 'fixture-boundary', 'owner': 'adapter.x', 'reason': 'fixture', 'retire_when': 'converted',
                                'edges': [['laplace.core_thing', 'laplace.door']]}]
    assert _kinds(system.check(tmp_path, description)) == []
    (tmp_path / 'src/laplace/core_thing.py').write_text('VALUE = 1\n')
    system._graph.cache_clear()
    assert _kinds(system.check(tmp_path, description)) == ['retained-edge-no-longer-exists']
    description['retained'] = []
    # an unowned file
    (tmp_path / 'src/laplace/orphan.py').write_text('X = 1\n')
    system._graph.cache_clear()
    assert 'unowned' in _kinds(system.check(tmp_path, description))
    (tmp_path / 'src/laplace/orphan.py').unlink()
    system._graph.cache_clear()
    # a package no distribution ships
    (tmp_path / 'src/elsewhere').mkdir()
    (tmp_path / 'src/elsewhere/__init__.py').write_text('')
    description['subsystems'][1]['modules'].append('elsewhere')
    system._graph.cache_clear()
    assert 'distribution' in _kinds(system.check(tmp_path, description))


def test_a_retained_facade_admits_no_new_consumer(tmp_path):
    description = _fixture(tmp_path)
    description['retained_facades'] = [{'facade': 'laplace.domain_thing', 'owner': 'adapter.x', 'reason': 'fixture', 'retire_when': 'converted',
                                        'consumers': ['src/laplace/door.py']}]
    system._graph.cache_clear()
    assert _kinds(system.check(tmp_path, description)) == []
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests/test_new.py').write_text('from laplace.domain_thing import core_thing\n')
    assert 'facade-consumer-not-retained' in _kinds(system.check(tmp_path, description))


def test_the_affected_cone_of_the_witness_change_names_its_consumers_and_leaves_neighbours_current():
    description = system.load()
    cone = system.cone(ROOT, ['src/laplace/projects/writing_sources.py', 'profiles/workflows/packet-return.v2.schema.json'], description, depth=1)
    assert cone['owners'] == ['domain.authoring', 'domain.projects']
    assert {'domain.work', 'adapter.native'} <= set(cone['affected_subsystems'])
    assert 'work.dispatch-return-admission' in cone['capabilities']
    assert 'tests/test_qualified_repository_pins.py' in cone['evaluators']
    assert {'adapter.desktop', 'domain.representation'} <= set(cone['unaffected_subsystems'])
    unrelated = system.cone(ROOT, ['docs/writing-campaigns.md'], description)
    assert unrelated['affected_subsystems'] == ['adapter.explanation'] and unrelated['capabilities'] == [] and unrelated['evaluators'] == []


def test_every_owned_path_has_one_owner_and_the_retired_package_is_gone():
    description = system.load()
    assert system.owner(description, 'src/laplace/system/__init__.py')[0] == 'core.identity'
    assert system.owner(description, 'src/atlas/store.py')[0] == 'domain.representation'
    assert system.owner(description, 'profiles/workflows/packet-return.v2.schema.json')[0] == 'domain.authoring'
    assert not (ROOT / 'src' / 'eigen_root').exists()
    with pytest.raises(ValueError):
        system.capability('no.such.capability', description, ROOT)
