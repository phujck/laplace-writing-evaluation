"""The consolidated-core conformance witness of the portable Writing package (standalone-use obligation, 2026-10-20).

Two finite checks, each a child process of the SELECTED interpreter (`sys.executable`) importing the SAME code this
process imported `laplace` from (an installed site-packages in the evaluation profile; `src` in a source checkout).
No developer launcher, no sibling checkout, no user site (-s), no user state, no provider: the child sees only that package root, its
own disposable workspace and state root.

1. HEADLESS: a project is imported from a synthetic TeX source, a Work row is recorded and read back, a saved proposal
   is refused at the identity door with a stale candidate identity (no byte moves), applied once through the real
   transaction and lock, replayed as the same application; the journal holds exactly one application. The module
   origins of every laplace/atlas module are under the package root. The child is FAIL-CLOSED: before any application
   import it makes the provider service, the HTTP server, the native door, the application facade, the frontend and
   the desktop app module unimportable and makes any process start raise; the flow then runs to completion, so the
   core boundary is proved by construction, not by an after-the-fact listing. One canonical definition (a definition
   node under the fixture's section plus its projection term, both through the friction gate) is written in the
   explicit workspace and must appear in the built context's glossary: the glossary resolves there, not in any other
   checkout.
2. HTTP: the existing app (`python -m laplace.web.writing_server`) serves a synthetic workspace on loopback: health,
   the project page, a frontend asset, project creation and a manuscript start, then a Work write whose guard
   refuses a stale revision (409) and admits the exact one.

The workspace resources the app needs are provisioned explicitly here and documented in the agent start guide:
`registry_projects.json` (the project registry the server requires) and `profiles/writing_sources.json` (the
repository configuration); nothing is read from any other checkout.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import laplace

PACKAGE_ROOT = Path(laplace.__file__).resolve().parents[1]

CORE_FLOW = r'''
import json, sys
from pathlib import Path
# FAIL-CLOSED, before any application import: the provider service, the HTTP server, the native door, the application facade,
# the frontend and the desktop app module cannot be imported at the core boundary, and no process can start
FORBIDDEN = ('laplace.writing.provider', 'laplace.web.scanner', 'laplace.native.tools', 'laplace.web.authoring', 'laplace.web.shared_ui', 'laplace.desktop.writing_app')
class _Deny:
    def find_spec(self, name, path=None, target=None):
        if name in FORBIDDEN:
            raise ImportError('core boundary: %s is not importable in the headless core' % name)
        return None
sys.meta_path.insert(0, _Deny())
def _no_process(event, args):
    if event in ('subprocess.Popen', 'os.exec', 'os.posix_spawn', 'os.system', 'os.fork', 'os.forkpty'):
        raise RuntimeError('core boundary: no process may start in the headless core (%s)' % event)
sys.addaudithook(_no_process)
package_root = Path(sys.argv[2]).resolve()
root = Path(sys.argv[1]); root.joinpath('contract').mkdir(parents=True, exist_ok=True)
src = root / 'sources' / 'fixture'; src.mkdir(parents=True)
(src / 'main.tex').write_text('\\documentclass{article}\n\\begin{document}\nOriginal prose.\n\\input{S1}\n\\end{document}\n')
(src / 'S1.tex').write_text('\\section{Setting}\\label{sec:setting}\nSetting prose.\n')
from laplace.projects import library as writing_projects; from laplace.manuscript import manuscript_source, proposal_preflight; from laplace.core import identity_doors; from laplace.work import project_work; from laplace.research import corpus_ingest
from laplace.pipeline import authoring
from laplace.writing import records; from laplace.manuscript import source_application, source_effects, proposal_currentness
from laplace.writing.records import _bank
status, _ = writing_projects.import_source({'name': 'fixture', 'title': 'Fixture', 'root': 'sources/fixture/main.tex', 'editable': True}, root)
assert status == 201, status
out = {}
# one small canonical definition in THIS workspace, through the friction gate (the conceptric's own write door): a definition
# node under the section, then its projection term; the glossary must read it back from this workspace's own corpus
for deposit in ({'kind': 'add-node', 'node': 'def:revised-prose', 'parent': 'sec:setting', 'node_kind': 'definition',
                 'essence': 'A revised sentence is one whose prose was revised.', 'by': 'fixture'},
                {'kind': 'set-projection', 'node': 'def:revised-prose', 'value': {'term': 'revised prose', 'aliases': ['the revision']}, 'by': 'fixture'}):
    deposited = corpus_ingest.rewire_add(root, 'fixture', deposit)
    assert not deposited.get('error'), deposited
# Work: one row recorded and read back through the owner's detail view
created = project_work.task('fixture', {'id': 'w1', 'title': 'Revise the prose', 'goal': 'Replace the original prose with the revised sentence.'}, root)
detail = project_work.read('fixture', {'view': 'detail', 'id': 'w1'}, root)
out['work'] = {'id': detail['task']['id'], 'status': detail['task']['status'], 'revision': created.get('work_revision'),
               'actions': sorted(detail.get('allowed_actions') or {})[:6]}
source = manuscript_source.resolve('fixture', repo_root=root)
selection = {'files': ['main.tex']}
context = authoring.build_context('fixture', selection, repo_root=root)
out['glossary'] = (context.get('consumed') or {}).get('glossary')   # the consumed identities the context receipt records
out['glossary_part'] = next((part.get('text') for part in context.get('parts') or [] if part.get('key') == 'glossary'), None)
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
out['before_state'] = proposal_currentness.proposal_view(turn)['proposal_state']
try:   # the human Apply route with a stale exact candidate identity: the identity door refuses before any effect
    source_application._apply_proposal_locked(root, {'turn_id': 'WT-h', 'project': 'fixture', 'proposal_version': version,
                                                     'expected': ['proposal:fixture::WT-h@sha256:' + '0' * 64]})
    out['stale_guard'] = 'ACCEPTED'
except Exception as error:   # noqa: BLE001
    body = identity_doors.body(error, {'ok': False})
    out['stale_guard'] = {'type': type(error).__name__, 'refused': sorted((body.get('refused') or {}).keys())}
out['source_after_refusal'] = (root / source['manuscript_dir'] / 'main.tex').read_text()
def apply_once():
    changes = []
    with records.proposal_write_lock(root):
        row = source_application._apply_proposal_locked(root, {'turn_id': 'WT-h', 'project': 'fixture', 'proposal_version': version}, source_changes=changes)
    source_effects.finish_source_changes(root, 'fixture', row, changes)
    return row
applied = apply_once()
out['applied'] = {'complete': applied.get('complete'), 'files': [row['path'] for row in (applied.get('owned_changes') or {}).get('files', [])]}
out['source_after_apply'] = (root / source['manuscript_dir'] / 'main.tex').read_text()
turn = records.fold_records(root)['turns']['WT-h']
out['after_state'] = proposal_currentness.proposal_view(turn)['proposal_state']
again = apply_once()
out['replay'] = {'reused': again.get('reused'), 'same_id': again.get('id') == applied.get('id'), 'source_state': source_effects.application_source_state(root, again)}
out['applications'] = len(source_effects.applications(turn))
out['rows'] = [json.loads(l)['record'] for l in (root / 'contract/talk.jsonl').read_text().splitlines()]
origins = {name: getattr(module, '__file__', None) for name, module in sys.modules.items() if name == 'laplace' or name.startswith(('laplace.', 'atlas.')) or name == 'atlas'}
out['origins'] = {'count': len(origins), 'outside_package_root': sorted(n for n, f in origins.items() if f and not Path(f).resolve().is_relative_to(package_root)),
                  'records_bank': origins.get('laplace.writing.records._bank')}
out['absent_at_core'] = {name: name not in sys.modules for name in FORBIDDEN}
out['guard'] = {'forbidden_imports': list(FORBIDDEN), 'process_start': 'raises'}
print(json.dumps(out))
'''


def _child_env(state: Path) -> dict:
    env = {key: value for key, value in os.environ.items() if not key.startswith('LAPLACE_') and key not in ('PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP')}
    env.update(PYTHONPATH=str(PACKAGE_ROOT), LAPLACE_STATE=str(state), PYTHONDONTWRITEBYTECODE='1', LAPLACE_SESSION_WORKSPACES=str(state / 'workspaces'))
    return env


def test_the_installed_core_runs_work_and_saved_source_application_headless(tmp_path):
    script = tmp_path / 'core_flow.py'
    script.write_text(CORE_FLOW)
    out = subprocess.run([sys.executable, '-s', str(script), str(tmp_path / 'root'), str(PACKAGE_ROOT)], capture_output=True, text=True,
                         cwd=str(tmp_path), env=_child_env(tmp_path / 'state'), timeout=180)
    assert out.returncode == 0, out.stderr[-4000:]
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result['work']['id'] == 'w1' and result['work']['status'] in ('open', 'ready') and result['work']['revision']
    assert result['before_state'] in ('saved-without-final-reply', 'ready')
    assert result['stale_guard'] != 'ACCEPTED' and result['stale_guard']['refused'] and 'Original prose.' in result['source_after_refusal']
    assert result['applied']['complete'] is True and result['applied']['files'] and 'Revised prose.' in result['source_after_apply']
    assert result['after_state'] == 'applied' and result['replay'] == {'reused': True, 'same_id': True, 'source_state': 'POSTIMAGE'}
    assert result['applications'] == 1 and result['rows'].count('writing-application') == 1
    assert result['origins']['outside_package_root'] == [] and result['origins']['count'] > 40, result['origins']
    assert result['origins']['records_bank'] and Path(result['origins']['records_bank']).resolve().is_relative_to(PACKAGE_ROOT)
    assert set(result['absent_at_core']) == {'laplace.writing.provider', 'laplace.web.scanner', 'laplace.native.tools', 'laplace.web.authoring', 'laplace.web.shared_ui', 'laplace.desktop.writing_app'}
    assert all(result['absent_at_core'].values()) and result['guard']['process_start'] == 'raises', result['absent_at_core']
    # the workspace's own definition reached the built context: resolved in the explicit workspace, not in any other checkout
    assert result['glossary'] == [{'id': 'def:revised-prose', 'term': 'revised prose', 'aliases': ['the revision']}], result['glossary']
    assert result['glossary_part'] and 'revised prose (def:revised-prose)' in result['glossary_part'], result['glossary_part']
    (tmp_path / 'core_flow_result.json').write_text(json.dumps(result, indent=1))
    target = os.environ.get('LAPLACE_PORTABLE_CORE_EVIDENCE')
    if target:
        Path(target).mkdir(parents=True, exist_ok=True)
        (Path(target) / 'headless.json').write_text(json.dumps(result, indent=1))


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def _request(base: str, path: str, payload: dict | None = None) -> tuple[int, object]:
    data = json.dumps(payload).encode() if payload is not None else None
    # every writing mutation crosses the app's same-origin deliberate-action boundary: the client header the frontend sends
    request = urllib.request.Request(base + path, data=data, method='POST' if data is not None else 'GET',
                                     headers={'Content-Type': 'application/json', 'X-Laplace-Writing': '1'} if data is not None else {})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            code = response.status
            kind = response.headers.get('Content-Type', '')
    except urllib.error.HTTPError as error:
        raw, code, kind = error.read(), error.code, error.headers.get('Content-Type', '')
    return code, (json.loads(raw) if 'json' in kind else raw)


def test_the_installed_app_serves_health_assets_project_and_a_guarded_work_write_on_loopback(tmp_path):
    workspace = tmp_path / 'workspace'
    (workspace / 'profiles').mkdir(parents=True)
    # the two explicitly provisioned workspace resources: the project registry the server requires and the repository
    # configuration the Work and source owners read (an exported workspace carries both; a synthetic one writes them)
    (workspace / 'registry_projects.json').write_text(json.dumps({'projects': []}))
    (workspace / 'profiles' / 'writing_sources.json').write_text(json.dumps({'repositories': {'laplace': '.'}}))
    state = tmp_path / 'state'
    port = _free_port()
    server = subprocess.Popen([sys.executable, '-s', '-m', 'laplace.web.writing_server', '--root', str(workspace), '--state', str(state),
                               '--host', '127.0.0.1', '--port', str(port)],
                              cwd=str(tmp_path), env=_child_env(state), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    base = 'http://127.0.0.1:%d' % port
    transcript = []
    try:
        deadline = time.time() + 60
        health = None
        while time.time() < deadline:
            try:
                code, health = _request(base, '/authoring/health')
                if code == 200:
                    break
            except (urllib.error.URLError, ConnectionError, OSError):
                pass
            assert server.poll() is None, 'the server exited before it was healthy: ' + (server.stdout.read() if server.stdout else '')[-2000:]
            time.sleep(0.2)
        assert isinstance(health, dict) and health.get('schema_version', '').startswith('laplace.writing-health'), health
        transcript.append({'path': '/authoring/health', 'code': 200, 'keys': sorted(health)[:12], 'runtime_start': health.get('runtime_start')})
        code, page = _request(base, '/project?workspace=writing')
        assert code == 200 and b'<html' in page[:2000].lower(), (code, page[:200])
        code, asset = _request(base, '/shared/workspace.mjs')
        assert code == 200 and len(asset) > 1000
        transcript.append({'path': '/shared/workspace.mjs', 'code': code, 'bytes': len(asset)})
        code, created = _request(base, '/projects/create', {'name': 'portable-core', 'title': 'Portable core fixture', 'kind': 'general', 'purpose': 'Exercise the installed owners.'})
        assert code == 201 and created.get('ok') is True and created.get('project') == 'portable-core', (code, created)
        code, started = _request(base, '/projects/start', {'project': 'portable-core', 'title': 'Fixture report', 'kind': 'paper'})
        assert code == 201 and started.get('ok', True) is not False, (code, started)
        transcript.append({'path': '/projects/start', 'code': code, 'manuscript': (started.get('authoring_lifecycle') or {}).get('manuscript', {}).get('root')})
        code, task = _request(base, '/work/task', {'project': 'portable-core', 'id': 'w1', 'title': 'First work', 'goal': 'Prove the guarded Work write over HTTP.'})
        assert code == 201 and task.get('work_revision'), (code, task)
        code, stale = _request(base, '/work/task', {'project': 'portable-core', 'id': 'w1', 'title': 'First work', 'goal': 'A stale guard must refuse.',
                                                     'expected_work_revision': 'sha256:' + '0' * 64})
        assert code == 409, (code, stale)
        code, detail = _request(base, '/work/state?project=portable-core&view=detail&id=w1')
        assert code == 200 and detail['task']['goal'] == 'Prove the guarded Work write over HTTP.'
        code, edited = _request(base, '/work/task', {'project': 'portable-core', 'id': 'w1', 'title': 'First work', 'goal': 'The exact guard admits the edit.',
                                                      'expected_work_revision': detail['task']['work_revision']})
        assert code == 201, (code, edited)
        code, detail = _request(base, '/work/state?project=portable-core&view=detail&id=w1')
        assert detail['task']['goal'] == 'The exact guard admits the edit.'
        transcript.append({'path': '/work/task', 'stale_code': 409, 'exact_code': 201, 'revision_before': task['work_revision'], 'revision_after': detail['task']['work_revision']})
    finally:
        server.terminate()
        try:
            server.wait(timeout=20)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
    assert (workspace / 'registry_projects.json').is_file() and not (Path.home() / '.mcp-gerard' / 'portable-core').exists()
    target = os.environ.get('LAPLACE_PORTABLE_CORE_EVIDENCE')
    if target:
        Path(target).mkdir(parents=True, exist_ok=True)
        (Path(target) / 'http.json').write_text(json.dumps({'package_root': str(PACKAGE_ROOT), 'interpreter': sys.executable, 'transcript': transcript}, indent=1))
