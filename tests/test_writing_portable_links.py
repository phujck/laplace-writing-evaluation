"""Portable manuscript links and current Work inputs (WORK-editor-manuscript-evidence-link-export-20261015).

One synthetic checkout with two imported projects. The selected manuscript links the same owner-pinned artifact
through its relative owner route and through a host-bound absolute spelling of it, a percent-named artifact, a
receipt-qualified artifact, a changed artifact, a missing artifact, the unselected project's same-named artifact,
a refused coordinate, links the canonical owner refuses (unknown owner, unknown receipt, wrong receipt pin), a
research result, a machine-bound non-route URL and a public https URL. Its Work holds an accepted review with no
declared inputs but pinned evidence, a HOLD review, an awaiting obligation whose input is in the closure, a
declared private input and an accepted review whose Work intent was revised afterwards. The checks: the canonical
owners decide every relationship; the explicit selection carries exactly the eligible input and states each
omission; the portable copy, its appendix, record page, HTML list and PDF are declared and mapped; the verifier
reads only declared, admitted coordinates; the exported tooling verifies and re-exports in isolation; the original
source, PDF and history are unchanged.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import html
from pathlib import PurePosixPath
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


inventory = _load('writing_eval_manifest')
exporter = _load('export_writing_evaluation')
verifier = _load('verify_writing_evaluation')
portable = _load('writing_portable_links')

from laplace.work import project_work, project_work_review  # noqa: E402
from laplace.projects import library as writing_projects
from laplace.native import tools as writing_tools
from laplace.projects import artifacts  # noqa: E402
from laplace.web import research_artifact_read
from laplace.writing import records as _bank  # noqa: E402

P, OTHER = 'alpha', 'beta'
HOST = 'http://127.0.0.1:8771'


def _sha(raw: bytes) -> str:
    return 'sha256:' + hashlib.sha256(raw).hexdigest()


def _tree(root: Path, skip=('.laplace-state', 'state')) -> dict:
    return {str(p.relative_to(root)): _sha(p.read_bytes()) for p in root.rglob('*') if p.is_file() and not any(part in skip for part in p.relative_to(root).parts)}


def _href(url: str, label: str) -> str:
    """The writer's TeX spelling of an owner link (the escapes the walk's literal rule decodes)."""
    return r'\href{' + url.replace('&', r'\&').replace('%', r'\%').replace('_', r'\_') + '}{' + label + '}'


def _release_inputs(root: Path) -> None:
    (root / 'contract').mkdir(parents=True, exist_ok=True)
    (root / 'pyproject.toml').write_text('[project]\nname="example"\n')
    (root / 'src/laplace').mkdir(parents=True, exist_ok=True); (root / 'src/laplace/app.py').write_text('import json\n')
    for relative in ('docs/writing-evaluation-release.md', 'docs/writing-evaluator-readme.md', 'docs/writing-evaluator-agents.md', 'docs/writing-container.md',
                     'docs/writing-registry.md', 'deploy/writing/Dockerfile', 'deploy/writing/writing-entrypoint.sh', 'deploy/writing/smoke.py'):
        (root / relative).parent.mkdir(parents=True, exist_ok=True); (root / relative).write_text('required release input')
    # the exporter's own tooling travels with every export (OPERATIONAL_INPUTS); the isolated-tool check runs it from there
    for relative in ('scripts/writing_eval_manifest.py', 'scripts/export_writing_evaluation.py', 'scripts/verify_writing_evaluation.py',
                     'scripts/writing_export_bytes.py', 'scripts/writing_portable_links.py', 'scripts/inspect_writing_export.py'):
        (root / relative).parent.mkdir(parents=True, exist_ok=True); shutil.copy(ROOT / relative, root / relative)


def _closure(src: Path, records=()) -> None:
    for name, value in (('projection_plan.json', {'sections': []}), ('references.json', {'sources': []}),
                        ('research_records.json', {'records': list(records)}), ('figure_manifest.json', {'figures': []})):
        (src / name).write_text(json.dumps(value))
    (src / 'main.pdf').write_bytes(b'the author\'s built pdf, not rebuilt')


def _work(root: Path, work_id: str, obligation: dict, *, pins=None, verdict=None, goal='Review the notes.'):
    project_work.task(P, {'id': work_id, 'title': 'Work ' + work_id, 'goal': goal, 'review_obligations': [obligation]}, root)
    if pins is None:
        return
    revision = lambda: project_work._task_revision(project_work._tasks(P, root)[work_id])
    handoff = project_work_review.record(P, {'id': work_id, 'phase': 'handoff', 'request_id': 'handoff-' + work_id, 'expected_work_revision': revision(),
                                              'obligations': [obligation['id']], 'object': {'kind': 'evidence', 'checkpoint': work_id}, 'pins': pins},
                                         root, door={'origin': 'native', 'turn_id': 'WT-a'})
    if verdict:
        project_work_review.record(P, {'id': work_id, 'phase': 'review', 'request_id': 'review-' + work_id, 'expected_work_revision': revision(),
                                       'handoff_id': handoff['phase']['id'], 'obligation_id': obligation['id'], 'verdict': verdict,
                                       'actor': {'origin': 'external', 'actor': 'independent-reviewer', 'evidence': [{'path': path, 'sha256': digest} for path, digest in pins.items()]}},
                                   root, door={'origin': 'human'}, mode='review')


def source_root(root: Path) -> dict:
    _release_inputs(root)
    bases = {}
    for project in (P, OTHER):
        src = root / 'sources' / project; src.mkdir(parents=True)
        (src / 'main.tex').write_text('\\documentclass{article}\n\\begin{document}\nPlaceholder.\n\\end{document}\n')
        status, body = writing_projects.import_source({'name': project, 'title': 'Fixture ' + project, 'root': 'sources/%s/main.tex' % project, 'editable': True}, root)
        assert status == 201, body
        _closure(src, records=[{'id': 'result-one', 'kind': 'result', 'summary': 'A synthetic result.'},
                               {'id': 'res:a', 'kind': 'result', 'summary': 'Result with a colon.'},
                               {'id': 'res_a', 'kind': 'result', 'summary': 'Result with an underscore.'}] if project == P else [])
        base = artifacts._project_root(root, project)
        (base / 'development').mkdir(parents=True, exist_ok=True)
        bases[project] = base
    for row in ({'record': 'writing-session', 'id': 'WS-a', 'project': P, 'provider': 'codex', 'model': 'm', 'effort': 'medium'},
                {'record': 'writing-turn', 'id': 'WT-a', 'session_id': 'WS-a', 'project': P, 'request_id': 'r-1', 'text': 'review', 'mode': 'review',
                 'provider_settings': {'provider': 'codex', 'model': 'm', 'effort': 'medium'}}):
        _bank.bank(root, row)
    observation = b'{"summary": "Exact retained observation"}\n'
    (bases[P] / 'development' / 'notes.json').write_bytes(observation)
    special = {}
    for name in ('sharp#1.json', 'what?.json', 'with space.json', '\u00fcn\u00efcode.json'):
        raw = ('{"name": %s}\n' % json.dumps(name)).encode('utf-8')
        (bases[P] / 'development' / name).write_bytes(raw)
        special[name] = artifacts.artifact_human_read(P, 'development/' + name, 'project', _sha(raw))['url']
    percent = b'{"name": "a literal percent file"}\n'
    (bases[P] / 'development' / 'a%2Fb.json').write_bytes(percent)
    (bases[P] / 'development' / 'drift.json').write_bytes(b'{"state": "later"}\n')
    (bases[OTHER] / 'development' / 'notes.json').write_bytes(b'{"summary": "The other project\'s notes"}\n')
    # a receipt-qualified artifact through the writer's own store (its human link carries owner and artifact_id)
    stored = writing_tools.execute(root, P, 'work', 'store_artifact', {'path': 'development/receipt.json', 'scope': 'project', 'before': None,
                                                                        'content': '{"kind": "stored through the owner"}\n', 'reason': 'Portable-link fixture'})
    receipt_url = stored['human_read']['url']
    pinned = artifacts.artifact_human_read(P, 'development/notes.json', 'project', _sha(observation))['url']
    percent_url = artifacts.artifact_human_read(P, 'development/a%2Fb.json', 'project', _sha(percent))['url']
    drift = artifacts.artifact_human_read(P, 'development/drift.json', 'project', _sha(b'{"state": "earlier"}\n'))['url']
    gone = artifacts.artifact_human_read(P, 'development/vanished.json', 'project', _sha(b'never present'))['url']
    foreign = artifacts.artifact_human_read(OTHER, 'development/notes.json', 'project', _sha(b'{"summary": "The other project\'s notes"}\n'))['url']
    refused = artifacts.artifact_human_read(P, 'references.json', 'project', _sha(b'x'))['url']
    unknown_owner = pinned.replace('owner=writing-artifact', 'owner=unknown')
    unknown_receipt = pinned + '&artifact_id=ART-unknown'
    wrong_pin_receipt = receipt_url.replace(stored['human_read']['expected_sha256'], '0' * 64)
    tex = '\n'.join([
        r'\documentclass{article}', r'\usepackage{hyperref}', r'\begin{document}', r'\section{Results}',
        'The observation ' + _href(pinned, 'observed result') + ' supports the claim, as does the result ' + _href('/research/result?project=%s&id=result-one' % P, 'result one') + '.',
        'The same observation by its machine-bound spelling ' + _href(HOST + pinned, 'observed result again') + ' and a stored receipt ' + _href(receipt_url, 'the receipt') + '.',
        'A percent-named file ' + _href(percent_url, 'percent file') + '; an unknown owner ' + _href(unknown_owner, 'unknown owner') + '; an unknown receipt ' + _href(unknown_receipt, 'unknown receipt')
        + '; a wrong receipt pin ' + _href(wrong_pin_receipt, 'wrong pin') + '.',
        'An earlier reading ' + _href(drift, 'drifted notes') + ' and a lost one ' + _href(gone, 'vanished notes') + ' are recorded; see also ' + _href(foreign, 'the other project') + '.',
        'A canonical file ' + _href(refused, 'references') + ', an external page ' + _href('https://example.org/method', 'method page')
        + ' and a machine-bound page ' + _href('http://localhost:8771/project?corpus=alpha&view=manuscript', 'the app on my machine') + '.',
        r'\begin{figure}', r'\centering', r'\fbox{figure body}',
        r'\caption{The figure draws on ' + _href(pinned, 'the observation') + '.}',
        r'\end{figure}',
        r'\section{Method}', 'Plain prose without links.',
        'Special names: ' + ' '.join(_href(url, 'special ' + str(index)) for index, url in enumerate(special.values())) + '.',
        'Two results that a lossy name would merge: ' + _href('/research/result?project=%s&id=res%%3Aa' % P, 'res colon') + ' and ' + _href('/research/result?project=%s&id=res_a' % P, 'res underscore') + '.',
        r'\end{document}', ''])
    (root / 'sources' / P / 'main.tex').write_text(tex)
    # the Work: public evidence outside the manuscript closure in several canonical shapes, and a private declared input
    (root / 'evidence').mkdir()
    for name in ('alpha-other', 'alpha-hold', 'alpha-intent'):
        (root / 'evidence' / (name + '.txt')).write_text('Independent %s notes.\n' % name)
    (root / 'private').mkdir(); (root / 'private' / 'notes.txt').write_text('never exported\n')
    pin = lambda name: _sha((root / 'evidence' / (name + '.txt')).read_bytes())
    _work(root, 'w-evidence', {'id': 'evidence', 'scope': 'other', 'label': 'Evidence review', 'inputs': []}, pins={'evidence/alpha-other.txt': pin('alpha-other')}, verdict='ACCEPT')
    _work(root, 'w-hold', {'id': 'hold', 'scope': 'other', 'label': 'Held review', 'inputs': ['evidence/alpha-hold.txt']}, pins={'evidence/alpha-hold.txt': pin('alpha-hold')}, verdict='HOLD')
    _work(root, 'w-awaiting', {'id': 'closure', 'scope': 'source', 'label': 'Source review', 'inputs': ['sources/%s/main.tex' % P]})
    _work(root, 'w-private', {'id': 'secret', 'scope': 'other', 'label': 'Private notes', 'inputs': ['private/notes.txt']})
    _work(root, 'w-intent', {'id': 'intent', 'scope': 'other', 'label': 'Intent review', 'inputs': ['evidence/alpha-intent.txt']}, pins={'evidence/alpha-intent.txt': pin('alpha-intent')}, verdict='ACCEPT')
    project_work.task(P, {'id': 'w-intent', 'goal': 'A revised goal after the review.', 'expected_work_revision': project_work._task_revision(project_work._tasks(P, root)['w-intent'])}, root)   # material intent revised; bytes unchanged
    return {'pinned_url': pinned, 'observation': observation, 'percent': percent, 'pin': pin('alpha-other'), 'base': bases[P], 'receipt_id': stored['id'],
            'receipt_pin': 'sha256:' + stored['human_read']['expected_sha256'], 'special': special}


@pytest.fixture
def roots(tmp_path, monkeypatch):
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / 'state-source'))
    source = tmp_path / 'source'
    facts = source_root(source)
    return source, tmp_path, facts


def _facets(root):
    tasks = project_work._tasks(P, root)
    return {work_id: project_work_review.facet(task, root, tasks=tasks, project=P)['obligations'][0] for work_id, task in tasks.items()}


def _by_label(links, label):
    return next(row for row in links['targets'] if any(ref['label'] == label for ref in row['references']))


def test_the_canonical_owner_admits_every_link_and_one_entry_holds_one_admitted_meaning(roots):
    source, _tmp, facts = roots
    manifest = inventory.build(source, P)
    links = manifest['manuscript_links']
    observed = _by_label(links, 'observed result')
    assert observed['status'] == 'packaged' and observed['target'] == facts['base'].relative_to(source).as_posix() + '/development/notes.json'
    assert [ref['label'] for ref in observed['references']] == ['observed result', 'observed result again', 'the observation'], 'the relative and the host-bound spelling of one owner link share one entry'
    assert [(ref['heading'], ref['kind']) for ref in observed['references']] == [('Results', 'paragraph'), ('Results', 'paragraph'), ('Results', 'figure')]
    assert observed['spellings'] == ['app-route', 'host-bound:127.0.0.1:8771'] and observed['references'][1]['spelling'] == 'host-bound:127.0.0.1:8771' and observed['admitted_sha256'] == _sha(facts['observation'])
    # the canonical owner's answer and the projection agree, relation by relation
    canonical = lambda **query: research_artifact_read.resolve_read(source, P, {'scope': 'project', 'path': 'development/notes.json', 'expected_sha256': _sha(facts['observation'])[7:], **query})
    assert not isinstance(canonical(owner='writing-artifact'), tuple)
    assert canonical(owner='unknown')[0] == 422 and _by_label(links, 'unknown owner')['status'] == 'refused' and 'Unknown artifact reader owner' in _by_label(links, 'unknown owner')['reason']
    assert canonical(owner='writing-artifact', artifact_id='ART-unknown')[0] == 422 and _by_label(links, 'unknown receipt')['status'] == 'refused'
    assert _by_label(links, 'wrong pin')['status'] == 'refused' and 'differs from the exact artifact receipt' in _by_label(links, 'wrong pin')['reason']
    receipt = _by_label(links, 'the receipt')
    assert receipt['status'] == 'packaged' and receipt['artifact_id'] == facts['receipt_id'] and receipt['admitted_sha256'] == facts['receipt_pin'] and receipt['target'].endswith('development/receipt.json')
    assert _by_label(links, 'unknown owner')['key'] != observed['key'] and _by_label(links, 'unknown receipt')['key'] != observed['key'], 'a refused owner or receipt is another relationship than the valid one at the same path'
    percent = _by_label(links, 'percent file')
    assert percent['path'] == 'development/a%2Fb.json' and percent['status'] == 'packaged' and percent['target'].endswith('/development/a%2Fb.json'), 'a literal percent in a file name is the owner coordinate, not a directory'
    assert _by_label(links, 'drifted notes')['status'] == 'changed' and _by_label(links, 'vanished notes')['status'] == 'missing'
    assert _by_label(links, 'the other project')['status'] == 'unselected-project' and _by_label(links, 'the other project')['target'] is None
    assert _by_label(links, 'references')['status'] == 'refused'
    assert _by_label(links, 'method page')['status'] == 'external'
    machine = _by_label(links, 'the app on my machine')
    assert machine['status'] == 'unavailable' and machine['target'] is None and 'localhost:8771' in machine['reason']
    result = _by_label(links, 'result one')
    assert result['status'] == 'packaged' and result['target'] == 'sources/%s/research_records.json' % P and 'record' in result and 'fragment' not in result
    assert result['destination'].startswith('the whole research records file')
    assert links['references_total'] == 21 and len(links['targets']) == 19, 'twenty-one references; the three spellings of the observation are one relationship'


def test_work_inventory_is_the_facet_selected_review_and_the_selection_states_each_omission(roots, monkeypatch):
    source, tmp_path, facts = roots
    live = _facets(source)
    assert live['w-evidence']['satisfied'] and live['w-evidence']['currentness'] == 'CURRENT'
    assert live['w-hold']['status'] == 'HOLD' and live['w-awaiting']['status'] == 'AWAITING_HANDOFF' and live['w-intent']['currentness'] == 'STALE'
    rows = {(row['work_id'], row['path']): row for row in inventory.build(source, P)['work_inputs']['rows']}
    evidence = rows[('w-evidence', 'evidence/alpha-other.txt')]
    assert evidence['reviewed'] and not evidence['declared'] and evidence['review_pin'] == facts['pin'] and evidence['disposition'] == 'outside-closure' and evidence['selectable'], \
        'an obligation with no declared inputs is projected from its review\'s own pins'
    assert rows[('w-hold', 'evidence/alpha-hold.txt')]['selectable'] is False and 'HOLD' in rows[('w-hold', 'evidence/alpha-hold.txt')]['selection_reason']
    awaiting = rows[('w-awaiting', 'sources/%s/main.tex' % P)]
    assert awaiting['disposition'] == 'selected' and awaiting['reviewed'] is False and awaiting['review_pin'] is None and awaiting['selectable'] is False
    private = rows[('w-private', 'private/notes.txt')]
    assert private['disposition'] == 'private' and private['reviewed'] is False
    intent = rows[('w-intent', 'evidence/alpha-intent.txt')]
    assert intent['currentness'] == 'STALE' and intent['current_sha256'] == intent['review_pin'] and intent['selectable'] is False and 'STALE' in intent['selection_reason'], \
        'equal bytes do not make a revised-intent review current'
    before = _tree(source)
    export = tmp_path / 'export-current'
    report = exporter.export(source, export, P, work_inputs='current')
    assert _tree(source) == before
    assert [row['path'] for row in report['selected_supplementary_sources']] == ['evidence/alpha-other.txt'], 'exactly the eligible input travels'
    omitted = {(row['work_id'], row['path']): row for row in report['work_input_omissions'][P]}
    assert set(omitted) == {('w-hold', 'evidence/alpha-hold.txt'), ('w-private', 'private/notes.txt'), ('w-intent', 'evidence/alpha-intent.txt')}
    assert 'HOLD' in omitted[('w-hold', 'evidence/alpha-hold.txt')]['reason'] and 'STALE' in omitted[('w-intent', 'evidence/alpha-intent.txt')]['reason']
    assert omitted[('w-private', 'private/notes.txt')]['disposition'] == 'private' and not (export / 'private').exists()
    assert not (export / 'evidence/alpha-hold.txt').exists() and not (export / 'evidence/alpha-intent.txt').exists()
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / 'state-export'))
    imported = _facets(export)
    assert imported['w-evidence']['currentness'] == 'CURRENT' and imported['w-hold']['currentness'] == 'STALE' and imported['w-intent']['currentness'] == 'STALE'
    assert imported['w-awaiting']['status'] == 'AWAITING_HANDOFF'
    result = verifier.verify(export)
    assert result['ok'], result['failures']
    assert result['work_inputs'][P] == {'supplementary': 1, 'outside-closure': 2, 'selected': 1, 'private': 1}


def test_the_portable_copy_offers_real_destinations_and_links_relative_to_the_package(roots, monkeypatch):
    source, tmp_path, facts = roots
    before = _tree(source)
    export = tmp_path / 'export-portable'
    report = exporter.export(source, export, P, work_inputs='current', portable_document=True)
    assert _tree(source) == before, 'the original source, built PDF and history are unchanged'
    doc = report['portable_documents'][P]
    result = _by_label(report['manuscript_links'][P], 'result one')
    page = export / result['target']
    assert result['target'].startswith('portable/%s/records/' % P) and result['target'].endswith('.html') and page.is_file() and 'id="record"' in page.read_text() and 'A synthetic result.' in page.read_text()
    assert result['destination'].startswith('exact record page') and result['records_file'] == 'sources/%s/research_records.json' % P
    text = (export / doc['derived_root']).read_text()
    assert HOST not in text and '/research/artifact?' not in text and text.count('\\protect\\hyperlink{portable-link-1}{') == 3, 'all three spellings of one owner link point to one entry'
    assert 'localhost:8771' not in text.replace('\\url{http://localhost', '')
    listing = (export / doc['html']).read_text()
    hrefs = [part.split('"')[0] for part in listing.split('<a href="')[1:]]
    assert all(not href.startswith('/') and 'localhost' not in href and '127.0.0.1' not in href for href in hrefs), hrefs
    assert any(href.startswith('records/') and href.endswith('.html') for href in hrefs) and not any('#result-one' in href for href in hrefs)
    assert 'https://example.org/method' in hrefs and 'Machine-bound URL' in listing
    appendix = (export / doc['appendix']).read_text()
    assert 'records/' in appendix and 'exact record page' in appendix and '#result-one' not in appendix
    assert 'Not selected:' in appendix and 'alpha-hold' in appendix.replace('\\_', '_')
    assert doc['pdf'] or not (shutil.which('latexmk') or shutil.which('pdflatex')), json.dumps(doc['compiler'])[:600]
    if doc['pdf']:
        pdf = export / doc['pdf']['path']
        assert _sha(pdf.read_bytes()) == doc['pdf']['sha256'] and doc['compiler']['ok'] and doc['compiler']['errors'] == []
        if shutil.which('pdftotext'):
            words = subprocess.run(['pdftotext', str(pdf), '-'], capture_output=True, text=True, timeout=60).stdout
            assert 'Sources and artifacts' in words and 'observed result' in words
    assert (export / 'sources' / P / 'main.pdf').read_bytes() == b"the author's built pdf, not rebuilt"
    mapping = {row['derived']: row for row in doc['files']}
    assert mapping[result['target']]['source'] is None and 'research_catalogue.state_read' in mapping[result['target']]['derivation']
    assert mapping[doc['derived_root']]['source_sha256'] == next(row['sha256'] for row in report['copied_files'] if row['path'] == 'sources/%s/main.tex' % P)
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / 'state-export'))
    checked = verifier.verify(export)
    assert checked['ok'], checked['failures']
    assert checked['portable_documents'][P]['files'] == len(doc['files'])


def test_the_verifier_reads_only_declared_admitted_coordinates(roots, tmp_path, monkeypatch):
    source, tmp_path, facts = roots
    export = tmp_path / 'export-fence'
    exporter.export(source, export, P, work_inputs='current', portable_document=True)
    outside = tmp_path / 'outside'; outside.mkdir(); secret = outside / 'secret.txt'; secret.write_text('must never be opened by the verifier\n')
    opened = []
    sys.addaudithook(lambda event, args: opened.append(str(args[0])) if event == 'open' and str(args[0]).startswith(str(outside)) else None)
    manifest_path = export / 'release/export-manifest.json'
    pristine = manifest_path.read_bytes()
    link = (export / 'evidence' / 'link.txt'); link.symlink_to(secret)
    undeclared = export / 'evidence' / 'undeclared.txt'; undeclared.write_text('inside the export, not declared\n')
    cases = {'absolute': str(secret), 'climbing': '../outside/secret.txt', 'symlink': 'evidence/link.txt', 'undeclared': 'evidence/undeclared.txt'}
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / 'state-fence'))
    for name, target in cases.items():
        report = json.loads(pristine)
        row = _by_label(report['manuscript_links'][P], 'observed result')
        row['target'] = target
        report['work_inputs'][P]['rows'].append({'work_id': 'w-crafted', 'obligation_id': 'x', 'path': target, 'disposition': 'supplementary', 'reviewed': True, 'review_pin': 'sha256:' + '0' * 64})
        report['portable_documents'][P]['files'].append({'derived': target, 'source': None, 'derivation': 'crafted'})
        manifest_path.write_text(json.dumps(report))
        result = verifier.verify(export)
        reasons = [failure.get('reason') for failure in result['failures'] if failure.get('path') == target or failure.get('link')]
        assert not result['ok'] and reasons, (name, result['failures'][:4])
        assert all('not a declared copied or derived entry' in reason or 'read fence' in reason for reason in reasons if reason), (name, reasons)
    assert opened == [], 'no coordinate outside the candidate was opened'
    # a symlink that IS declared (a crafted copied entry) is refused by the fence in both the existing and the new reads
    report = json.loads(pristine)
    report['copied_files'].append({'path': 'evidence/link.txt', 'sha256': 'sha256:' + '0' * 64, 'bytes': 1})
    report['work_inputs'][P]['rows'].append({'work_id': 'w-crafted', 'obligation_id': 'x', 'path': 'evidence/link.txt', 'disposition': 'supplementary', 'reviewed': True, 'review_pin': 'sha256:' + '0' * 64})
    manifest_path.write_text(json.dumps(report))
    result = verifier.verify(export)
    assert any('symbolic link' in str(failure.get('reason')) for failure in result['failures']) and opened == []
    manifest_path.write_bytes(pristine); link.unlink(); undeclared.unlink()
    assert verifier.verify(export)['ok']


def test_the_exported_tooling_verifies_and_re_exports_in_isolation(roots, tmp_path):
    source, tmp_path, facts = roots
    export = tmp_path / 'export-tools'
    exporter.export(source, export, P, work_inputs='current', portable_document=True)
    assert (export / 'scripts/writing_portable_links.py').is_file(), 'the helper travels as an operational input'
    env = {key: value for key, value in os.environ.items() if not key.startswith('LAPLACE_') and key not in ('PYTHONPATH', 'PYTHONHOME')}
    env.update(PYTHONPATH=str(ROOT / 'src'), LAPLACE_STATE=str(tmp_path / 'state-isolated'), PYTHONDONTWRITEBYTECODE='1')
    elsewhere = tmp_path / 'elsewhere'; elsewhere.mkdir()
    probe = subprocess.run([sys.executable, '-s', '-c', 'import sys; sys.path.insert(0, sys.argv[1]); import writing_portable_links, writing_eval_manifest; print(writing_portable_links.__file__); print(writing_eval_manifest._portable().__file__)',
                            str(export / 'scripts')], capture_output=True, text=True, env=env, cwd=str(elsewhere), timeout=120)
    assert probe.returncode == 0, probe.stderr
    assert all(line.startswith(str(export)) for line in probe.stdout.strip().splitlines()), probe.stdout
    verified = subprocess.run([sys.executable, '-s', str(export / 'scripts/verify_writing_evaluation.py'), '--root', str(export)], capture_output=True, text=True, env=env, cwd=str(elsewhere), timeout=300)
    assert verified.returncode == 0, verified.stderr[-2000:] + verified.stdout[-2000:]
    assert json.loads(verified.stdout)['ok'] and json.loads(verified.stdout)['portable_documents'][P]['files'] >= 2
    again = subprocess.run([sys.executable, '-s', str(export / 'scripts/export_writing_evaluation.py'), '--repo-root', str(export), '--destination', str(tmp_path / 're-export'), '--project', P],
                           capture_output=True, text=True, env=env, cwd=str(elsewhere), timeout=300)
    assert again.returncode == 0, again.stderr[-2000:]
    assert json.loads(again.stdout.strip().splitlines()[-1])['status'] == 'CANDIDATE_REQUIRES_CLEAN_INSTALL_ACCEPTANCE'
    assert (tmp_path / 're-export' / 'scripts/writing_portable_links.py').is_file()


def test_a_changed_or_missing_reviewed_input_refuses_the_explicit_selection(roots, tmp_path):
    source, tmp_path, facts = roots
    (source / 'evidence' / 'alpha-other.txt').write_text('Edited after the review.\n')
    assert _facets(source)['w-evidence']['currentness'] == 'STALE'
    with pytest.raises(ValueError, match='changed'):
        exporter.export(source, tmp_path / 'export-changed', P, work_inputs='current')
    assert not (tmp_path / 'export-changed').exists(), 'the refusal precedes the destination'
    stated = exporter.export(source, tmp_path / 'export-stated', P)
    assert next(row for row in stated['work_inputs'][P]['rows'] if row['work_id'] == 'w-evidence')['disposition'] == 'changed'
    (source / 'evidence' / 'alpha-other.txt').unlink()
    with pytest.raises(ValueError, match='missing'):
        exporter.export(source, tmp_path / 'export-missing', P, work_inputs='current')


def test_the_link_parser_follows_the_walk_literal_rule_and_the_finite_url_classification():
    found = portable.tex_hrefs(r'See \href{/research/artifact?project=p\&scope=project\&path=a\%252Fb.json\&expected_sha256=' + 'a' * 64 + r'\&owner=writing-artifact}{a label} and \href{\macro}{x}.')
    assert [row['label'] for row in found] == ['a label', 'x'] and found[1]['url'] is None, 'an unresolved macro is no URL'
    link = portable.human_link(found[0]['url'])
    assert link == {'kind': 'artifact', 'project': 'p', 'scope': 'project', 'path': 'a%2Fb.json', 'expected_sha256': 'sha256:' + 'a' * 64, 'artifact_id': None, 'owner': 'writing-artifact'}, 'decoded once, as the owner route decodes it'
    assert portable.human_link('/project?corpus=p&view=manuscript')['kind'] == 'app-only'
    assert portable.human_link('http://127.0.0.1:8771/research/result?project=p&id=r')['kind'] == 'research-result' and portable.human_link('http://127.0.0.1:8771/research/result?project=p&id=r')['host_bound'] == '127.0.0.1:8771'
    assert portable.human_link('http://localhost:8771/anything')['kind'] == 'unavailable' and portable.human_link('http://192.168.1.4/project')['kind'] == 'unavailable'
    assert portable.human_link('https://example.org/x')['kind'] == 'external' and portable.human_link('http://example.org/x')['kind'] == 'external'
    assert portable.human_link('file:///tmp/provider/cwd/x.json')['kind'] == 'unknown' and portable.human_link('ART-1')['kind'] == 'unknown'


def _decode_html_href(href: str) -> str:
    return unquote(href)


def _decode_tex_href(href: str) -> str:
    return unquote(href.replace('\\%', '%').replace('\\#', '#').replace('\\&', '&'))


def test_local_hrefs_name_their_exact_files_once_decoded_and_record_pages_never_collide(roots, monkeypatch):
    """PL-C1: filesystem path, relative URL and carrier escaping are three steps. Every local href in the HTML list and
    the appendix, decoded exactly once by a URL consumer, is the exact admitted file (literal percent, #, ?, space and
    non-ASCII names included); two valid result ids that a lossy name would merge keep distinct pages with their own
    records."""
    source, tmp_path, facts = roots
    export = tmp_path / 'export-carrier'
    report = exporter.export(source, export, P, work_inputs='current', portable_document=True)
    links = report['manuscript_links'][P]
    doc = report['portable_documents'][P]
    specials = {_by_label(links, 'special %d' % index)['target'] for index in range(4)}
    assert specials == {facts['base'].relative_to(source).as_posix() + '/development/' + name for name in ('sharp#1.json', 'what?.json', 'with space.json', '\u00fcn\u00efcode.json')}
    listing = (export / doc['html']).read_text(encoding='utf-8')
    hrefs = [part.split('"')[0] for part in listing.split('<a href="')[1:]]
    local = [html.unescape(h) for h in hrefs if not h.startswith('http')]
    resolved = {str(PurePosixPath(os.path.normpath(str(PurePosixPath(doc['html']).parent / _decode_html_href(h))))) for h in local}
    expected = {row['target'] for row in links['targets'] if row['status'] == 'packaged'} | ({doc['pdf']['path']} if doc.get('pdf') else set())
    assert resolved == expected, (resolved ^ expected)
    assert all((export / rel).is_file() for rel in resolved), 'each decoded href is an existing exported file'
    assert any('a%252Fb.json' in h for h in local) and any('sharp%231.json' in h for h in local) and any('what%3F.json' in h for h in local) and any('with%20space.json' in h for h in local) and any('%C3%BC' in h for h in local), local
    appendix = (export / doc['appendix']).read_text(encoding='utf-8')
    tex_hrefs = [line.split('\\href{', 1)[1].split('}', 1)[0] for line in appendix.splitlines() if '\\href{' in line]
    appendix_resolved = {str(PurePosixPath(os.path.normpath(str(PurePosixPath(doc['appendix']).parent / _decode_tex_href(h))))) for h in tex_hrefs}
    assert appendix_resolved == {row['target'] for row in links['targets'] if row['status'] == 'packaged'}, (appendix_resolved ^ expected)
    colon, underscore = _by_label(links, 'res colon'), _by_label(links, 'res underscore')
    assert colon['target'] != underscore['target'] and colon['target'].startswith('portable/%s/records/' % P) and underscore['target'].startswith('portable/%s/records/' % P)
    assert 'Result with a colon.' in (export / colon['target']).read_text(encoding='utf-8') and 'Result with an underscore.' in (export / underscore['target']).read_text(encoding='utf-8')
    assert colon['id'] == 'res:a' and underscore['id'] == 'res_a', 'the owner ids are not narrowed'
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / 'state-export'))
    checked = verifier.verify(export)
    assert checked['ok'], checked['failures']
    with pytest.raises(ValueError, match='collision'):
        colliding = {'targets': [{'key': 'k1', 'ordinal': 1, 'label': 'a', 'kind': 'research-result', 'status': 'packaged', 'record': {'id': 'x'}, 'id': 'x', 'target': 'r.json', 'references': []},
                                 {'key': 'k1 ', 'ordinal': 2, 'label': 'b', 'kind': 'research-result', 'status': 'packaged', 'record': {'id': 'y'}, 'id': 'y', 'target': 'r.json', 'references': []}],
                     'references_total': 2, 'by_status': {'packaged': 2}}
        real = hashlib.sha256
        monkeypatch.setattr(portable.hashlib, 'sha256', lambda data: real(b'same'))
        portable.portable_document(source, P, source_root='sources/%s/main.tex' % P, closure_files=[], links=colliding, work={'rows': []})


def test_an_omission_states_the_live_observation_and_the_missing_pin_and_leaves_currentness_to_the_imported_facet(roots, monkeypatch):
    """PL-C2: the omission prose promises nothing about imported currentness; the imported canonical facet decides."""
    source, tmp_path, facts = roots
    export = tmp_path / 'export-omission'
    report = exporter.export(source, export, P, work_inputs='current')
    omitted = {row['work_id']: row for row in report['work_input_omissions'][P]}
    hold = omitted['w-hold']
    assert hold['live_observation'].startswith('review ') and 'HOLD' in hold['live_observation'] and 'CURRENT' in hold['live_observation']
    assert hold['omitted_pin'] == _sha((source / 'evidence' / 'alpha-hold.txt').read_bytes())
    assert 'can make the imported review STALE' in hold['consequence'] and 'imported canonical Work review facet alone decides' in hold['consequence']
    assert all('reads as it does live' not in row['consequence'] for row in omitted.values())
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / 'state-export'))
    imported = _facets(export)
    assert imported['w-hold']['status'] == 'HOLD' and imported['w-hold']['currentness'] == 'STALE', 'the historical verdict stays; the omission made it stale, as the prose allows'
    assert imported['w-evidence']['currentness'] == 'CURRENT' and imported['w-intent']['currentness'] == 'STALE'
    assert omitted['w-private']['omitted_pin'] is None and 'reviewed pin' not in omitted['w-private']['consequence']


def test_malformed_portable_metadata_is_a_named_finite_failure_before_anything_is_read(roots, tmp_path, monkeypatch):
    """PL-C3: the new optional metadata is admitted once; a malformed container or field names itself in the failures
    and nothing of the portable section is consumed; the restored manifest verifies again."""
    source, tmp_path, facts = roots
    export = tmp_path / 'export-shape'
    exporter.export(source, export, P, work_inputs='current', portable_document=True)
    manifest_path = export / 'release/export-manifest.json'
    pristine = manifest_path.read_bytes()
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / 'state-shape'))
    matrix = {
        'portable_documents is not an object': {'portable_documents': ['bad']},
        "portable_documents['alpha'] is not an object": {'portable_documents': {P: 'bad'}},
        "portable_documents['alpha'].files is not a list": {'portable_documents': {P: {'files': 'x'}}},
        "portable_documents['alpha'].pdf is not null or": {'portable_documents': {P: {'files': [], 'pdf': 'nope'}}},
        "portable_documents['alpha'].compiler is not null or an object": {'portable_documents': {P: {'files': [], 'compiler': []}}},
        "manuscript_links['alpha'].targets has 1 rows": {'manuscript_links': {P: {'targets': [42]}}},
        "manuscript_links is not an object": {'manuscript_links': 'x'},
        "work_inputs['alpha'].rows has 1 rows": {'work_inputs': {P: {'rows': [{'path': 1}]}}},
        "work_inputs['alpha'].rows is not a list": {'work_inputs': {P: {'rows': None}}},
    }
    for expected, patch in matrix.items():
        crafted = json.loads(pristine); crafted.update(patch)
        manifest_path.write_text(json.dumps(crafted))
        result = verifier.verify(export)
        reasons = [row.get('reason') for row in result['failures'] if str(row.get('reason', '')).startswith('portable metadata shape: ')]
        assert not result['ok'] and any(expected in reason for reason in reasons), (expected, result['failures'][:3])
        assert result.get('portable_metadata_shape') == 'malformed' and 'manuscript_links' not in result or result.get('manuscript_links') == {}
    manifest_path.write_bytes(pristine)
    restored = verifier.verify(export)
    assert restored['ok'], restored['failures']


def test_an_omission_is_reconciled_against_the_final_union_of_selections(roots, tmp_path, monkeypatch):
    """PL-C2-R1: eligibility is per Work relationship, inclusion is per final path and pin. A HOLD review of the same
    public path and pin that an accepted review carries is not physically omitted: its omission says this obligation
    did not select it and records the carried relation; the imported facet then reads HOLD/CURRENT because the pin
    travelled. A path only a HOLD review names stays absent and reads STALE after import. An explicit supplementary
    entry for that path reconciles the same way."""
    source, tmp_path, facts = roots
    shared_pin = facts['pin']
    _work(source, 'w-shared', {'id': 'shared', 'scope': 'other', 'label': 'Held review of the shared evidence', 'inputs': ['evidence/alpha-other.txt']},
          pins={'evidence/alpha-other.txt': shared_pin}, verdict='HOLD')
    export = tmp_path / 'export-union'
    report = exporter.export(source, export, P, work_inputs='current', portable_document=True)
    assert [row['path'] for row in report['selected_supplementary_sources']] == ['evidence/alpha-other.txt'], 'the shared path travels once, through the accepted review'
    omitted = {row['work_id']: row for row in report['work_input_omissions'][P]}
    shared = omitted['w-shared']
    assert shared['physically_carried'] is True and shared['carried_disposition'] == 'supplementary' and shared['pin_carried'] is True and shared['carried_through'] == ['w-evidence/evidence']
    assert 'did not select the input' in shared['consequence'] and 'travels through w-evidence/evidence' in shared['consequence'] and 'absent' not in shared['consequence']
    assert shared['disposition'] == 'outside-closure', 'the omission keeps the per-relationship disposition it was decided under'
    held = omitted['w-hold']
    assert held['physically_carried'] is False and 'is then absent' in held['consequence'] and not (export / 'evidence/alpha-hold.txt').exists()
    final = {(row['work_id'], row['path']): row['disposition'] for row in report['work_inputs'][P]['rows']}
    assert final[('w-shared', 'evidence/alpha-other.txt')] == 'supplementary' and final[('w-hold', 'evidence/alpha-hold.txt')] == 'outside-closure'
    appendix = (export / report['portable_documents'][P]['appendix']).read_text(encoding='utf-8').replace('\\_', '_')
    listing = (export / report['portable_documents'][P]['html']).read_text(encoding='utf-8')
    assert 'travels through w-evidence/evidence' in appendix and 'travels through w-evidence/evidence' in listing
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / 'state-union'))
    imported = _facets(export)
    assert (imported['w-shared']['status'], imported['w-shared']['currentness']) == ('HOLD', 'CURRENT'), 'the held review of a carried pin stays current'
    assert (imported['w-hold']['status'], imported['w-hold']['currentness']) == ('HOLD', 'STALE'), 'the uniquely omitted held pin is stale'
    assert imported['w-evidence']['currentness'] == 'CURRENT'
    assert verifier.verify(export)['ok']
    # the explicit supplementary variant: the caller carries the held path itself; its omission is reconciled the same way
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / 'state-source'))
    held_pin = _sha((source / 'evidence' / 'alpha-hold.txt').read_bytes())
    explicit = [{'path': str(source / 'evidence' / 'alpha-hold.txt'), 'repository_path': 'evidence/alpha-hold.txt', 'sha256': held_pin, 'reason': 'reviewer asked for the held notes'}]
    second = exporter.export(source, tmp_path / 'export-explicit', P, explicit, work_inputs='current')
    assert sorted(row['path'] for row in second['selected_supplementary_sources']) == ['evidence/alpha-hold.txt', 'evidence/alpha-other.txt']
    held_again = {row['work_id']: row for row in second['work_input_omissions'][P]}['w-hold']
    assert held_again['physically_carried'] is True and held_again['carried_through'] == ['an explicit supplementary entry'] and held_again['pin_carried'] is True
    assert {row['work_id']: row['disposition'] for row in second['work_inputs'][P]['rows'] if row['path'] == 'evidence/alpha-hold.txt'} == {'w-hold': 'supplementary'}
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / 'state-explicit'))
    assert (_facets(tmp_path / 'export-explicit')['w-hold']['status'], _facets(tmp_path / 'export-explicit')['w-hold']['currentness']) == ('HOLD', 'CURRENT')


def _pdf_actions(pdf: Path) -> dict:
    """The actual link actions of a PDF: every URI action target and the count of GoTo destinations, read from the
    decompressed object text (qpdf --qdf --object-streams=disable)."""
    import re as _re
    plain = pdf.with_suffix('.qdf.pdf')
    subprocess.run(['qpdf', '--qdf', '--object-streams=disable', str(pdf), str(plain)], check=True, capture_output=True, timeout=120)
    text = plain.read_bytes().decode('latin-1')
    uris = [_re.sub(r'\\(.)', r'\1', match) for match in _re.findall(r'/URI\s*\((.*?)(?<!\\)\)', text, flags=_re.S)]
    return {'uris': uris, 'goto': len(_re.findall(r'/S\s*/GoTo\b', text)), 'launch': len(_re.findall(r'/S\s*/Launch\b', text))}


@pytest.mark.skipif(not (shutil.which('qpdf') and (shutil.which('latexmk') or shutil.which('pdflatex'))), reason='the actual PDF check needs qpdf and a TeX chain')
def test_the_portable_pdf_links_packaged_and_public_targets_but_carries_no_action_to_a_machine_bound_url(roots):
    """PL-A1: the appendix typesets a machine-bound URL as readable text without a link action; the public external URL
    stays linked, packaged relative targets stay linked and the body references keep their GoTo destinations."""
    source, tmp_path, facts = roots
    export = tmp_path / 'export-pdf-actions'
    report = exporter.export(source, export, P, work_inputs='current', portable_document=True)
    doc = report['portable_documents'][P]
    assert doc['pdf'], json.dumps(doc['compiler'])[:400]
    actions = _pdf_actions(export / doc['pdf']['path'])
    assert actions['launch'] == 0
    assert not any('localhost:8771' in uri for uri in actions['uris']), actions['uris']
    assert 'https://example.org/method' in actions['uris'], actions['uris']
    packaged = [row for row in report['manuscript_links'][P]['targets'] if row['status'] == 'packaged']
    relative = [uri for uri in actions['uris'] if not uri.startswith('http')]
    assert len(relative) == len(packaged), (relative, [row['target'] for row in packaged])
    assert actions['goto'] >= report['manuscript_links'][P]['references_total'], 'every body reference keeps its GoTo destination into the appendix'
    appendix = (export / doc['appendix']).read_text(encoding='utf-8')
    assert '\\nolinkurl{http://localhost:8771' in appendix.replace('\\%', '%') and '\\url{https://example.org/method}' in appendix
    # the URI pass is recorded in the mapping; this PDF needs no change, so the declared bytes are the compiled bytes
    uri_actions = doc['uri_actions']
    assert uri_actions['unchanged'] and uri_actions['compiled_sha256'] == doc['pdf']['sha256'] and uri_actions['kept'].get('external') == 1, uri_actions


def _revtex_available() -> bool:
    if not (shutil.which('qpdf') and shutil.which('pdftotext') and (shutil.which('latexmk') or shutil.which('pdflatex')) and shutil.which('kpsewhich')):
        return False
    return bool(subprocess.run(['kpsewhich', 'revtex4-2.cls'], capture_output=True, text=True, timeout=30).stdout.strip())


def test_the_appendix_destination_stays_out_of_the_heading_argument_and_builds_clean_under_revtex():
    """The generated appendix of a REVTeX manuscript built with 11 TeX errors because each entry heading carried
    \\hypertarget inside the run-in \\paragraph* argument, which REVTeX expands. The destination now follows the
    heading outside its argument: no heading argument holds a destination, a two-column revtex4-2 document with the
    generated appendix builds through the declared chain with no TeX error, and each named destination lands at its
    own heading (same page, same column, at the heading line), so the body links stay navigable."""
    import re as _re
    targets = [{'ordinal': 1, 'label': 'Public method page', 'kind': 'external', 'url': 'https://example.org/method', 'status': 'external',
                'reason': 'a canonical URL on a public host; it is kept as written', 'references': [{'heading': 'Body', 'file': 'paper/main.tex', 'line': 7, 'kind': 'paragraph'}]},
               {'ordinal': 2, 'label': 'Machine-bound app', 'kind': 'unavailable', 'url': 'http://localhost:8771/project?corpus=alpha', 'host': 'localhost:8771', 'status': 'unavailable',
                'references': [{'heading': 'Body', 'file': 'paper/main.tex', 'line': 8, 'kind': 'paragraph'}]}]
    appendix = portable._appendix_tex('first', {'targets': targets}, {'rows': []}, [], 'paper/portable-links.tex').decode('utf-8')
    headings = _re.findall(r'\\paragraph\*\{(.*?)\}(?=\\hypertarget|\s*$)', appendix, flags=_re.M)
    assert len(headings) == 2 and not any('hypertarget' in heading for heading in headings), appendix
    assert appendix.count('\\hypertarget{portable-link-1}{}') == 1 and appendix.count('\\hypertarget{portable-link-2}{}') == 1, appendix
    if not _revtex_available():
        pytest.skip('the REVTeX build check needs revtex4-2, a TeX chain, qpdf and pdftotext')
    main = '\n'.join([r'\documentclass[reprint,aps,prx,superscriptaddress,nofootinbib]{revtex4-2}', r'\usepackage{hyperref}', r'\begin{document}',
                      r'\title{Fixture}', r'\author{A. Author}', r'\maketitle', r'\section{Body}',
                      r'See \protect\hyperlink{portable-link-1}{the method} for the procedure.',
                      r'The authoring view is \protect\hyperlink{portable-link-2}{the app}.', r'\input{portable-links}', r'\end{document}', ''])
    built = portable.compile_portable({'paper/main.tex': main.encode('utf-8'), 'paper/portable-links.tex': appendix.encode('utf-8')}, 'paper/main.tex')
    assert built['ok'] and built['errors'] == [], json.dumps({k: v for k, v in built.items() if k != 'pdf'})[:1200]
    import tempfile
    with tempfile.TemporaryDirectory(prefix='laplace-revtex-appendix-') as scratch:
        pdf = Path(scratch) / 'main.pdf'; pdf.write_bytes(built['pdf'])
        plain = pdf.with_suffix('.qdf.pdf')   # qdf renumbers objects: pages and destinations are both read from this one file
        subprocess.run(['qpdf', '--qdf', '--object-streams=disable', str(pdf), str(plain)], check=True, capture_output=True, timeout=120)
        text = plain.read_bytes().decode('latin-1')
        pages = {int(obj): int(index) for index, obj in _re.findall(r'page (\d+): (\d+) 0 R', subprocess.run(['qpdf', '--show-pages', str(plain)], capture_output=True, text=True, timeout=60).stdout)}
        bbox = subprocess.run(['pdftotext', '-bbox', str(pdf), '-'], capture_output=True, text=True, timeout=60).stdout
        # bookmarks carry GoTo actions too; the body links are the GoTo actions whose destination is a portable-link name
        assert sorted(_re.findall(r'/D\s*\((portable-link-[12])\)\s*/S\s*/GoTo\b', text)) == ['portable-link-1', 'portable-link-2'], 'both body links keep their GoTo into the appendix'
        height = float(_re.search(r'<page width="[\d.]+" height="([\d.]+)"', bbox).group(1))
        for ordinal, word in ((1, 'Public'), (2, 'Machine-bound')):
            ref = _re.search(r'\(portable-link-%d\)\s*(\d+) 0 R' % ordinal, text).group(1)
            dest = _re.search(r'^%s 0 obj\s*<<\s*/D\s*\[\s*(\d+) 0 R\s*/XYZ\s+([\d.]+)\s+([\d.]+)' % ref, text, flags=_re.M)
            assert dest, 'portable-link-%d is a named destination' % ordinal
            page, x, y = pages[int(dest.group(1))], float(dest.group(2)), float(dest.group(3))
            heading = None
            for number, body in enumerate(_re.split(r'<page ', bbox)[1:], start=1):
                found = _re.search(r'xMin="([\d.]+)" yMin="[\d.]+" xMax="[\d.]+" yMax="([\d.]+)">%s</word>' % _re.escape(word), body)
                if found:
                    heading = (number, float(found.group(1)), height - float(found.group(2)))
            assert heading, word
            assert page == heading[0] and abs(x - heading[1]) < 40 and 0 <= y - heading[2] < 30, ('portable-link-%d' % ordinal, (page, x, y), heading)


def test_the_derived_pdf_keeps_each_relative_link_meaning_and_carries_no_machine_bound_action():
    """FC-R1: a relative URI action means a file beside the ORIGINAL PDF; once the PDF is relocated under portable/<project>/
    the same spelling misses. The URI pass names the same selected file (at its pin) from the derived PDF, keeping its
    fragment; a relative link to a file this export does not carry, a loopback URL written with \\url and an absolute path
    lose their link action while their printed text stays; a public URL, an already-portable neighbour and the internal
    body link stay as they were; a PDF that needs no change keeps its exact bytes."""
    import re as _re
    decide = lambda uri: portable.uri_disposition(uri, derived_pdf='portable/p/paper/main.pdf', original_pdf='paper/main.pdf',
                                                  admitted={'notes/a.md': 'sha256:' + 'a' * 64}, present={'notes/a.md', 'portable/p/paper/data.csv'})
    assert decide('../notes/a.md#sec')['to'] == '../../../notes/a.md#sec' and decide('../notes/a.md#sec')['sha256'] == 'sha256:' + 'a' * 64
    # (a .pdf neighbour would be a GoToR action, not a URI action: the pass handles URI actions)
    assert decide('data.csv')['disposition'] == 'portable' and decide('https://example.org/x')['disposition'] == 'external' and decide('#top')['disposition'] == 'same-document'
    for uri in ('../notes/missing.md', '../../../outside.md', '/research/artifact?project=p', 'file:///home/author/a.md', 'http://127.0.0.1:8771/project?workspace=writing', 'http://localhost/x'):
        assert decide(uri)['disposition'] == 'unavailable', uri
    if not (shutil.which('qpdf') and shutil.which('pdftotext') and (shutil.which('latexmk') or shutil.which('pdflatex'))):
        pytest.skip('the compiled-PDF check needs qpdf, pdftotext and a TeX chain')
    main = '\n'.join([r'\documentclass{article}', r'\usepackage{hyperref}', r'\begin{document}', r'\section{Body}\label{body}',
                      r'Selected: \href{../notes/a.md#sec}{the notes}. Uncarried: \href{../notes/missing.md}{lost notes}.',
                      r'Neighbour: \href{data.csv}{the data}. Public: \href{https://example.org/method}{method page}.',
                      r'Operational: \url{http://127.0.0.1:8771/project?workspace=writing}. Back to \hyperref[body]{the body}.', r'\end{document}', ''])
    built = portable.compile_portable({'paper/main.tex': main.encode('utf-8')}, 'paper/main.tex')
    assert built['ok'], json.dumps({k: v for k, v in built.items() if k != 'pdf'})[:800]
    kwargs = dict(derived_pdf='portable/p/paper/main.pdf', original_pdf='paper/main.pdf', admitted={'notes/a.md': 'sha256:' + 'a' * 64},
                  present={'notes/a.md', 'portable/p/paper/data.csv'})
    result = portable.relocate_uri_actions(built['pdf'], **kwargs)
    assert result['ok'], result['record']
    record = result['record']
    assert [(row['uri'], row['to'], row['target']) for row in record['rebased']] == [('../notes/a.md#sec', '../../../notes/a.md#sec', 'notes/a.md')]
    # a link broken across lines is one annotation per line piece, so the loopback URL may appear more than once
    assert sorted({row['uri'] for row in record['unavailable']}) == ['../notes/missing.md', 'http://127.0.0.1:8771/project?workspace=writing']
    assert record['kept'] == {'portable': 1, 'external': 1} and record['compiled_sha256'] == portable._sha(built['pdf']) and not record['unchanged']
    import tempfile
    with tempfile.TemporaryDirectory(prefix='laplace-uri-pass-') as scratch:
        facts = {}
        for name, raw in (('compiled', built['pdf']), ('relocated', result['pdf'])):
            pdf = Path(scratch) / (name + '.pdf'); pdf.write_bytes(raw)
            text = subprocess.run(['qpdf', '--qdf', '--object-streams=disable', str(pdf), '-'], capture_output=True, timeout=120).stdout.decode('latin-1')
            facts[name] = {'uris': sorted(_re.findall(r'/URI \((.*?)\)', text)), 'goto': len(_re.findall(r'/S /GoTo\b', text)),
                           'text': subprocess.run(['pdftotext', str(pdf), '-'], capture_output=True, timeout=120).stdout}
    assert facts['relocated']['uris'] == sorted(['../../../notes/a.md\\#sec', 'data.csv', 'https://example.org/method']) or \
           facts['relocated']['uris'] == sorted(['../../../notes/a.md#sec', 'data.csv', 'https://example.org/method']), facts['relocated']['uris']
    assert facts['relocated']['goto'] == facts['compiled']['goto'] >= 1 and facts['relocated']['text'] == facts['compiled']['text']
    assert b'127.0.0.1:8771/project' in facts['relocated']['text'] and b'lost notes' in facts['relocated']['text']
    loopback = 'http://127.0.0.1:8771/project?workspace=writing'
    assert facts['compiled']['uris'].count(loopback) == sum(row['uri'] == loopback for row in record['unavailable']) >= 1, 'every line piece of the loopback link loses its action'
    unchanged = portable.relocate_uri_actions(result['pdf'], **kwargs)
    assert unchanged['ok'] and unchanged['record']['unchanged'] and unchanged['pdf'] == result['pdf'] and unchanged['record']['kept'] == {'portable': 2, 'external': 1}
