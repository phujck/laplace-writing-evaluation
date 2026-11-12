"""The project authoring lifecycle (writing.project_lifecycle, M5 2026-10-15) on disposable synthetic projects.

A source-optional ("general") project moves into a selected manuscript and canonical reader/argument plan
ownership through the existing owners, by one guarded transition reachable natively (structure_change
start_authoring), over HTTP (POST /work/structure/change) and by the human Add manuscript (POST /projects/start).
The same project keeps its slug, directories, selected source, Work, references, artifacts, histories and
drafts. No real project, history or provider is touched.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from laplace.core import identity_doors
from laplace.work import project_work
from laplace.projects import library as wp
from laplace.native import tools as writing_tools
from laplace.pipeline import registry
from laplace.projects import project_lifecycle as lifecycle
from laplace.writing import records as writing_records

PROJECT = 'dd'


def _general(root, name=PROJECT):
    status, created = wp.create({'name': name, 'title': 'Due diligence', 'kind': 'company', 'purpose': 'Assess', 'audience': 'Board'}, root)
    assert status == 201, created
    return created


def _metadata(root, project=PROJECT):
    return writing_tools.execute(root, project, 'work', 'project_metadata', {})


def _row(root, project=PROJECT):
    return next(row for row in json.loads((root / 'registry_projects.json').read_text())['projects'] if row['name'] == project)


def _tree(path: Path) -> dict:
    return {file.relative_to(path).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
            for file in sorted(path.rglob('*')) if file.is_file() and not file.name.endswith('.lock')}


def _start(root, payload=None, project=PROJECT, mode='work'):
    payload = payload or _metadata(root, project)['authoring_lifecycle']['next_action']['payload']
    return writing_tools.execute(root, project, mode, 'structure_change', payload)


def test_a_source_less_project_starts_its_manuscript_and_owns_its_plan_through_the_existing_owners(tmp_path):
    _general(tmp_path)
    before = _metadata(tmp_path)['authoring_lifecycle']
    assert before['state'] == 'NO_MANUSCRIPT' and before['plan']['owned'] is False
    assert before['next_action'] == {'operation': 'structure_change', 'payload': {'operation': 'start_authoring',
        'expected_project_lifecycle': before['revision']}, 'does': before['next_action']['does']}
    row_before = _row(tmp_path)
    started = _start(tmp_path)
    assert started['status'] == 'STARTED' and started['lifecycle']['state'] == 'PLAN_OWNED'
    record = registry.resolve(PROJECT, tmp_path)
    assert record.kind == 'project' and record.project_dir == row_before['project_dir'], 'the same layout and home'
    assert record.plan_path == 'writing_projects/dd/manuscript/projection_plan.json'
    assert not (tmp_path / record.plan_path).exists(), 'the plan file is the plan owner\'s to create'
    row_after = _row(tmp_path)
    assert {key: value for key, value in row_after.items() if key != 'manifest'} == {key: value for key, value in row_before.items() if key != 'manifest'}
    assert {key: value for key, value in row_after['manifest'].items() if key != 'planning'} == row_before['manifest']
    assert row_after['manifest']['planning'] == {'owner': 'project_structure', 'plan_path': record.plan_path, 'declared': started['receipt_id'],
        'selection_identity': started['planning']['selection_identity'], 'by': 'agent', 'publication': 'PUBLISHED',
        'journal_offset': row_after['manifest']['planning']['journal_offset'], 'journal_anchor': row_after['manifest']['planning']['journal_anchor']}
    anchor = row_after['manifest']['planning']['journal_anchor']
    assert anchor['file'] and anchor['cut_bytes'] == min(row_after['manifest']['planning']['journal_offset'], registry.PLANNING_ANCHOR_BYTES)
    assert started['planning']['selection_identity'].startswith('sha256:')
    # source, structure, logical plan and section planning are reachable together through their own owners
    document = writing_tools.execute(tmp_path, PROJECT, 'work', 'source', {})['document']
    assert document['root'].startswith('writing_projects/dd/manuscript/') and document['storage_dir'] == 'writing_projects/dd/manuscript'
    structure = writing_tools.execute(tmp_path, PROJECT, 'work', 'structure', {})
    assert structure['status'] == 'MISSING'
    initialized = writing_tools.execute(tmp_path, PROJECT, 'work', 'structure_change', {'operation': 'initialize',
        'expected_revision': structure['revision'], 'expected_source_revision': structure['selected_source']['revision']})
    assert initialized['ok'] and (tmp_path / record.plan_path).is_file()
    from laplace.research import concepts as concepts_surface
    from laplace.manuscript import project_structure
    concept = concepts_surface.state(PROJECT, root=tmp_path)
    writing_tools.execute(tmp_path, PROJECT, 'work', 'concept_change', {'operation': 'add_node', 'node': 'claim:one',
        'node_kind': 'result', 'essence': 'One claim', 'base_revision': concept['revision']})
    plan = project_structure.state(PROJECT, tmp_path)
    placed = writing_tools.execute(tmp_path, PROJECT, 'work', 'structure_change', {'operation': 'plan', 'expected_revision': plan['revision'],
        'op': {'kind': 'set-nodes', 'section': plan['sections'][0]['id'], 'order': ['claim:one']}})
    assert placed['ok'] and project_structure.state(PROJECT, tmp_path)['sections'][0]['node_ids'] == ['claim:one']
    logical = writing_tools.execute(tmp_path, PROJECT, 'work', 'logical_plan', {})
    assert logical.get('status') != 'NOT_AVAILABLE'
    caps = _metadata(tmp_path)['capabilities']
    assert caps['reader_plan'] and caps['concepts'] and not caps['start_planning'] and not caps['start_manuscript']


def test_an_existing_project_with_a_selected_manuscript_adopts_plan_ownership_and_keeps_every_byte(tmp_path):
    _general(tmp_path)
    status, draft = wp._start_manuscript_unplanned({'project': PROJECT, 'title': 'Briefing', 'kind': 'paper'}, tmp_path)
    assert status == 201, draft
    home = tmp_path / 'writing_projects' / PROJECT
    # accumulated project state: authored draft text, a Work item, an artifact and a reference note
    source = tmp_path / draft['source']['root']
    source.write_text(source.read_text().replace('\\end{document}', 'Authored findings stay.\n\\end{document}'))
    project_work.task(PROJECT, {'id': 'WORK-dd', 'title': 'Review findings', 'goal': 'Check the briefing'}, tmp_path)
    (home / 'artifacts').mkdir(exist_ok=True)
    (home / 'artifacts' / 'findings.json').write_text('{"finding": "kept"}')
    tree = _tree(home)
    journal = (tmp_path / 'contract' / 'talk.jsonl').read_bytes()
    work = json.dumps(project_work.read(PROJECT, {'view': 'summary'}, tmp_path), sort_keys=True)
    selection = wp.metadata(PROJECT, tmp_path)['selection']
    observed = _metadata(tmp_path)['authoring_lifecycle']
    assert observed['state'] == 'MANUSCRIPT_WITHOUT_PLAN' and _metadata(tmp_path)['capabilities']['start_planning'] is True
    adopted = _start(tmp_path)
    assert adopted['status'] == 'PLAN_OWNED' and adopted['manuscript_started'] is None
    assert _tree(home) == tree, 'manuscript, selection, artifacts and every project file keep their bytes'
    assert (tmp_path / 'contract' / 'talk.jsonl').read_bytes().startswith(journal), 'the journal only gains its receipt'
    assert json.dumps(project_work.read(PROJECT, {'view': 'summary'}, tmp_path), sort_keys=True) == work
    assert wp.metadata(PROJECT, tmp_path)['selection'] == selection
    rows = [json.loads(line) for line in (tmp_path / 'contract' / 'talk.jsonl').read_text().splitlines()]
    receipts = [row for row in rows if row.get('record') == 'project-planning-declared']
    assert len(receipts) == 1 and receipts[0]['id'] == adopted['receipt_id'] and receipts[0]['selection_identity'] == observed['manuscript']['selection_identity']
    assert len(list(home.glob('manuscript/working-draft*'))) == 1, 'no second manuscript'


def test_repeating_the_transition_is_an_idempotent_no_op(tmp_path):
    _general(tmp_path)
    first = _start(tmp_path)
    registry_bytes = (tmp_path / 'registry_projects.json').read_bytes()
    again = _start(tmp_path, {'operation': 'start_authoring', 'expected_project_lifecycle': first['lifecycle']['revision']})
    assert again['status'] == 'ALREADY_OWNED' and again['unchanged'] is True
    assert (tmp_path / 'registry_projects.json').read_bytes() == registry_bytes


def test_missing_or_stale_guards_refuse_before_any_effect(tmp_path):
    _general(tmp_path)
    registry_bytes = (tmp_path / 'registry_projects.json').read_bytes()
    from laplace.native import declarations as writing_declarations
    with pytest.raises(writing_declarations.PayloadAdmissionError):          # the native door's shape admission
        _start(tmp_path, {'operation': 'start_authoring'})
    with pytest.raises(identity_doors.IdentityRefused):                        # the owner's own identity gate
        lifecycle.start_authoring(PROJECT, {'operation': 'start_authoring'}, tmp_path)
    stale = _metadata(tmp_path)['authoring_lifecycle']['revision']
    meta = _metadata(tmp_path)
    writing_tools.execute(tmp_path, PROJECT, 'work', 'project_metadata_change', {'title': 'Renamed briefing', 'expected_revision': meta['revision']})
    renamed = (tmp_path / 'registry_projects.json').read_bytes()
    assert renamed != registry_bytes
    with pytest.raises(identity_doors.IdentityRefused):
        _start(tmp_path, {'operation': 'start_authoring', 'expected_project_lifecycle': stale})
    assert (tmp_path / 'registry_projects.json').read_bytes() == renamed
    assert not list((tmp_path / 'writing_projects' / PROJECT).glob('manuscript/working-draft*')), 'no manuscript was started'
    with pytest.raises(Exception):
        _start(tmp_path, {'operation': 'start_authoring', 'expected_project_lifecycle': stale, 'plan_path': 'elsewhere.json'})


def test_unsafe_or_foreign_states_refuse_and_name_their_reason(tmp_path):
    _general(tmp_path)
    manuscript = tmp_path / 'writing_projects' / PROJECT / 'manuscript'
    manuscript.mkdir(exist_ok=True)
    for name in ('one.tex', 'two.tex'):
        (manuscript / name).write_text('\\documentclass{article}\n\\begin{document}\nText.\n\\end{document}\n')
    ambiguous = _metadata(tmp_path)['authoring_lifecycle']
    assert ambiguous['state'] == 'REFUSED' and 'editions' in ambiguous['reason'] and ambiguous['next_action'] is None
    with pytest.raises(lifecycle.LifecycleRefused, match='editions'):
        _start(tmp_path, {'operation': 'start_authoring', 'expected_project_lifecycle': ambiguous['revision']})
    (manuscript / 'two.tex').unlink()
    (manuscript / 'projection_plan.json').write_text('{"sections": []}')
    planned = _metadata(tmp_path)['authoring_lifecycle']
    assert planned['state'] == 'REFUSED' and 'without a declaration' in planned['reason']
    registry_bytes = (tmp_path / 'registry_projects.json').read_bytes()
    with pytest.raises(lifecycle.LifecycleRefused):
        _start(tmp_path, {'operation': 'start_authoring', 'expected_project_lifecycle': planned['revision']})
    assert (tmp_path / 'registry_projects.json').read_bytes() == registry_bytes
    with pytest.raises(ValueError, match='Unknown project'):
        lifecycle.observe('absent-project', tmp_path)


def test_a_conceptric_project_already_owns_its_plan_and_is_not_changed(tmp_path):
    status, created = wp.create({'name': 'paperx', 'title': 'Paper X', 'kind': 'paper', 'purpose': 'p', 'audience': 'a'}, tmp_path)
    assert status == 201, created
    observed = _metadata(tmp_path, 'paperx')['authoring_lifecycle']
    assert observed['state'] == 'LAYOUT_OWNED' and observed['layout'] == 'conceptric'
    registry_bytes = (tmp_path / 'registry_projects.json').read_bytes()
    result = _start(tmp_path, {'operation': 'start_authoring', 'expected_project_lifecycle': observed['revision']}, project='paperx')
    assert result['status'] == 'ALREADY_OWNED' and (tmp_path / 'registry_projects.json').read_bytes() == registry_bytes


def test_the_review_actor_cannot_start_authoring(tmp_path):
    _general(tmp_path)
    payload = _metadata(tmp_path)['authoring_lifecycle']['next_action']['payload']
    with pytest.raises(Exception):
        _start(tmp_path, payload, mode='review')
    assert registry.resolve(PROJECT, tmp_path).plan_path == ''


def test_http_and_human_doors_reach_the_same_owner(tmp_path):
    from laplace.web import project_work_surface
    _general(tmp_path, 'viahttp')
    _general(tmp_path, 'viahuman')
    status, _, body = wp.handle('/projects/metadata', {'project': ['viahttp']}, 'GET', b'', tmp_path)
    metadata = json.loads(body)
    assert status == 200 and metadata['authoring_lifecycle']['state'] == 'NO_MANUSCRIPT'
    request = json.dumps({'project': 'viahttp', **metadata['authoring_lifecycle']['next_action']['payload']}).encode()
    status, _, body = project_work_surface.handle('/work/structure/change', {}, 'POST', request, tmp_path)
    http = json.loads(body)
    assert status == 200 and http['status'] == 'STARTED' and http['lifecycle']['state'] == 'PLAN_OWNED'
    status, human = wp.start_manuscript({'project': 'viahuman', 'title': 'Human', 'kind': 'paper'}, tmp_path)
    assert status == 201 and human['authoring_lifecycle']['state'] == 'PLAN_OWNED' and human['planning']['plan_path'].endswith('viahuman/manuscript/projection_plan.json')
    assert human['planning']['by'] == 'author' and http['planning']['by'] == 'author', 'tool calls are attributed to the agent, page and HTTP calls to the author'
    status, again = wp.start_manuscript({'project': 'viahuman', 'title': 'Human', 'kind': 'paper'}, tmp_path)
    assert status == 409, 'a second Add manuscript never makes a second draft'
    assert len(list((tmp_path / 'writing_projects' / 'viahuman' / 'manuscript').glob('working-draft*'))) == 1


def test_a_partial_transition_is_recovered_by_the_same_call(tmp_path, monkeypatch):
    _general(tmp_path)
    original = lifecycle._set_planning
    def failed(*args, **kwargs):
        raise OSError('controlled declaration failure')
    monkeypatch.setattr(lifecycle, '_set_planning', failed)
    with pytest.raises(OSError):
        _start(tmp_path)
    monkeypatch.setattr(lifecycle, '_set_planning', original)
    partial = _metadata(tmp_path)['authoring_lifecycle']
    assert partial['state'] == 'MANUSCRIPT_WITHOUT_PLAN', 'the manuscript landed; planning is the remaining step'
    recovered = _start(tmp_path)
    assert recovered['status'] == 'PLAN_OWNED' and recovered['manuscript_started'] is None
    assert len(list((tmp_path / 'writing_projects' / PROJECT / 'manuscript').glob('working-draft*'))) == 1
    rows = [json.loads(line) for line in (tmp_path / 'contract' / 'talk.jsonl').read_text().splitlines()]
    assert [row['record'] for row in rows if row.get('record', '').startswith(('manuscript-draft', 'project-planning'))] == [
        'manuscript-draft-start', 'manuscript-draft-ready', 'project-planning-declared']


def test_source_less_research_reads_are_unchanged_by_the_transition(tmp_path):
    _general(tmp_path)
    before = writing_tools.execute(tmp_path, PROJECT, 'work', 'research', {'view': 'summary'})
    _start(tmp_path)
    after = writing_tools.execute(tmp_path, PROJECT, 'work', 'research', {'view': 'summary'})
    # the research owner still serves the same records, results, figures and producers from the project's state
    # home; only its index stamp and the read basis (which now names the selected manuscript) move
    volatile = {'index_stamp', 'read_basis'}
    assert {k: v for k, v in after.items() if k not in volatile} == {k: v for k, v in before.items() if k not in volatile}


# --- repair1 (2026-10-15): PB-R1 canonical admission, PB-R2 declaration/home fences, PB-R3 publication recovery ---

def _effects(root, project=PROJECT):
    """Every durable effect a refused transition must not have: registry, journal and the project's tree."""
    journal = root / 'contract' / 'talk.jsonl'
    return ((root / 'registry_projects.json').read_bytes(), journal.read_bytes() if journal.is_file() else b'',
            _tree(root / 'writing_projects' / project))


