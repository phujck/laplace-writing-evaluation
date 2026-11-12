"""Core consolidation, research family (R1) and the Writing representation seam (R2), 2026-10-19.

R1: the six Research owners plus the explicit-root context (writing.research_context) and the reply shapes
(writing.research_http) import no facade, HTTP door, scanner or gateway; laplace.web.research_surface is the HTTP entry
and forwards the owners' same objects; the native operation table calls the owners directly (one implementation,
two doors); the source-optional Research home keeps its identities across a manuscript start.

R2: Writing body custody reaches Atlas through one narrow representation entry (writing.representation) with an
explicit local root; the legacy nonlocal custody read stays a labelled, lazily imported fallback.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
from pathlib import Path

import pytest

from laplace.core import bodies as core_bodies
from laplace.web import research_surface
from laplace.writing import schemas as writing_schemas
from laplace.native import tools as writing_tools
from laplace.research import research_records
from laplace.research import research_runs
from laplace.research import research_context
from laplace.research import research_catalogue
from laplace.web import research_http
from laplace.writing import operations
from laplace.writing import operations
from laplace.web import research_artifact_read, research_http
from laplace.research import research_catalogue, research_context, research_observation, research_presentation, research_records, research_runs

SRC = Path(__file__).resolve().parents[1] / 'src' / 'laplace'
PYTHON = str(SRC.parents[1] / 'scripts' / 'laplace-python')
OWNERS = ['research/research_context.py', 'web/research_http.py', 'research/research_observation.py',
          'research/research_presentation.py', 'research/research_records.py', 'research/research_runs.py',
          'research/research_catalogue.py', 'web/research_artifact_read.py']
DOORS = {'laplace.web.research_surface', 'laplace.web.authoring', 'laplace.web.authoring_http', 'laplace.web.scanner',
         'laplace.native.tools'}


def _imports(path):
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ''
            yield module, node.lineno
            for alias in node.names:
                yield (module + '.' + alias.name if module else alias.name), node.lineno


def test_the_research_owners_import_no_facade_or_door_even_lazily():
    offences = [(rel, line, name) for rel in OWNERS for name, line in _imports(SRC / rel) if name in DOORS]
    assert offences == []
    facade = (SRC / 'web' / 'research_surface.py').read_text()
    for moved in ('def _project(', 'def owner_home(', 'def _project_root(', 'def _inside(', 'def result_bindings(',
                  'def record_input_contract(', 'def producer_input_contract(', 'def producer_execution_contract(',
                  'RESEARCH_RECORDS_SCHEMA = ', '_RUNS = ', '_PRODUCERS = ', '_PRODUCER_FLAGS = '):
        assert moved not in facade, moved + ' is still a facade body'
    assert '_owned_file_receipt' not in (SRC / 'research' / 'research_observation.py').read_text()
    assert 'core_receipts.file_receipt(' in (SRC / 'research' / 'research_records.py').read_text()


def test_the_facade_forwards_the_owners_same_objects_and_the_table_calls_them():
    # the /research door forwards no owner name any more (2026-10-21): each owner holds its own object
    from laplace.web import research_surface
    for name in ('result_bindings', 'record_input_contract', 'producer_execution_contract', 'state_read', 'run_status_read',
                 '_RECORDS', '_RUNS', '_project', 'owner_home'):
        assert not hasattr(research_surface, name), name
    assert callable(research_records.result_bindings) and callable(research_runs.producer_execution_contract)
    assert research_records._RECORDS == 'research_records.json' and research_runs._RUNS == 'research_runs'
    assert writing_schemas.SCHEMAS['research_record'] == research_records.record_input_contract()
    assert writing_schemas.SCHEMAS['research_producer'] == research_runs.producer_input_contract()
    assert operations._FAMILY_OPERATIONS[operations._execute_research] == frozenset(
        {'research', 'research_reconcile', 'research_record', 'research_producer', 'experiment_run', 'run_status', 'run_cancel'})
    assert not [name for name, _ in _imports(SRC / 'writing' / 'operations.py') if name == 'laplace.web.research_surface']


def test_the_research_owners_import_headless(tmp_path):
    script = ('import json,sys,importlib\n'
              'for m in ("laplace.research.research_context","laplace.web.research_http","laplace.research.research_observation",'
              '"laplace.research.research_records","laplace.research.research_runs","laplace.research.research_catalogue",'
              '"laplace.research.research_presentation","laplace.web.research_artifact_read"):\n'
              '    importlib.import_module(m)\n'
              'print(json.dumps(sorted(x for x in sys.modules if x.startswith("laplace"))))')
    out = subprocess.run([PYTHON, '-c', script], capture_output=True, text=True, cwd=str(SRC.parents[1]),
                         env={**os.environ, 'LAPLACE_STATE': str(tmp_path / 'state')})
    assert out.returncode == 0, out.stderr[-2000:]
    loaded = set(json.loads(out.stdout.strip().splitlines()[-1]))
    assert not (loaded & DOORS), sorted(loaded & DOORS)


def _general_project(root: Path, name: str = 'campaign') -> Path:
    from laplace.projects import library as writing_projects
    assert writing_projects.create({'name': name, 'title': 'Campaign', 'kind': 'general', 'purpose': 'Audit.'}, root)[0] == 201
    home = research_context.owner_home(name, root)
    assert home == (root / 'writing_projects' / name / 'manuscript').resolve()
    (home / 'research_runs').mkdir()
    (home / 'research_runs' / 'run-1.result.json').write_text('{"recall": 0.75}')
    status, made = research_records.record(name, {'kind': 'result', 'id': 'result:recall', 'result': 'research_runs/run-1.result.json',
                                                  'title': 'Recall', 'measures': [{'label': 'Recall', 'key': 'recall'}]}, root)
    assert status == 201, made
    return home


def test_source_optional_research_keeps_its_home_and_identities_across_a_manuscript_start(tmp_path):
    from laplace.manuscript import manuscript_source
    from laplace.projects import library as writing_projects
    home = _general_project(tmp_path)
    item, state_home = research_context.project('campaign', tmp_path)
    assert state_home == home and research_context.project_root(item, tmp_path) == (tmp_path / 'writing_projects' / 'campaign').resolve()
    before = research_catalogue.state_read('campaign', tmp_path, view='result', ident='result:recall')
    assert before[0] == 200 and before[1]['exact'] is True
    binding = research_records.result_bindings(home, ['result:recall'], research_context.project_root(item, tmp_path))
    assert binding['status'] == 'CURRENT' and binding['bindings'][0]['revision'] == before[1]['result']['revision']
    # the real owner door the app's Home "Add manuscript" uses: the selected draft moves, the Research home does not
    assert writing_projects.start_manuscript({'project': 'campaign', 'title': 'Report', 'kind': 'paper'}, tmp_path)[0] == 201
    source = manuscript_source.resolve('campaign', repo_root=tmp_path)
    assert source['manuscript_dir'].endswith('/manuscript/working-draft')
    assert research_context.project('campaign', tmp_path)[1] == home == research_context.owner_home('campaign', tmp_path)
    after = research_catalogue.state_read('campaign', tmp_path, view='result', ident='result:recall')
    assert after == before, 'same id, revision and measurements through the same state home'
    assert research_records.result_bindings(home, ['result:recall'], research_context.project_root(item, tmp_path)) == binding
    # the selected manuscript scope is distinct from the project scope: the result file is a state-home file
    read = research_artifact_read.resolve_read(tmp_path, 'campaign', {'scope': ['manuscript'], 'path': ['research_runs/run-1.result.json']})
    assert not isinstance(read, tuple) and read.target == home / 'research_runs' / 'run-1.result.json'
    assert research_context.inside(home, '../outside.json') is None and research_context.inside(home, 'research_runs/run-1.result.json') == read.target


def test_native_and_http_doors_answer_from_one_owner(tmp_path):
    _general_project(tmp_path)
    native = writing_tools.execute(tmp_path, 'campaign', 'work', 'research', {'view': 'result', 'id': 'result:recall'})
    code, _, raw = research_surface.handle('/research/result', {'project': ['campaign'], 'id': ['result:recall']}, 'GET', b'', repo_root=tmp_path)
    assert code == 200 and json.loads(raw) == native
    summary = writing_tools.execute(tmp_path, 'campaign', 'work', 'research', {'view': 'summary'})
    code, _, raw = research_surface.handle('/research/state', {'project': ['campaign'], 'view': ['summary']}, 'GET', b'', repo_root=tmp_path)
    assert code == 200 and json.loads(raw)['results'] == summary['results']
    with pytest.raises(operations.OwnerError) as refused:
        writing_tools.execute(tmp_path, 'campaign', 'work', 'run_status', {'id': 'run-missing'})
    code, _, raw = research_surface.handle('/research/run/status', {'project': ['campaign'], 'id': ['run-missing']}, 'GET', b'', repo_root=tmp_path)
    assert code == 404 and json.loads(raw) == {'error': 'unknown run'} and 'unknown run' in str(refused.value)
    code, _, raw = research_surface.handle('/research/record', {'project': ['campaign']}, 'POST', b'[1]', repo_root=tmp_path)
    assert code == 400 and json.loads(raw) == {'error': 'body must be an object'}
    code, _, raw = research_surface.handle('/research/producer', {}, 'POST', b'not json', repo_root=tmp_path)
    assert code == 400 and json.loads(raw) == {'error': 'bad json'}


def test_result_bindings_report_unresolved_and_stale_links_without_claiming_validity(tmp_path):
    home = _general_project(tmp_path)
    item, _ = research_context.project('campaign', tmp_path)
    project_root = research_context.project_root(item, tmp_path)
    missing = research_records.result_bindings(home, ['result:absent'], project_root)
    assert missing == {'status': 'UNRESOLVED', 'bindings': [], 'gaps': ['linked research result is unresolved: result:absent']}
    # recording a result that names an unavailable run is refused by the record owner before any write
    status, refused = research_records.record('campaign', {'kind': 'result', 'id': 'result:ran', 'result': 'research_runs/run-1.result.json',
                                                           'run_id': 'run-vanished', 'title': 'Ran'}, tmp_path)
    assert status == 422 and 'run_id is unavailable' in refused['error']
    status, made = research_records.record('campaign', {'kind': 'result', 'id': 'result:ran', 'result': 'research_runs/run-1.result.json',
                                                        'title': 'Ran'}, tmp_path)
    assert status == 201, made
    # the receipt a record publishes is laplace.core.receipts.file_receipt: the one before/intended/observed shape
    assert set(made['owned_changes']['files'][0]) == {'scope', 'path', 'before_sha256', 'after_sha256', 'observed_after_sha256'}
    assert made['owned_changes']['files'][0]['path'] == 'writing_projects/campaign/manuscript/research_records.json'
    # a recorded result whose run later vanishes is STALE by the run owner's answer, not by any scientific claim
    store = home / 'research_records.json'; rows = json.loads(store.read_text())
    for row in rows['records']:
        if row['id'] == 'result:ran':
            row['run_id'] = 'run-vanished'
    store.write_text(json.dumps(rows))
    stale = research_records.result_bindings(home, ['result:ran'], project_root)
    assert stale['status'] == 'UNRESOLVED' and stale['bindings'][0]['currentness'] == 'STALE'
    assert stale['bindings'][0]['reason'] == 'the linked result run is not current'


# ---- R2: the Writing representation seam -------------------------------------------------------------------------

def test_body_custody_reaches_atlas_through_the_representation_entry_only(tmp_path, monkeypatch):
    from atlas.store import BlobStore
    from laplace.representation import writing_bodies as bodies, writing_representation as representation
    from laplace.core.bodies import REFERENCE_SCHEMA as PUBLIC_BODY_SCHEMA
    store = bodies.store(tmp_path)
    assert isinstance(store, BlobStore) and isinstance(representation.body_store(tmp_path), BlobStore)
    raw = b'{"exact":"body bytes"}'
    handle = store.put(raw)
    # the same explicit local root for both spellings; the handle is content-addressed and lives under the repository
    assert representation.body_store(tmp_path).key_path(handle) == store.key_path(handle)
    assert store.key_path(handle).is_relative_to(tmp_path / 'contract' / 'writing_bodies')
    reference = {'schema_version': PUBLIC_BODY_SCHEMA, 'content_handle': handle, 'store': 'contract/writing_bodies',
                 'bytes': len(raw), 'encoding': 'application/json'}
    assert bodies.read_bytes(reference, tmp_path) == raw
    with core_bodies.budget(limit=4096) as ledger:
        assert bodies.read_bytes(reference, tmp_path) == raw and ledger['reads'] == 1
    # a reference to a store that is not this repository's: under a finite budget it is refused BEFORE the legacy
    # entry is reached; unbudgeted it reaches exactly the entry's explicit legacy read and nothing else
    foreign = {**reference, 'store': 'atlas-custody', 'content_handle': 'sha256:' + 'f' * 64, 'bytes': 7}
    monkeypatch.setattr(representation, 'legacy_custody_body', lambda handle: pytest.fail('legacy read reached under a finite budget'))
    with core_bodies.budget(limit=4096):
        with pytest.raises(core_bodies.BudgetExceeded, match='refused before'):
            bodies.read_bytes(foreign, tmp_path)
    reached = []
    monkeypatch.setattr(representation, 'legacy_custody_body', lambda handle: reached.append(handle) or b'legacy!')
    assert bodies.read_bytes(foreign, tmp_path) == b'legacy!' and reached == [foreign['content_handle']]
    # a tampered body is refused by the store's own hash check; a missing body by name
    path = store.key_path(handle)
    path.write_bytes(path.read_bytes() + b'\n')
    with pytest.raises(Exception) as corrupt:
        store.get(handle)
    assert type(corrupt.value).__name__ == 'BlobHashMismatch'
    with pytest.raises(Exception) as missing:
        store.get('sha256:' + '0' * 64)
    assert type(missing.value).__name__ == 'BlobMissing'


def test_a_fresh_synthetic_store_replays_typed_events_and_its_read_only_face_never_writes(tmp_path):
    from atlas.errors import StoreError
    from atlas.store import ConceptricStore
    from test_store_projection import _sew, _wake   # the Atlas suite's own typed fixtures; no canonical history is read
    root = tmp_path / 'store'
    writer = ConceptricStore(root, expected_store_role='fixture')
    wake = _wake()
    writer.append(wake)
    replayed = writer.replay()
    assert replayed.event_count == 1
    # the same typed event is the same identity in a second fresh store: content-addressed, not store-local
    twin = ConceptricStore(tmp_path / 'twin', expected_store_role='fixture')
    twin.append(wake)
    assert twin.replay() == replayed
    reader = ConceptricStore(root, read_only=True, expected_store_role='fixture')
    assert reader.replay() == replayed
    with pytest.raises(StoreError, match='refuses append'):
        reader.append(_sew())
    # a different declared role is a refusal, never a silent re-labelling
    with pytest.raises(StoreError):
        ConceptricStore(root, expected_store_role='another-fixture')
