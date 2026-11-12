"""Faithful reimport of one synthetic project (Work5, 2026-10-20): the export/import boundary the exporter and the records
fold already own keeps the original Work, session, turn, reply and review rows with their ids, intent, exact bytes and
pins; the native binding is explicitly detached on import; the original source is untouched; and one interrupted
saved-source application is replayed in the reimported workspace through the existing owner semantics.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest

from laplace.manuscript import manuscript_source, proposal_preflight
from laplace.work import project_work, project_work_review
from laplace.projects import library as writing_projects
from laplace.pipeline import authoring
from laplace.writing import records
from laplace.manuscript import source_application, source_effects, proposal_currentness
from laplace.writing.records import _bank

SCRIPTS = Path(__file__).parents[1] / 'scripts'
SPEC = importlib.util.spec_from_file_location('export_writing_evaluation', SCRIPTS / 'export_writing_evaluation.py')
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)
P = 'fixture'
ORIGINAL = '\\documentclass{article}\n\\begin{document}\nOriginal prose.\n\\end{document}\n'


def _sha(raw: bytes) -> str:
    return 'sha256:' + hashlib.sha256(raw).hexdigest()


def _tree(root: Path, skip=('.laplace-state', 'state')) -> dict:
    return {str(p.relative_to(root)): _sha(p.read_bytes()) for p in root.rglob('*') if p.is_file() and not any(part in skip for part in p.relative_to(root).parts)}


def _source_root(root: Path) -> None:
    """A synthetic source checkout the exporter accepts: the release inputs it requires, a project imported through the
    project owner, a Work with review obligations, a producer handoff and an independent review, a session whose native
    binding exists, a turn and its saved proposal."""
    (root / 'contract').mkdir(parents=True)
    (root / 'pyproject.toml').write_text('[project]\nname="example"\n')
    (root / 'src/laplace').mkdir(parents=True); (root / 'src/laplace/app.py').write_text('import json\n')
    for relative in ('docs/writing-evaluation-release.md', 'docs/writing-evaluator-readme.md', 'docs/writing-evaluator-agents.md', 'docs/writing-container.md',
                     'docs/writing-registry.md', 'deploy/writing/Dockerfile', 'deploy/writing/writing-entrypoint.sh', 'deploy/writing/smoke.py'):
        (root / relative).parent.mkdir(parents=True, exist_ok=True); (root / relative).write_text('required release input')
    src = root / 'sources' / P; src.mkdir(parents=True)
    (src / 'main.tex').write_text(ORIGINAL)
    (root / 'evidence').mkdir(); (root / 'evidence' / 'review.md').write_text('Independent review notes.\n')
    status, _ = writing_projects.import_source({'name': P, 'title': 'Fixture', 'root': 'sources/%s/main.tex' % P, 'editable': True}, root)
    assert status == 201
    # the project closure the exporter requires beside the manuscript (plan, references, research records, figure manifest, build)
    for name, value in (('projection_plan.json', {'sections': []}), ('references.json', {'sources': []}), ('research_records.json', {'records': []}), ('figure_manifest.json', {'figures': []})):
        (src / name).write_text(json.dumps(value))
    (src / 'main.pdf').write_bytes(b'fixture pdf')
    project_work.task(P, {'id': 'w-source', 'title': 'Revise the prose', 'goal': 'Replace the original prose.',
                          'review_obligations': [{'id': 'source', 'scope': 'source', 'label': 'Source review', 'inputs': ['sources/%s/main.tex' % P]}]}, root)
    for row in ({'record': 'writing-session', 'id': 'WS-orig', 'project': P, 'provider': 'codex', 'model': 'm', 'effort': 'medium'},
                {'record': 'writing-binding', 'session_id': 'WS-orig', 'native_id': 'native-conversation-7', 'model': 'm'},
                {'record': 'writing-turn', 'id': 'WT-orig', 'session_id': 'WS-orig', 'project': P, 'request_id': 'r-1', 'text': 'revise', 'mode': 'revise',
                 'provider_settings': {'provider': 'codex', 'model': 'm', 'effort': 'medium'}}):
        _bank.bank(root, row)
    handoff = project_work_review.record(P, {'id': 'w-source', 'phase': 'handoff', 'request_id': 'handoff-original', 'expected_work_revision': project_work._task_revision(project_work._tasks(P, root)['w-source']),
                                              'obligations': ['source'], 'object': {'kind': 'source', 'checkpoint': 'sources'}, 'pins': {'sources/%s/main.tex' % P: _sha(ORIGINAL.encode())}},
                                         root, door={'origin': 'native', 'turn_id': 'WT-orig'})
    project_work_review.record(P, {'id': 'w-source', 'phase': 'review', 'request_id': 'review-original', 'expected_work_revision': project_work._task_revision(project_work._tasks(P, root)['w-source']),
                                   'handoff_id': handoff['phase']['id'], 'obligation_id': 'source', 'verdict': 'ACCEPT',
                                   'actor': {'origin': 'external', 'actor': 'independent-reviewer', 'evidence': [{'path': 'evidence/review.md', 'sha256': _sha((root / 'evidence/review.md').read_bytes())}]}},
                               root, door={'origin': 'human'}, mode='review')
    # the saved proposal of the original turn: the edit the reimported workspace will apply
    source = manuscript_source.resolve(P, repo_root=root)
    context = authoring.build_context(P, {'files': ['main.tex']}, repo_root=root)
    raw = (root / source['manuscript_dir'] / 'main.tex').read_text()
    edit = {'file': 'main.tex', 'line_start': 3, 'line_end': 3, 'before': 'Original prose.', 'after': 'Revised prose.', 'source_anchor': proposal_preflight.source_anchor(raw, 3, 3)}
    turn = records.fold_records(root)['turns']['WT-orig']
    _bank.bank(root, {'record': 'writing-turn', **turn, 'selection': {'files': ['main.tex']}, 'context_id': context.get('context_id'),
                      'dependencies': context.get('dependencies'), 'document': context.get('document', source)})
    _bank.bank(root, {'record': 'writing-reply', 'id': 'WR-orig', 'turn_id': 'WT-orig', 'session_id': 'WS-orig', 'project': P, 'status': 'completed',
                      'proposal': {'answer': 'proposal', 'edits': [edit]}})


@pytest.fixture
def roots(tmp_path, monkeypatch):
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / 'state-source'))
    source = tmp_path / 'source'
    _source_root(source)
    return source, tmp_path


def test_reimport_keeps_original_ids_rows_pins_and_detaches_the_native_binding(roots, monkeypatch):
    source, tmp_path = roots
    before = _tree(source)
    original_rows = (source / 'contract/talk.jsonl').read_bytes()
    original_work = (source / 'corpus_friction/work_orders.jsonl').read_bytes()
    folded_before = records.fold_records(source)
    assert folded_before['sessions']['WS-orig']['native_id'] == 'native-conversation-7'
    export = tmp_path / 'export'
    report = exporter.export(source, export, P)
    assert report['imported_sessions'] == 1 and report['status'] == 'CANDIDATE_REQUIRES_CLEAN_INSTALL_ACCEPTANCE'
    assert _tree(source) == before, 'the original source is untouched by export'
    # the reimported workspace: original rows byte for byte, then the explicit import boundary; ids, text and pins unchanged
    exported_rows = (export / 'contract/talk.jsonl').read_bytes()
    assert exported_rows.startswith(original_rows)
    boundary = [json.loads(line) for line in exported_rows[len(original_rows):].decode().splitlines() if line.strip()]
    assert [row['record'] for row in boundary] == ['writing-session-import'] and boundary[0]['session_id'] == 'WS-orig'
    assert boundary[0]['source_manifest_sha256'] == report['source_manifest_sha256']
    assert (export / 'corpus_friction/work_orders.jsonl').read_bytes() == original_work
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / 'state-export'))
    folded = records.fold_records(export)
    session = folded['sessions']['WS-orig']
    assert session['native_id'] is None and session['imported_history']['source_manifest_sha256'] == report['source_manifest_sha256']
    assert session['pending_context'] == {'reason': 'imported project history'} and 'tool_contract_digest' not in session
    assert folded['turns']['WT-orig']['text'] == 'revise' and folded['turns']['WT-orig']['request_id'] == 'r-1'
    assert folded['turns']['WT-orig']['reply']['proposal']['edits'][0]['after'] == 'Revised prose.'
    task = project_work._tasks(P, export)['w-source']
    assert task['id'] == 'w-source' and project_work._task_revision(task) == project_work._task_revision(project_work._tasks(P, source)['w-source'])
    facet = project_work_review.facet(task, export)
    entry = facet['obligations'][0]
    assert entry['status'] == 'ACCEPTED' and entry['currentness'] == 'CURRENT' and entry['independence'] == 'INDEPENDENT' and entry['reviewer_verified'] is True
    assert facet['handoff']['producer'] == 'codex:m' and facet['remaining'] == []
    # the original source's manuscript is not the reimported one: edits land in the export only
    assert (export / 'sources' / P / 'main.tex').read_text() == ORIGINAL
    # one interrupted application, replayed: the first attempt is cut after the bytes moved and before the finish;
    # the retry answers the same application (same id, POSTIMAGE); the journal holds one application row
    turn = folded['turns']['WT-orig']
    from laplace.manuscript.manuscript_proposals import proposal_version
    version = proposal_version(turn)[0]
    assert proposal_currentness.proposal_view(turn)['proposal_state'] in ('ready', 'saved-without-final-reply')
    real_finish = source_effects.finish_source_changes
    cut = {'done': False}

    def cut_finish(*args, **kwargs):
        if not cut['done']:
            cut['done'] = True
            raise RuntimeError('fixture: the process died after the bytes moved and before the finish')
        return real_finish(*args, **kwargs)
    monkeypatch.setattr(source_effects, 'finish_source_changes', cut_finish)

    def apply_once():
        changes = []
        with records.proposal_write_lock(export):
            row = source_application._apply_proposal_locked(export, {'turn_id': 'WT-orig', 'project': P, 'proposal_version': version}, source_changes=changes)
        source_effects.finish_source_changes(export, P, row, changes)
        return row
    with pytest.raises(RuntimeError, match='before the finish'):
        apply_once()
    assert 'Revised prose.' in (export / 'sources' / P / 'main.tex').read_text()
    replayed = apply_once()
    assert replayed.get('reused') is True and replayed.get('complete') is True
    assert source_effects.application_source_state(export, replayed) == 'POSTIMAGE'
    turn_after = records.fold_records(export)['turns']['WT-orig']
    assert len(source_effects.applications(turn_after)) == 1 and proposal_currentness.proposal_view(turn_after)['proposal_state'] == 'applied'
    assert _tree(source) == before and (source / 'sources' / P / 'main.tex').read_text() == ORIGINAL, 'the original is still untouched after the reimported apply'
    # the reviewed obligation is now STALE in the export (its pinned input moved) and still CURRENT at the untouched original
    assert project_work_review.facet(project_work._tasks(P, export)['w-source'], export)['obligations'][0]['currentness'] == 'STALE'
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / 'state-source'))
    assert project_work_review.facet(project_work._tasks(P, source)['w-source'], source)['obligations'][0]['currentness'] == 'CURRENT'
    target = os.environ.get('LAPLACE_RECOVERY_EVIDENCE')
    if target:
        Path(target).mkdir(parents=True, exist_ok=True)
        (Path(target) / 'reimport.json').write_text(json.dumps({'imported_sessions': report['imported_sessions'], 'boundary': boundary, 'session': {k: session.get(k) for k in ('id', 'native_id', 'imported_history', 'pending_context')},
                                                                'work_revision_equal': True, 'review_after_reimport': entry, 'replay': {'reused': replayed.get('reused'), 'source_state': 'POSTIMAGE', 'applications': 1},
                                                                'original_untouched': True}, indent=1))
