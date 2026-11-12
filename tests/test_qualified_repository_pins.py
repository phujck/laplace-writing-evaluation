"""The dispatch return's qualified repository pins (capability work.dispatch-return-admission in laplace.system).

The return contract says an input path is "absolute or repository-relative", and a worker's evidence comes back from
``repository.read`` as ``{repository, path}``; the return validator used to refuse every such pin outside the
project's artifact/source scope ("evidence path is outside this project's artifact/source scope") and the schema
refused the ``repository`` member, so a correct worker return stood INVALID while the reader that produced its pins
admitted them. These checks hold the one admission both now share (``writing_sources.qualified_file``), its
refusals, the unaffected neighbours (project pins, outputs, resolvers without repository scope) and recovery of an
already-landed return without replay. Synthetic public fixtures only.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest

from laplace.work import project_work
from laplace.projects import writing_sources
from laplace.pipeline import workflow
from test_writing_dispatch import tree as base_tree  # noqa: F401  (fixture the next one wraps)
from test_writing_dispatch_return_validity import _case, _child, _pin, tree  # noqa: F401  (fixture)


def _repository_file(root, relative='evidence/public/worker-notes.md', text='public repository evidence\n'):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _qualified(root, path):
    return {'repository': 'laplace', 'path': path.relative_to(root).as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def _journal_rows(root):
    path = root / 'contract' / 'talk.jsonl'
    return path.read_bytes().count(b'\n') if path.is_file() else 0


def test_a_repository_qualified_input_pin_is_admitted_through_the_repository_owner(tree):
    """Fine and coarse views agree: the per-pin validator admits {repository, path, sha256} exactly as the repository
    owner admits it, and the dispatch child stands COMPLETE with no return error."""
    _, ident, _, source, output, returned, doc = _case(tree, 2)
    evidence = _repository_file(tree)
    assert writing_sources.qualified_file(tree, {'repository': 'laplace', 'path': 'evidence/public/worker-notes.md'}) == evidence.resolve()
    doc['inputs'] = [_qualified(tree, evidence), _pin(source)]
    returned.write_text(json.dumps(doc))
    row = _child(tree, ident)
    assert row['state'] == 'COMPLETE' and not row['return_errors'], (row['state'], row['return_errors'])


def test_the_contracts_repository_relative_input_is_admitted_and_its_coarse_view_agrees(tree):
    """The diamond: the contract's own wording (an unqualified repository-relative input outside the project) and the
    validator's execution now agree; before, the coarse contract admitted what the fine check refused."""
    _, ident, _, source, output, returned, doc = _case(tree, 2)
    evidence = _repository_file(tree, 'evidence/public/relative-notes.md')
    doc['inputs'] = [{'path': 'evidence/public/relative-notes.md', 'sha256': hashlib.sha256(evidence.read_bytes()).hexdigest()}]
    returned.write_text(json.dumps(doc))
    row = _child(tree, ident)
    assert row['state'] == 'COMPLETE' and not row['return_errors'], (row['state'], row['return_errors'])


@pytest.mark.parametrize('case', ['unknown-repository', 'escape', 'symlink-out', 'changed-bytes', 'repository-output'])
def test_a_qualified_pin_the_owner_would_not_admit_is_refused_by_name(tree, tmp_path_factory, case):
    _, ident, _, source, output, returned, doc = _case(tree, 2)
    evidence = _repository_file(tree)
    pin = _qualified(tree, evidence)
    if case == 'unknown-repository':
        pin['repository'] = 'not-configured'
    elif case == 'escape':
        outside = tmp_path_factory.mktemp('outside') / 'secret.md'
        outside.write_text('outside the repository')
        pin.update(path='../' + outside.parent.name + '/secret.md', sha256=hashlib.sha256(outside.read_bytes()).hexdigest())
    elif case == 'symlink-out':
        outside = tmp_path_factory.mktemp('outside') / 'secret.md'
        outside.write_text('outside the repository')
        link = tree / 'evidence' / 'public' / 'link.md'
        os.symlink(outside, link)
        pin.update(path='evidence/public/link.md', sha256=hashlib.sha256(outside.read_bytes()).hexdigest())
    elif case == 'changed-bytes':
        evidence.write_text('changed after the read')
    if case == 'repository-output':
        doc['output'] = {**_qualified(tree, output), 'repository': 'laplace'}
    else:
        doc['inputs'] = [pin]
    returned.write_text(json.dumps(doc))
    row = _child(tree, ident)
    assert row['state'] != 'COMPLETE' and row['return_errors'], row
    expected = {'unknown-repository': 'available repository', 'escape': 'escape', 'symlink-out': 'escape',
                'changed-bytes': 'pinned artifact bytes moved', 'repository-output': 'project artifact'}[case]
    assert any(expected in error for error in row['return_errors']), row['return_errors']