def _token(project, revision, kind='project-lifecycle'):
    return list(identity_doors.identities((kind, project, revision)).values())


def _repeat(root, project=PROJECT):
    return _start(root, {'operation': 'start_authoring', 'expected_project_lifecycle': _metadata(root, project)['authoring_lifecycle']['revision']}, project)


def _receipts(root):
    return [row for row in (json.loads(line) for line in (root / 'contract' / 'talk.jsonl').read_text().splitlines())
            if row.get('record') == 'project-planning-declared']


def test_a_canonical_token_alone_legacy_alone_or_both_coherent_reach_the_same_owner(tmp_path):
    from laplace.web import project_work_surface
    for name in ('canonical', 'legacy', 'both', 'viahttp'):
        _general(tmp_path, name)
    forms = {'canonical': lambda revision: {'expected': _token('canonical', revision)},
             'legacy': lambda revision: {'expected_project_lifecycle': revision},
             'both': lambda revision: {'expected_project_lifecycle': revision, 'expected': _token('both', revision)}}
    for name, form in forms.items():
        revision = _metadata(tmp_path, name)['authoring_lifecycle']['revision']
        started = _start(tmp_path, {'operation': 'start_authoring', **form(revision)}, project=name)
        assert started['status'] == 'STARTED' and started['lifecycle']['state'] == 'PLAN_OWNED', name
    revision = _metadata(tmp_path, 'viahttp')['authoring_lifecycle']['revision']
    request = json.dumps({'project': 'viahttp', 'operation': 'start_authoring', 'expected': _token('viahttp', revision)}).encode()
    status, _, body = project_work_surface.handle('/work/structure/change', {}, 'POST', request, tmp_path)
    assert status == 200 and json.loads(body)['lifecycle']['state'] == 'PLAN_OWNED'


