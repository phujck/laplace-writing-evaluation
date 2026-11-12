"""Core consolidation, family 1: authoring state, source application and consumed-context currentness.

The family (source_application, proposal_currentness, turn_reads, turn_context, mutation_attribution) and the owners
the facade's implementations moved to (records._bank, source_effects, turn_jobs) depend one way: none of them imports
the authoring facade, the HTTP door, the provider adapter or the scanner, at module level or lazily. The facade only
forwards their names outward. A real synthetic source application runs headless in a subprocess, and Work and source
application share the same declared admission, refusal formatting, journal write and replay mechanics while their
domain guards stay local.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
from pathlib import Path

import pytest

from laplace.core import identity_doors
from laplace.work import project_work as work
from laplace.native import declarations as writing_declarations, tools as writing_tools, verbs as writing_verbs
from laplace.writing import delivery, records
from laplace.manuscript import proposal_currentness, source_effects
from laplace.writing.records import _bank as journal_bank
from test_work_repair2 import P, make, root  # noqa: F401  (root is the fixture)

SRC = Path(__file__).resolve().parents[1] / 'src' / 'laplace'
PYTHON = str(SRC.parents[1] / 'scripts' / 'laplace-python')   # the configured runtime (isolated interpreter, src on the path)
FAMILY = ['manuscript/source_application.py', 'manuscript/proposal_currentness.py', 'writing/turn_reads.py', 'writing/turn_context.py',
          'writing/mutation_attribution.py', 'writing/records/_bank.py', 'writing/records/_fold.py', 'writing/records/_index.py',
          'manuscript/source_effects.py', 'writing/turn_jobs.py', 'manuscript/manuscript_proposals.py']
DOORS = {'laplace.web.authoring', 'laplace.web.authoring_http', 'laplace.writing.provider', 'laplace.web.scanner', 'laplace.web.research_surface'}
MOVED = {'_bank': 'laplace.writing.records._bank', 'proposal_write_lock': 'laplace.writing.records._bank',
         'author_update_delivery_lock': 'laplace.writing.records._bank', 'turn_context_basis': 'laplace.writing.records._bank',
         '_applications': 'laplace.manuscript.source_effects', '_applied_edits': 'laplace.manuscript.source_effects',
         'application_source_state': 'laplace.manuscript.source_effects', 'finish_source_changes': 'laplace.manuscript.source_effects',
         'proposal_view': 'laplace.manuscript.proposal_currentness', 'applications_for_effect': 'laplace.manuscript.proposal_currentness',
         '_bank_read_baseline_groups': 'laplace.writing.turn_reads'}


def _imports(path):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ''
            for alias in node.names:
                yield (module + '.' + alias.name if module else alias.name), node.lineno
            yield module, node.lineno


# --------------------------------------------------------------------------------------------- the import boundary

def test_the_family_never_imports_a_door_or_the_facade_even_lazily():
    offences = []
    for rel in FAMILY:
        for name, line in _imports(SRC / rel):
            if name in DOORS or name.startswith('laplace.web.authoring') or name == 'laplace.web.authoring_http':
                if rel == 'writing/mutation_attribution.py' and name == 'laplace.web.research_surface':
                    continue   # the one named residual: the research project home (family 3)
                offences.append((rel, line, name))
    assert offences == []


def test_the_facade_keeps_no_body_and_no_forward_of_the_moved_names():
    facade = SRC / 'web' / 'authoring.py'
    source = facade.read_text()
    for name in ('def _bank(', 'def proposal_write_lock(', 'def _applications(', 'def proposal_view(', 'def finish_source_changes(', 'def _bank_read_baseline_groups('):
        assert name not in source
    from laplace.web import authoring as authoring_surface
    import importlib
    for name, module in MOVED.items():
        owner = importlib.import_module(module)
        public = name.lstrip('_') if name in {'_bank', '_applications', '_applied_edits', '_bank_read_baseline_groups'} else name
        public = {'bank_read_baseline_groups': 'bank_read_baseline_groups'}.get(public, public)
        assert hasattr(owner, public), (name, module)
        assert not hasattr(authoring_surface, name), (name, 'consumers reach the owner %s directly' % module)


def test_the_family_imports_headless():
    script = ('import sys,importlib\n'
              'for m in ("laplace.writing.records","laplace.manuscript.source_effects","laplace.manuscript.source_application","laplace.manuscript.proposal_currentness",'
              '"laplace.writing.turn_reads","laplace.writing.turn_context","laplace.writing.mutation_attribution","laplace.manuscript.manuscript_proposals"):\n'
              '    importlib.import_module(m)\n'
              'print(json.dumps(sorted(x for x in sys.modules if x.startswith("laplace"))))')
    out = subprocess.run([PYTHON, '-c', 'import json;' + script], capture_output=True, text=True, cwd=str(SRC.parents[1]))
    assert out.returncode == 0, out.stderr[-2000:]
    loaded = set(json.loads(out.stdout.strip().splitlines()[-1]))
    assert not (loaded & DOORS) and 'laplace.native.tools' not in loaded and 'laplace.writing.child_hosts' not in loaded, sorted(loaded & DOORS)


# ---------------------------------------------------------------------------------- a real source application, headless

HEADLESS_FLOW = r'''
import json, sys
from pathlib import Path
root = Path(sys.argv[1]); root.joinpath('contract').mkdir(parents=True, exist_ok=True)
src = root / 'sources' / 'fixture'; src.mkdir(parents=True)
(src / 'main.tex').write_text('\\documentclass{article}\n\\begin{document}\nOriginal prose.\n\\end{document}\n')
from laplace.projects import library as writing_projects; from laplace.manuscript import manuscript_source, proposal_preflight; from laplace.core import identity_doors
from laplace.pipeline import authoring
from laplace.writing import records; from laplace.manuscript import source_application, source_effects, proposal_currentness
from laplace.writing.records import _bank
status, _ = writing_projects.import_source({'name': 'fixture', 'title': 'Fixture', 'root': 'sources/fixture/main.tex', 'editable': True}, root)
assert status == 201
source = manuscript_source.resolve('fixture', repo_root=root)
selection = {'files': ['main.tex']}
context = authoring.build_context('fixture', selection, repo_root=root)
raw = (root / source['manuscript_dir'] / 'main.tex').read_text()
edit = {'file': 'main.tex', 'line_start': 3, 'line_end': 3, 'before': 'Original prose.', 'after': 'Revised prose.'}
edit['source_anchor'] = proposal_preflight.source_anchor(raw, 3, 3)
_bank.bank(root, {'record': 'writing-session', 'id': 'WS-h', 'project': 'fixture', 'provider': 'codex', 'model': 'm', 'effort': 'medium'})
_bank.bank(root, {'record': 'writing-turn', 'id': 'WT-h', 'session_id': 'WS-h', 'project': 'fixture', 'request_id': 'r', 'text': 'revise', 'mode': 'revise',
                  'selection': selection, 'context_id': context.get('context_id'), 'dependencies': context.get('dependencies'), 'document': context.get('document', source)})
_bank.bank(root, {'record': 'writing-reply', 'id': 'WR-h', 'turn_id': 'WT-h', 'session_id': 'WS-h', 'project': 'fixture', 'status': 'completed',
                  'proposal': {'answer': 'proposal', 'edits': [edit]}})
turn = records.fold_records(root)['turns']['WT-h']
from laplace.manuscript.manuscript_proposals import proposal_version
version = proposal_version(turn)[0]
out = {'before_state': proposal_currentness.proposal_view(turn)['proposal_state']}
try:   # the human Apply route with a stale exact candidate identity: the identity door refuses before any effect
    source_application._apply_proposal_locked(root, {'turn_id': 'WT-h', 'project': 'fixture', 'proposal_version': version,
                                                     'expected': ['proposal:fixture::WT-h@sha256:' + '0' * 64]})
    out['stale_guard'] = 'ACCEPTED'
except Exception as error:   # noqa: BLE001
    body = identity_doors.body(error, {'ok': False})
    out['stale_guard'] = {'type': type(error).__name__, 'refused': sorted((body.get('refused') or {}).keys())}
out['source_after_refusal'] = (root / source['manuscript_dir'] / 'main.tex').read_text()
# the human Apply route as authoring_surface.apply_proposal runs it, without the facade: lock, transaction, finish
def apply_once():
    changes = []
    with records.proposal_write_lock(root):
        row = source_application._apply_proposal_locked(root, {'turn_id': 'WT-h', 'project': 'fixture', 'proposal_version': version}, source_changes=changes)
    source_effects.finish_source_changes(root, 'fixture', row, changes)
    return row
applied = apply_once()
out['applied'] = {'complete': applied.get('complete'), 'files': [row['path'] for row in (applied.get('owned_changes') or {}).get('files', [])],
                  'effect': sorted((applied.get('source_effect') or {}).keys())[:6]}
out['source_after_apply'] = (root / source['manuscript_dir'] / 'main.tex').read_text()
turn = records.fold_records(root)['turns']['WT-h']
out['after_state'] = proposal_currentness.proposal_view(turn)['proposal_state']
again = apply_once()
out['replay'] = {'reused': again.get('reused'), 'same_id': again.get('id') == applied.get('id'),
                 'source_state': source_effects.application_source_state(root, again)}
out['applications'] = len(source_effects.applications(turn))
out['rows'] = [json.loads(l)['record'] for l in (root / 'contract/talk.jsonl').read_text().splitlines()]
out['loaded_doors'] = sorted(m for m in sys.modules if m in {'laplace.web.authoring', 'laplace.web.authoring_http', 'laplace.writing.provider', 'laplace.web.scanner'})
out['loaded_native_door'] = 'laplace.native.tools' in sys.modules
print(json.dumps(out))
'''


def test_a_real_source_application_runs_headless(tmp_path):
    script = tmp_path / 'headless_flow.py';script.write_text(HEADLESS_FLOW)
    out = subprocess.run([PYTHON, str(script), str(tmp_path / 'root')], capture_output=True, text=True, cwd=str(SRC.parents[1]),
                         env={**os.environ, 'LAPLACE_STATE': str(tmp_path / 'state')})
    assert out.returncode == 0, out.stderr[-3000:]
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result['before_state'] == 'saved-without-final-reply' or result['before_state'] == 'ready'
    assert result['stale_guard'] != 'ACCEPTED' and 'refused' in json.dumps(result['stale_guard']) and 'Original prose.' in result['source_after_refusal']
    assert result['applied']['complete'] is True and result['applied']['files'] and 'Revised prose.' in result['source_after_apply']
    assert result['after_state'] == 'applied', result['after_state']
    assert result['replay'] == {'reused': True, 'same_id': True, 'source_state': 'POSTIMAGE'}
    assert result['applications'] == 1 and result['rows'].count('writing-application') == 1
    # the facade, the HTTP door and the provider adapter are never reached; laplace.web.scanner is reached once, by
    # pipeline.authoring.build_context -> _glossary -> verify._load_corpus_network (the pipeline's corpus loader),
    # a residual outside this family that the packet names
    assert set(result['loaded_doors']) <= {'laplace.web.scanner'}, result['loaded_doors']


# -------------------------------------------------------------------- the shared mechanics, Work and source application

def test_work_and_source_application_share_admission_refusal_journal_and_replay(root):
    # one payload admission for both operations: the declared contract refuses a wrong shape the same way
    for operation, payload in (('project', {'view': 'nowhere'}), ('apply_revision', {'turn_id': 7})):
        with pytest.raises(writing_declarations.PayloadAdmissionError):
            writing_declarations.validate_owner_payload(operation, payload, project=P)
    # one request grammar routes both acts and prepares the agent's native request for both
    assert writing_verbs.classify('project', {'view': 'roots'}, project=P, root=root).exact
    assert writing_verbs.classify('apply_revision', {'turn_id': 'WT-n', 'proposal_version': 'sha256:' + 'a' * 64}, project=P, root=root).route is not None
    # one journal write owner: the Work read receipt and every family row go through records._bank.bank
    make(root, 'W1', title='one', goal='one')
    value = writing_tools.execute(root, P, 'work', 'project', {'view': 'roots'}, 'WT-n')
    rows = [json.loads(line) for line in (root / 'contract/talk.jsonl').read_text().splitlines()]
    assert any(row['id'] == value['read_receipt']['id'] for row in rows)
    assert writing_tools._bank_talk_row.__module__ == 'laplace.native.tools' and journal_bank.bank is records.bank
    # the domain guards stay local but leave through the same refusal body: Work's exact revision and the proposal's basis
    stale_work = pytest.raises(work.WorkConflict, work.task, P, {'id': 'W1', 'title': 'two', 'expected_work_revision': 'sha256:' + '0' * 64}, root)
    work_body = identity_doors.body(stale_work.value, {'ok': False, **stale_work.value.details})
    assert work_body['code'] == 'CHANGED_INPUT' and work_body['next_reads'][0]['operation'] == 'project'
    refusal = identity_doors.gate.__module__ == 'laplace.core.identity_doors'
    assert refusal
    # one replay port keeps the consulted Work page current and reports a genuine change
    turn = records.fold_records(root)['turns']['WT-n']
    read = next(row for row in turn['tool_reads'].values() if row['id'] == value['read_receipt']['id'])
    assert proposal_currentness._observe_read(root, turn, read, {}) is None
    work.task(P, {'id': 'W1', 'title': 'changed', 'expected_work_revision': work._task_revision(work._tasks(P, root)['W1'])}, root)
    assert proposal_currentness._observe_read(root, turn, read, {})['currentness'] == 'CHANGED'
    # one bounded delivery policy: the Work page is profiled, the application is not (its contract is explicit)
    assert delivery.profile('project', {'view': 'roots'}) and delivery.profile('apply_revision', {'turn_id': 'WT-n'}) is None