def test_unaffected_neighbours_keep_their_meaning(tree):
    """Project-artifact pins validate as before; a resolver without repository scope (a wave lane's) refuses a
    qualified pin by name instead of resolving it some other way."""
    _, ident, _, source, output, returned, doc = _case(tree, 2)
    returned.write_text(json.dumps(doc))
    assert _child(tree, ident)['state'] == 'COMPLETE'
    evidence = _repository_file(tree)
    doc['inputs'] = [_qualified(tree, evidence)]
    problems = workflow.packet_return_problems(doc, schema_directory=workflow.packet_schema_directory(tree),
                                               resolve_pin=lambda raw: tree / raw, require_current_inputs=True)
    assert any('admits no repository-qualified pin' in problem for problem in problems), problems


def test_a_landed_return_is_revalidated_in_place_without_rewrite_or_replay(tree):
    """Recovery from the landed effect: the same return bytes that stood INVALID under the old admission stand
    COMPLETE on the next read; the read rewrites nothing and banks no journal row."""
    _, ident, _, source, output, returned, doc = _case(tree, 2)
    evidence = _repository_file(tree)
    doc['inputs'] = [_qualified(tree, evidence)]
    returned.write_text(json.dumps(doc))
    token, rows = hashlib.sha256(returned.read_bytes()).hexdigest(), _journal_rows(tree)
    row = _child(tree, ident)
    assert row['state'] == 'COMPLETE', (row['state'], row['return_errors'])
    assert hashlib.sha256(returned.read_bytes()).hexdigest() == token and _journal_rows(tree) == rows


def test_the_return_contract_view_states_the_qualified_pin(tree):
    """Help follows the contract: the child return contract served to the model carries the repository member."""
    schema = json.loads((workflow.packet_schema_directory(tree) / 'packet-return.v2.schema.json').read_text())
    for pin in (schema['$defs']['artifact_pin'], schema['properties']['inputs']['items']):
        assert 'repository' in pin['properties'] and 'repository' not in pin['required']


def test_a_pin_in_another_configured_repository_is_read_at_that_repositorys_coordinate(tree, tmp_path_factory):
    """The discriminating case for every consumer of the pin: a second configured repository outside the workspace,
    whose coordinate names no workspace file. A consumer that drops the repository member and resolves the bare path
    (the old one-argument call) cannot find these bytes, so the coarse COMPLETE standing fails with it."""
    external = tmp_path_factory.mktemp('external-repository')
    (external / 'notes').mkdir()
    evidence = external / 'notes' / 'only-here.md'
    evidence.write_text('evidence only the external repository holds\n')
    config = tree / 'profiles' / 'writing_sources.json'
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps({'repositories': {'laplace': '.', 'external': str(external)}}))
    assert not (tree / 'notes' / 'only-here.md').exists()
    _, ident, _, source, output, returned, doc = _case(tree, 2)
    doc['inputs'] = [{'repository': 'external', 'path': 'notes/only-here.md', 'sha256': hashlib.sha256(evidence.read_bytes()).hexdigest()}]
    returned.write_text(json.dumps(doc))
    row = _child(tree, ident)
    assert row['state'] == 'COMPLETE' and not row['return_errors'], (row['state'], row['return_errors'])