def test_stale_wrong_home_or_incoherent_canonical_tokens_refuse_with_no_effect(tmp_path):
    from laplace.manuscript import project_structure
    from laplace.native import declarations as writing_declarations
    _general(tmp_path)
    stale = _metadata(tmp_path)['authoring_lifecycle']['revision']
    meta = _metadata(tmp_path)
    writing_tools.execute(tmp_path, PROJECT, 'work', 'project_metadata_change', {'title': 'Renamed', 'expected_revision': meta['revision']})
    current = _metadata(tmp_path)
    revision = current['authoring_lifecycle']['revision']
    effects = _effects(tmp_path)
    for payload in ({'expected': _token(PROJECT, stale)},                                      # stale
                    {'expected': _token(PROJECT, current['revision'], 'project-metadata')},    # another home of the project
                    {'expected': _token('other', revision)},                                   # another project's scope
                    {'expected_project_lifecycle': revision, 'expected': _token(PROJECT, stale)}):  # incoherent pair
        with pytest.raises((identity_doors.IdentityRefused, writing_declarations.PayloadAdmissionError)):   # door or owner
            _start(tmp_path, {'operation': 'start_authoring', **payload})
        with pytest.raises(identity_doors.IdentityRefused):                                                  # the owner alone
            project_structure.change(PROJECT, {'operation': 'start_authoring', **payload}, tmp_path)
        assert _effects(tmp_path) == effects, payload
    assert _metadata(tmp_path)['authoring_lifecycle']['state'] == 'NO_MANUSCRIPT'


def test_a_malformed_canonical_presence_is_refused_before_any_read(tmp_path, monkeypatch):
    from laplace.manuscript import project_structure
    _general(tmp_path)
    effects = _effects(tmp_path)
    def no_read(*args, **kwargs):
        pytest.fail('a malformed canonical guard reached a read')
    monkeypatch.setattr(lifecycle, 'observe', no_read)
    monkeypatch.setattr(registry, 'resolve', no_read)
    for expected in ('sha256:' + 'a' * 64, ['not-a-token'], [7]):
        with pytest.raises(identity_doors.IdentityRefused):
            project_structure.change(PROJECT, {'operation': 'start_authoring', 'expected': expected}, tmp_path)
    monkeypatch.undo()
    assert _effects(tmp_path) == effects


VALID_PLANNING = {'owner': 'project_structure', 'plan_path': 'writing_projects/dd/manuscript/projection_plan.json',
                  'declared': 'PLAN-OWN-' + '0' * 32, 'selection_identity': 'sha256:' + '0' * 64, 'by': 'author',
                  'publication': 'PUBLISHED', 'journal_offset': 0,
                  'journal_anchor': {'file': '1:2', 'cut_sha256': 'sha256:' + hashlib.sha256(b'').hexdigest(), 'cut_bytes': 0}}


def _set_row(root, change, project=PROJECT):
    """A synthetic fixture edit of the disposable registry row (never a real registry)."""
    path = root / 'registry_projects.json'
    data = json.loads(path.read_text())
    change(next(row for row in data['projects'] if row['name'] == project))
    path.write_text(json.dumps(data, indent=2) + '\n')


@pytest.mark.parametrize('case,planning,said', [
    ('wrong owner and path', {'owner': 'unrelated', 'plan_path': 'elsewhere/projection_plan.json'}, 'fields are not exactly'),
    ('wrong owner', {**VALID_PLANNING, 'owner': 'unrelated'}, 'another owner'),
    ('wrong path', {**VALID_PLANNING, 'plan_path': 'elsewhere/projection_plan.json'}, 'another plan path'),
    ('malformed value', 'yes', 'not an object'),
    ('malformed field', {**VALID_PLANNING, 'journal_offset': -1}, 'journal offset'),
    ('missing identity', {key: value for key, value in VALID_PLANNING.items() if key != 'declared'}, 'fields are not exactly'),
    ('invalid identity', {**VALID_PLANNING, 'declared': 'PLAN-OWN-x'}, 'declaration identity'),
])
def test_a_planning_declaration_this_owner_did_not_make_is_refused_never_reused_or_overwritten(tmp_path, case, planning, said):
    _general(tmp_path)
    status, draft = wp._start_manuscript_unplanned({'project': PROJECT, 'title': 'Briefing', 'kind': 'paper'}, tmp_path)
    assert status == 201, draft
    _set_row(tmp_path, lambda row: row['manifest'].__setitem__('planning', planning))
    observed = _metadata(tmp_path)['authoring_lifecycle']
    assert observed['state'] == 'REFUSED' and said in observed['reason'] and observed['next_action'] is None, case
    assert _metadata(tmp_path)['capabilities']['start_planning'] is False, 'Home offers no action the owner refuses'
    assert registry.resolve(PROJECT, tmp_path).plan_path == '', 'the registry never honours it'
    effects = _effects(tmp_path)
    with pytest.raises(lifecycle.LifecycleRefused, match='neither reused nor overwritten'):
        _start(tmp_path, {'operation': 'start_authoring', 'expected_project_lifecycle': observed['revision']})
    assert _effects(tmp_path) == effects and _row(tmp_path)['manifest']['planning'] == planning


def test_a_manuscript_home_that_resolves_outside_the_checkout_is_refused(tmp_path):
    root, outside = tmp_path / 'checkout', tmp_path / 'outside'
    root.mkdir()
    _general(root)
    status, draft = wp._start_manuscript_unplanned({'project': PROJECT, 'title': 'Briefing', 'kind': 'paper'}, root)
    assert status == 201, draft
    home = root / 'writing_projects' / PROJECT / 'manuscript'
    home.rename(home.with_name('manuscript-moved'))
    outside.mkdir()
    (outside / 'main.tex').write_text('\\documentclass{article}\n\\begin{document}\nSubstantive outside text.\n\\end{document}\n')
    home.symlink_to(outside, target_is_directory=True)
    observed = _metadata(root)['authoring_lifecycle']
    assert observed['state'] == 'REFUSED' and 'resolves outside' in observed['reason'] and observed['next_action'] is None
    effects, outside_tree = _effects(root), _tree(outside)
    with pytest.raises(lifecycle.LifecycleRefused, match='resolves outside'):
        _start(root, {'operation': 'start_authoring', 'expected_project_lifecycle': observed['revision']})
    assert _effects(root) == effects and _tree(outside) == outside_tree and 'planning' not in _row(root)['manifest']


def test_a_read_only_manuscript_is_refused_with_no_effect(tmp_path):
    _general(tmp_path)
    status, draft = wp._start_manuscript_unplanned({'project': PROJECT, 'title': 'Briefing', 'kind': 'paper'}, tmp_path)
    assert status == 201, draft
    _set_row(tmp_path, lambda row: row['manifest'].setdefault('document', {}).__setitem__('read_only', True))
    observed = _metadata(tmp_path)['authoring_lifecycle']
    assert observed['state'] == 'REFUSED' and 'read-only' in observed['reason']
    effects = _effects(tmp_path)
    with pytest.raises(lifecycle.LifecycleRefused, match='read-only'):
        _start(tmp_path, {'operation': 'start_authoring', 'expected_project_lifecycle': observed['revision']})
    assert _effects(tmp_path) == effects


def _fail_receipt(monkeypatch, *, land):
    """The declaration receipt append fails; with ``land`` the row reaches the journal before the failure."""
    original = writing_records.bank
    def append(root, row):
        if row.get('record') != 'project-planning-declared':
            return original(root, row)
        if land:
            original(root, row)
        raise OSError('controlled receipt failure')
    monkeypatch.setattr(writing_records, 'bank', append)
    return original


@pytest.mark.parametrize('land', [False, True], ids=['before-the-row-lands', 'after-the-row-lands'])
def test_a_failed_receipt_append_is_pending_and_recovered_exactly_once(tmp_path, monkeypatch, land):
    _general(tmp_path)
    original = _fail_receipt(monkeypatch, land=land)
    with pytest.raises(OSError, match='controlled receipt failure'):
        _start(tmp_path)
    monkeypatch.setattr(writing_records, 'bank', original)
    pending = _metadata(tmp_path)['authoring_lifecycle']
    declared = _row(tmp_path)['manifest']['planning']
    assert pending['state'] == 'PLAN_PUBLICATION_PENDING' and declared['publication'] == 'PENDING'
    assert _metadata(tmp_path)['capabilities']['start_planning'] is True, 'Home offers the completion'
    assert registry.resolve(PROJECT, tmp_path).plan_path == '', 'an unpublished declaration is not ownership'
    assert len(_receipts(tmp_path)) == int(land)
    recovered = _start(tmp_path)
    assert recovered['status'] == 'PUBLISHED' and recovered['manuscript_started'] is None and recovered['lifecycle']['state'] == 'PLAN_OWNED'
    receipts = _receipts(tmp_path)
    assert len(receipts) == 1 and receipts[0]['id'] == declared['declared'] == recovered['receipt_id']
    assert {key: receipts[0][key] for key in ('selection_identity', 'by', 'plan_path')} == {
        key: declared[key] for key in ('selection_identity', 'by', 'plan_path')}, 'the original attribution'
    assert _row(tmp_path)['manifest']['planning'] == {**declared, 'publication': 'PUBLISHED'}
    again = _repeat(tmp_path)
    assert again['status'] == 'ALREADY_OWNED' and len(_receipts(tmp_path)) == 1
    assert len(list((tmp_path / 'writing_projects' / PROJECT / 'manuscript').glob('working-draft*'))) == 1


def test_a_failed_publication_mark_is_recovered_without_a_second_receipt(tmp_path, monkeypatch):
    _general(tmp_path)
    original, calls = lifecycle._set_planning, []
    def second_fails(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise OSError('controlled publication-mark failure')
        return original(*args, **kwargs)
    monkeypatch.setattr(lifecycle, '_set_planning', second_fails)
    with pytest.raises(OSError, match='publication-mark'):
        _start(tmp_path)
    monkeypatch.setattr(lifecycle, '_set_planning', original)
    assert _metadata(tmp_path)['authoring_lifecycle']['state'] == 'PLAN_PUBLICATION_PENDING' and len(_receipts(tmp_path)) == 1
    recovered = _start(tmp_path)
    assert recovered['status'] == 'PUBLISHED' and len(_receipts(tmp_path)) == 1
    assert _repeat(tmp_path)['status'] == 'ALREADY_OWNED' and len(_receipts(tmp_path)) == 1


def test_a_pending_declaration_whose_journal_was_replaced_is_refused(tmp_path, monkeypatch):
    _general(tmp_path)
    original = _fail_receipt(monkeypatch, land=False)
    with pytest.raises(OSError):
        _start(tmp_path)
    monkeypatch.setattr(writing_records, 'bank', original)
    (tmp_path / 'contract' / 'talk.jsonl').write_text('')
    observed = _metadata(tmp_path)['authoring_lifecycle']
    assert observed['state'] == 'REFUSED' and 'journal is shorter' in observed['reason']
    effects = _effects(tmp_path)
    with pytest.raises(lifecycle.LifecycleRefused):
        _start(tmp_path, {'operation': 'start_authoring', 'expected_project_lifecycle': observed['revision']})
    assert _effects(tmp_path) == effects


def test_success_is_reported_only_when_the_after_state_owns_the_plan(tmp_path, monkeypatch):
    _general(tmp_path)
    original = lifecycle._set_planning
    def mark_lost(project, root, change):
        current = _row(root, project)['manifest'].get('planning')
        if current is not None:                       # the publication mark silently does not land
            return dict(current)
        return original(project, root, change)
    monkeypatch.setattr(lifecycle, '_set_planning', mark_lost)
    with pytest.raises(lifecycle.LifecycleRefused, match='did not result in plan ownership') as refused:
        _start(tmp_path)
    assert refused.value.lifecycle['state'] == 'PLAN_PUBLICATION_PENDING'
    monkeypatch.setattr(lifecycle, '_set_planning', original)
    assert _start(tmp_path)['status'] == 'PUBLISHED' and len(_receipts(tmp_path)) == 1


def test_a_declaration_that_appears_concurrently_is_not_overwritten(tmp_path, monkeypatch):
    _general(tmp_path)
    original, foreign = lifecycle._set_planning, {**VALID_PLANNING, 'owner': 'unrelated'}
    def interleaved(project, root, change):           # another writer lands just before the declaration's write
        _set_row(root, lambda row: row['manifest'].__setitem__('planning', foreign), project)
        return original(project, root, change)
    monkeypatch.setattr(lifecycle, '_set_planning', interleaved)
    payload = _metadata(tmp_path)['authoring_lifecycle']['next_action']['payload']
    with pytest.raises(ValueError, match='appeared concurrently'):
        _start(tmp_path, payload)
    assert _row(tmp_path)['manifest']['planning'] == foreign and _receipts(tmp_path) == []


# --- repair2 (2026-10-15): PB-R2-R1 total declaration validation, PB-R3-R1 exact bounded receipt proof ---

_JSON_WRONG = [[], {}, None, True, 1, 1.5, '']
_ANCHOR = VALID_PLANNING['journal_anchor']
_MALFORMED = [(field, value) for field in sorted(registry.PLANNING_FIELDS - {'journal_offset', 'journal_anchor'}) for value in _JSON_WRONG] + [
    ('journal_offset', value) for value in ([], {}, None, True, False, '0', 1.5, -1)] + [
    ('journal_anchor', value) for value in ([], None, True, 1, 'x', {}, {**_ANCHOR, 'extra': 1}, {key: _ANCHOR[key] for key in ('file', 'cut_bytes')},
                                            {**_ANCHOR, 'file': 1}, {**_ANCHOR, 'file': 'x:y'}, {**_ANCHOR, 'file': []}, {**_ANCHOR, 'cut_sha256': 'sha256:x'},
                                            {**_ANCHOR, 'cut_sha256': {}}, {**_ANCHOR, 'cut_bytes': 5}, {**_ANCHOR, 'cut_bytes': False},
                                            {**_ANCHOR, 'cut_bytes': '0'}, {**_ANCHOR, 'cut_bytes': []})]


@pytest.mark.parametrize('field,value', _MALFORMED, ids=[f'{field}={value!r}' for field, value in _MALFORMED])
def test_every_malformed_json_field_is_refused_and_the_project_stays_readable(tmp_path, field, value):
    _general(tmp_path)
    _set_row(tmp_path, lambda row: row['manifest'].__setitem__('planning', {**VALID_PLANNING, field: value}))
    problem = registry.planning_declaration_problem({**VALID_PLANNING, field: value}, 'writing_projects/dd/manuscript')
    assert isinstance(problem, str) and problem
    record = registry.resolve(PROJECT, tmp_path)
    assert record is not None and record.kind == 'project' and record.plan_path == '', 'readable, never honoured, never dropped'
    metadata = _metadata(tmp_path)
    observed = metadata['authoring_lifecycle']
    assert observed['state'] == 'REFUSED' and problem in observed['reason'] and observed['next_action'] is None
    assert metadata['capabilities']['start_planning'] is False and metadata['capabilities']['reader_plan'] is False
    effects = _effects(tmp_path)
    with pytest.raises(lifecycle.LifecycleRefused, match='neither reused nor overwritten'):
        _start(tmp_path, {'operation': 'start_authoring', 'expected_project_lifecycle': observed['revision']})
    assert _effects(tmp_path) == effects


def _pending(tmp_path, monkeypatch):
    """A synthetic project whose declaration is committed PENDING with no receipt (the append failed before landing)."""
    _general(tmp_path)
    original = _fail_receipt(monkeypatch, land=False)
    with pytest.raises(OSError):
        _start(tmp_path)
    monkeypatch.setattr(writing_records, 'bank', original)
    planning = _row(tmp_path)['manifest']['planning']
    assert planning['publication'] == 'PENDING' and _receipts(tmp_path) == []
    return planning


def _exact(planning):
    return {'record': 'project-planning-declared', 'id': planning['declared'], 'project': PROJECT, 'plan_path': planning['plan_path'],
            'selection_identity': planning['selection_identity'], 'by': planning['by']}


def _append(root, raw: bytes):
    with (root / 'contract' / 'talk.jsonl').open('ab') as stream:
        stream.write(raw)


def _owner_start(root):
    """The owner itself (as the native door calls it), without the tool door's own read/action journal rows, so a
    journal fixture is exactly what the owner sees."""
    revision = lifecycle.observe(PROJECT, root)['revision']
    return lifecycle.start_authoring(PROJECT, {'operation': 'start_authoring', 'expected_project_lifecycle': revision}, root,
                                     actor={'kind': 'agent'})


def _refused_without_effect(root, said):
    """The adverse outcome every unproved receipt must have: REFUSED, no action, no false ownership, no write."""
    metadata = wp.metadata(PROJECT, root)                 # the owner read; it banks no journal row
    observed = metadata['authoring_lifecycle']
    assert observed['state'] == 'REFUSED' and said in observed['reason'] and 'stays PENDING' in observed['reason']
    assert observed['next_action'] is None and metadata['capabilities']['start_planning'] is False
    effects = _effects(root)
    with pytest.raises(lifecycle.LifecycleRefused, match=said):
        _owner_start(root)
    assert _effects(root) == effects, 'nothing appended, published or rewritten'
    assert registry.resolve(PROJECT, root).plan_path == '' and _row(root)['manifest']['planning']['publication'] == 'PENDING'


def test_a_torn_journal_tail_is_never_appended_onto_and_recovers_once_the_row_completes(tmp_path, monkeypatch):
    planning = _pending(tmp_path, monkeypatch)
    _append(tmp_path, b'{"record":"partial"')
    _refused_without_effect(tmp_path, 'incomplete row')
    _append(tmp_path, b'}\n')                      # the in-flight row completes: the proof is now ABSENT and clean
    recovered = _owner_start(tmp_path)
    assert recovered['status'] == 'PUBLISHED' and [row['id'] for row in _receipts(tmp_path)] == [planning['declared']]
    lines = (tmp_path / 'contract' / 'talk.jsonl').read_text().splitlines()
    assert '{"record":"partial"}' in lines and all(json.loads(line) for line in lines), 'every journal line is whole'


def test_a_torn_tail_before_a_fresh_declaration_refuses_before_any_declaration(tmp_path):
    _general(tmp_path)
    status, draft = wp._start_manuscript_unplanned({'project': PROJECT, 'title': 'Briefing', 'kind': 'paper'}, tmp_path)
    assert status == 201, draft
    _append(tmp_path, b'{"record":"partial"')
    effects = _effects(tmp_path)
    with pytest.raises(lifecycle.LifecycleRefused, match='incomplete row'):
        _owner_start(tmp_path)
    assert _effects(tmp_path) == effects and 'planning' not in _row(tmp_path)['manifest']


def test_a_malformed_row_naming_the_declaration_is_unproved(tmp_path, monkeypatch):
    planning = _pending(tmp_path, monkeypatch)
    _append(tmp_path, ('{"id": "%s", "record": "project-planning-declared", broken\n' % planning['declared']).encode())
    _refused_without_effect(tmp_path, 'not readable JSON')


@pytest.mark.parametrize('field,value', [('project', 'another-project'), ('selection_identity', 'sha256:' + 'f' * 64),
    ('plan_path', 'elsewhere/projection_plan.json'), ('by', 'author'), ('record', 'project-planning-other')])
def test_a_same_identity_row_with_other_content_is_unproved_not_reused(tmp_path, monkeypatch, field, value):
    planning = _pending(tmp_path, monkeypatch)
    assert planning['by'] == 'agent', 'the tool door attributes to the agent, so by=author is a wrong actor'
    _append(tmp_path, (json.dumps({**_exact(planning), field: value}) + '\n').encode())
    _refused_without_effect(tmp_path, 'other content')


def test_duplicate_receipts_of_one_declaration_are_unproved(tmp_path, monkeypatch):
    planning = _pending(tmp_path, monkeypatch)
    _append(tmp_path, ((json.dumps(_exact(planning)) + '\n') * 2).encode())
    _refused_without_effect(tmp_path, 'appears on 2 journal rows')


def test_one_exact_complete_receipt_is_published_without_a_second_append(tmp_path, monkeypatch):
    planning = _pending(tmp_path, monkeypatch)
    _append(tmp_path, (json.dumps({**_exact(planning), 'ts': 'landed-by-the-failed-call'}) + '\n').encode())
    journal = (tmp_path / 'contract' / 'talk.jsonl').read_bytes()
    recovered = _owner_start(tmp_path)
    assert recovered['status'] == 'PUBLISHED' and recovered['lifecycle']['state'] == 'PLAN_OWNED'
    assert (tmp_path / 'contract' / 'talk.jsonl').read_bytes() == journal, 'the landed receipt is the one receipt'


def test_an_offset_that_is_not_a_row_start_is_unproved(tmp_path, monkeypatch):
    planning = _pending(tmp_path, monkeypatch)
    moved = planning['journal_offset'] - 3              # a self-consistent anchor at the moved cut, so only the row start fails
    _set_row(tmp_path, lambda row: row['manifest']['planning'].update(journal_offset=moved, journal_anchor=lifecycle._cut_anchor(tmp_path, moved)[0]))
    _refused_without_effect(tmp_path, 'not the start of a row')


_IN_FLIGHT = {   # what another writer leaves after the receipt this owner appends, and how that writer finishes it
    'escaped same id, other project': ('{"record":"project-planning-declared","id":"\\u0050LAN-OWN-%(hex)s","project":"another-project"', '}\n', 'other content'),
    'partial id prefix of the same id': ('{"record":"other","id":"PLAN-OW', 'N-%(hex)s"}\n', 'other content'),
    'id field not yet present': ('{"record":"other"', ',"id":"ROW-1"}\n', None),
    'known different complete id': ('{"id":"ROW-2","record":"other"', '}\n', None),
    'full literal same id, other project': ('{"record":"project-planning-declared","id":"%(id)s","project":"another-project"', '}\n', 'other content'),
}


@pytest.mark.parametrize('case', sorted(_IN_FLIGHT))
def test_an_unfinished_row_after_the_receipt_keeps_publication_pending_until_its_writer_finishes(tmp_path, monkeypatch, case):
    planning = _pending(tmp_path, monkeypatch)
    names = {'id': planning['declared'], 'hex': planning['declared'][len('PLAN-OWN-'):]}
    fragment, rest, said = (part % names if part else part for part in _IN_FLIGHT[case])
    original = writing_records.bank
    def append_then_other_writer(root, row):
        banked = original(root, row)
        if row.get('record') == 'project-planning-declared':
            _append(root, fragment.encode())
        return banked
    monkeypatch.setattr(writing_records, 'bank', append_then_other_writer)
    with pytest.raises(lifecycle.LifecycleRefused, match='incomplete row'):
        _owner_start(tmp_path)                    # never waived by what the unfinished bytes appear to say
    monkeypatch.setattr(writing_records, 'bank', original)
    assert registry.resolve(PROJECT, tmp_path).plan_path == '' and _row(tmp_path)['manifest']['planning']['publication'] == 'PENDING'
    _refused_without_effect(tmp_path, 'incomplete row')
    _append(tmp_path, rest.encode())              # the other writer finishes its row
    rows = [json.loads(line) for line in (tmp_path / 'contract' / 'talk.jsonl').read_text().splitlines()]
    same = [row for row in rows if row.get('id') == planning['declared']]
    if said:                                      # its decoded identity is the declaration's: never published, never duplicated
        assert len(same) == 2
        _refused_without_effect(tmp_path, said)
    else:
        assert len(same) == 1 and _owner_start(tmp_path)['status'] == 'PUBLISHED'
        assert [row['id'] for row in _receipts(tmp_path)] == [planning['declared']]


@pytest.mark.parametrize('case', ['a whole unrelated row', 'a whole exact duplicate'])
def test_a_whole_row_after_the_receipt_is_judged_by_its_decoded_identity(tmp_path, monkeypatch, case):
    planning = _pending(tmp_path, monkeypatch)
    whole = {'record': 'other', 'id': 'ROW-3'} if case == 'a whole unrelated row' else _exact(planning)
    original = writing_records.bank
    def append_then_other_writer(root, row):
        banked = original(root, row)
        if row.get('record') == 'project-planning-declared':
            _append(root, (json.dumps(whole) + '\n').encode())
        return banked
    monkeypatch.setattr(writing_records, 'bank', append_then_other_writer)
    if case == 'a whole unrelated row':
        assert _owner_start(tmp_path)['status'] == 'PUBLISHED' and len(_receipts(tmp_path)) == 1
    else:
        with pytest.raises(lifecycle.LifecycleRefused, match='appears on 2 journal rows'):
            _owner_start(tmp_path)
        assert registry.resolve(PROJECT, tmp_path).plan_path == ''


class _Counted:
    """Counts what the proof actually reads from the journal (bytes and readline calls)."""
    def __init__(self, stream, tally):
        self.stream, self.tally = stream, tally
    def __enter__(self):
        return self
    def __exit__(self, *exc):
        self.stream.close()
    def seek(self, *args):
        return self.stream.seek(*args)
    def read(self, *args):
        data = self.stream.read(*args); self.tally['bytes'] += len(data); return data
    def readline(self, *args):
        data = self.stream.readline(*args); self.tally['bytes'] += len(data); self.tally['rows'] += 1; return data


def _counted_proof(root, planning, monkeypatch):
    tally, real = {'bytes': 0, 'rows': 0}, Path.open
    monkeypatch.setattr(Path, 'open', lambda self, *a, **k: _Counted(real(self, *a, **k), tally) if self.name == 'talk.jsonl' else real(self, *a, **k))
    try:
        return lifecycle._receipt_proof(PROJECT, root, planning), tally
    finally:
        monkeypatch.setattr(Path, 'open', real)


def test_the_receipt_proof_is_hard_bounded_in_bytes_rows_and_line_length(tmp_path, monkeypatch):
    planning = _pending(tmp_path, monkeypatch)
    unrelated = b''.join((json.dumps({'record': 'unrelated', 'id': 'ROW-%03d' % n, 'body': 'x' * 500}) + '\n').encode() for n in range(256))
    _append(tmp_path, unrelated)
    assert lifecycle.PROOF_BYTES == 4 << 20 and lifecycle.PROOF_ROWS == 10_000 and lifecycle.PROOF_LINE == 1 << 20
    (proof, _), tally = _counted_proof(tmp_path, planning, monkeypatch)
    window = planning['journal_anchor']['cut_bytes']
    assert proof == 'ABSENT' and tally['bytes'] == window + len(unrelated) + 1, 'the anchor window, the row-start byte and the suffix only'
    monkeypatch.setattr(lifecycle, 'PROOF_BYTES', len(unrelated) - 1)
    (proof, why), tally = _counted_proof(tmp_path, planning, monkeypatch)
    assert proof == 'UNPROVED' and 'bytes were appended' in why and tally == {'bytes': 0, 'rows': 0}, 'refused before reading'
    monkeypatch.setattr(lifecycle, 'PROOF_BYTES', 4 << 20)
    monkeypatch.setattr(lifecycle, 'PROOF_ROWS', 16)
    (proof, why), tally = _counted_proof(tmp_path, planning, monkeypatch)
    assert proof == 'UNPROVED' and 'rows were appended' in why and tally['rows'] == 17 and tally['bytes'] < window + len(unrelated)
    monkeypatch.setattr(lifecycle, 'PROOF_ROWS', 10_000)
    monkeypatch.setattr(lifecycle, 'PROOF_LINE', 128)
    (proof, why), tally = _counted_proof(tmp_path, planning, monkeypatch)
    assert proof == 'UNPROVED' and 'longer than 128 bytes' in why and tally['bytes'] == window + 1 + 129, 'one bounded read, no retained line'
    monkeypatch.setattr(lifecycle, 'PROOF_LINE', 1 << 20)
    monkeypatch.setattr(lifecycle, 'PROOF_ROWS', 16)
    _refused_without_effect(tmp_path, 'rows were appended')


def test_through_the_native_door_a_torn_tail_merged_by_the_doors_own_journal_row_stays_unproved(tmp_path, monkeypatch):
    # the tool door banks its own read/action rows through the shared append seam, which does not check the tail:
    # the fragment becomes one complete malformed line. The owner reports that truthfully; it never publishes.
    _pending(tmp_path, monkeypatch)
    _append(tmp_path, b'{"record":"partial"')
    first = _metadata(tmp_path)['authoring_lifecycle']           # the door banks its read row after this owner read
    assert first['state'] == 'REFUSED' and 'incomplete row' in first['reason'] and first['next_action'] is None
    observed = _metadata(tmp_path)['authoring_lifecycle']        # ...so the fragment is now one complete malformed line
    assert observed['state'] == 'REFUSED' and 'not readable JSON' in observed['reason'] and observed['next_action'] is None
    with pytest.raises(lifecycle.LifecycleRefused, match='not readable JSON'):
        _start(tmp_path, {'operation': 'start_authoring', 'expected_project_lifecycle': observed['revision']})
    assert registry.resolve(PROJECT, tmp_path).plan_path == '' and _row(tmp_path)['manifest']['planning']['publication'] == 'PENDING'
    assert not any('project-planning-declared' in line for line in (tmp_path / 'contract' / 'talk.jsonl').read_text().splitlines())


def test_a_receipt_append_that_silently_does_not_land_is_never_published(tmp_path, monkeypatch):
    planning = _pending(tmp_path, monkeypatch)
    original = writing_records.bank
    monkeypatch.setattr(writing_records, 'bank', lambda root, row: None if row.get('record') == 'project-planning-declared' else original(root, row))
    with pytest.raises(lifecycle.LifecycleRefused, match='appended receipt is not in the journal'):
        _owner_start(tmp_path)
    assert registry.resolve(PROJECT, tmp_path).plan_path == '' and _row(tmp_path)['manifest']['planning'] == planning
    monkeypatch.setattr(writing_records, 'bank', original)
    assert _owner_start(tmp_path)['status'] == 'PUBLISHED' and len(_receipts(tmp_path)) == 1


# --- repair3 (2026-10-15): PB-R3-R2B bounded original file-and-cut continuity ---

def _replace_journal(root, raw: bytes):
    """An ordinary atomic replacement: a new file renamed over contract/talk.jsonl."""
    journal = root / 'contract' / 'talk.jsonl'
    staged = journal.with_name('talk.jsonl.new')
    staged.write_bytes(raw)
    staged.replace(journal)


def test_an_atomic_same_length_replacement_is_never_republished(tmp_path, monkeypatch):
    planning = _pending(tmp_path, monkeypatch)
    offset = planning['journal_offset']
    row = b'{"record":"unrelated","pad":"'
    raw = row + b'x' * (offset - len(row) - 3) + b'"}\n'   # Sol's shape: one whole unrelated row, its newline at the offset
    assert len(raw) == offset and raw.endswith(b'\n')
    _replace_journal(tmp_path, raw + (tmp_path / 'contract' / 'talk.jsonl').read_bytes()[offset:])
    assert (tmp_path / 'contract' / 'talk.jsonl').stat().st_size >= offset
    _refused_without_effect(tmp_path, 'not the file the declaration was cut from')


@pytest.mark.parametrize('shape', ['identical copy plus appends', 'larger unrelated'])
def test_an_atomic_larger_replacement_is_never_republished(tmp_path, monkeypatch, shape):
    planning = _pending(tmp_path, monkeypatch)
    current = (tmp_path / 'contract' / 'talk.jsonl').read_bytes()
    extra = b'{"record":"unrelated","id":"ROW-9"}\n'
    raw = current + extra if shape == 'identical copy plus appends' else b'{"record":"unrelated"}\n' * (len(current) // 10 + 5)
    _replace_journal(tmp_path, raw)
    if shape == 'identical copy plus appends':
        assert lifecycle._cut_anchor(tmp_path, planning['journal_offset'])[0]['cut_sha256'] == planning['journal_anchor']['cut_sha256']
    _refused_without_effect(tmp_path, 'not the file the declaration was cut from')


def test_an_in_place_rewrite_inside_the_anchor_window_is_never_republished(tmp_path, monkeypatch):
    planning = _pending(tmp_path, monkeypatch)
    journal = tmp_path / 'contract' / 'talk.jsonl'
    with journal.open('r+b') as stream:                    # same file, same length, one changed byte before the cut
        stream.seek(planning['journal_offset'] - 5)
        byte = stream.read(1)
        stream.seek(planning['journal_offset'] - 5)
        stream.write(b'Z' if byte != b'Z' else b'Y')
    _refused_without_effect(tmp_path, "bytes before the declaration's cut changed")


def test_the_original_journal_with_ordinary_appends_stays_recoverable(tmp_path, monkeypatch):
    planning = _pending(tmp_path, monkeypatch)
    for n in range(3):                                     # other owners keep appending to the same file
        writing_records.bank(tmp_path, {'record': 'unrelated-ordinary-row', 'id': 'ROW-%d' % n})
    _metadata(tmp_path)                                    # and the tool door banks its own rows
    assert lifecycle._receipt_proof(PROJECT, tmp_path, planning) == ('ABSENT', None)
    assert _owner_start(tmp_path)['status'] == 'PUBLISHED' and [row['id'] for row in _receipts(tmp_path)] == [planning['declared']]


@pytest.mark.parametrize('land', [False, True], ids=['before-the-row-lands', 'after-the-row-lands'])
def test_a_declaration_cut_where_no_journal_existed_never_re_appends_automatically(tmp_path, monkeypatch, land):
    _general(tmp_path)
    status, draft = wp._start_manuscript_unplanned({'project': PROJECT, 'title': 'Briefing', 'kind': 'paper'}, tmp_path)
    assert status == 201, draft
    (tmp_path / 'contract' / 'talk.jsonl').unlink()       # synthetic: the declaration is cut before any journal exists
    original = _fail_receipt(monkeypatch, land=land)
    with pytest.raises(OSError):
        _owner_start(tmp_path)
    monkeypatch.setattr(writing_records, 'bank', original)
    planning = _row(tmp_path)['manifest']['planning']
    assert planning['journal_offset'] == 0 and planning['journal_anchor']['file'] == '' and planning['publication'] == 'PENDING'
    if land:                                               # the one exact receipt exists: it is published, not re-appended
        journal = (tmp_path / 'contract' / 'talk.jsonl').read_bytes()
        assert _owner_start(tmp_path)['status'] == 'PUBLISHED' and (tmp_path / 'contract' / 'talk.jsonl').read_bytes() == journal
    else:
        _refused_without_effect(tmp_path, 'continuity cannot be established')


def test_a_fresh_declaration_with_no_journal_yet_publishes_in_its_own_call(tmp_path):
    _general(tmp_path)
    status, draft = wp._start_manuscript_unplanned({'project': PROJECT, 'title': 'Briefing', 'kind': 'paper'}, tmp_path)
    assert status == 201, draft
    (tmp_path / 'contract' / 'talk.jsonl').unlink()
    started = _owner_start(tmp_path)
    assert started['status'] == 'PLAN_OWNED' and started['planning']['journal_anchor']['file'] == ''
    assert [row['id'] for row in _receipts(tmp_path)] == [started['receipt_id']]


def test_an_anchor_that_claims_no_journal_for_a_later_cut_is_refused(tmp_path):
    _general(tmp_path)
    claimed = {**VALID_PLANNING, 'journal_offset': 10, 'journal_anchor': {**_ANCHOR, 'file': '', 'cut_bytes': 10}}
    problem = registry.planning_declaration_problem(claimed, 'writing_projects/dd/manuscript')
    assert problem == "the planning declaration's journal anchor does not describe its own cut"
    _set_row(tmp_path, lambda row: row['manifest'].__setitem__('planning', claimed))
    observed = wp.metadata(PROJECT, tmp_path)['authoring_lifecycle']
    assert observed['state'] == 'REFUSED' and problem in observed['reason'] and registry.resolve(PROJECT, tmp_path).plan_path == ''
