"""The read-only boot-failure inspection path (Work5, 2026-10-20; boundary correction W5-R1/R2): a real synthetic export is
inspected by the standard-library checker while the candidate kernel is unimportable. One verdict consumes every requested
and declared condition; one admission boundary fences every candidate coordinate before it is opened; no byte, bytecode
included, is written under the inspected root.
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

import pytest

SCRIPTS = Path(__file__).parents[1] / 'scripts'
SPEC = importlib.util.spec_from_file_location('export_writing_evaluation', SCRIPTS / 'export_writing_evaluation.py')
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)
from test_writing_eval_manifest import fixture, write  # noqa: E402
CHECKER_FILES = ('inspect_writing_export.py', 'writing_export_bytes.py')


def _sha(path: Path) -> str:
    return 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()


def _poisoned_kernel(tmp_path: Path) -> Path:
    """A `laplace` package that refuses to import: the candidate kernel that cannot start."""
    poison = tmp_path / 'poison'
    (poison / 'laplace').mkdir(parents=True)
    (poison / 'laplace' / '__init__.py').write_text("raise ImportError('the candidate kernel cannot start')\n")
    (poison / 'atlas').mkdir()
    (poison / 'atlas' / '__init__.py').write_text("raise ImportError('the candidate atlas cannot start')\n")
    return poison


def _checker_copy(target: Path) -> Path:
    """The trusted-checker recipe: the checker files taken from the accepted source, placed outside the candidate (or, for the
    candidate-local control, inside it)."""
    target.mkdir(parents=True, exist_ok=True)
    for name in CHECKER_FILES:
        shutil.copyfile(SCRIPTS / name, target / name)
    return target / 'inspect_writing_export.py'


def _run(checker: Path, root: Path, poison: Path, *extra: str, bytecode_default=False, timeout=60) -> tuple[int, dict, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith('LAPLACE_') and key not in ('PYTHONPATH', 'PYTHONHOME', 'PYTHONDONTWRITEBYTECODE', 'PYTHONPYCACHEPREFIX')}
    env['PYTHONPATH'] = str(poison)
    if not bytecode_default:
        env['PYTHONDONTWRITEBYTECODE'] = '1'
    argv = [sys.executable, '-s', str(checker), '--root', str(root), *extra]
    out = subprocess.run(argv, capture_output=True, text=True, env=env, cwd=str(root.parent), timeout=timeout)
    report = json.loads(out.stdout) if out.stdout.strip() else {}
    return out.returncode, report, out.stderr


def _tree(root: Path) -> dict:
    return {str(p.relative_to(root)): (p.read_bytes() if p.is_file() else ('LINK', os.readlink(p)) if p.is_symlink() else ('OTHER',)) for p in root.rglob('*')}


def _export(tmp_path: Path):
    source = tmp_path / 'source'
    source.mkdir(parents=True)
    fixture(source)
    write(source, 'projects/first/text/source.txt', 'included source')
    refs = json.loads((source / 'projects/first/text/references.json').read_text())
    refs['sources'][0]['source']['path'] = '/historical/root/projects/first/text/source.txt'
    write(source, 'projects/first/text/references.json', refs)
    export = tmp_path / 'export'
    report = exporter.export(source, export, 'first')
    return export, report


@pytest.fixture
def scene(tmp_path):
    export, report = _export(tmp_path)
    poison = _poisoned_kernel(tmp_path)
    trusted = _checker_copy(tmp_path / 'trusted')
    accepted = _sha(export / 'release/export-manifest.json')
    return export, report, poison, trusted, accepted, tmp_path


def test_the_external_checker_reads_a_real_export_without_the_kernel_and_names_every_drift(scene):
    export, report, poison, trusted, accepted, tmp_path = scene
    probe = subprocess.run([sys.executable, '-s', '-c', 'import laplace'], capture_output=True, text=True, env={**os.environ, 'PYTHONPATH': str(poison)})
    assert probe.returncode != 0 and 'cannot start' in probe.stderr
    loaded = subprocess.run([sys.executable, '-s', '-c', 'import importlib.util, sys\n'
                             'spec = importlib.util.spec_from_file_location("i", %r); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n'
                             'print(sorted(k for k in sys.modules if k == "laplace" or k.startswith(("laplace.", "atlas"))))' % str(trusted)],
                            capture_output=True, text=True, env={**os.environ, 'PYTHONPATH': str(poison)})
    assert loaded.returncode == 0 and loaded.stdout.strip() == '[]', loaded.stdout + loaded.stderr
    before = _tree(export)
    # 1. unanchored: the candidate's own claims, consistent, said to be its own claims; the checker names where it ran from
    code, plain, _ = _run(trusted, export, poison)
    assert code == 0 and plain['status'] == 'DECLARED_BYTES_CONSISTENT_UNANCHORED' and plain['kernel'].startswith('not consulted'), plain['discrepancies']
    assert plain['files']['declared'] == len(report['copied_files']) + len(report['derived_files']) and plain['files']['present'] == plain['files']['declared']
    assert plain['manifest']['source_manifest']['identity_match'] is True and plain['trust']['accepted_identity_match'] is None and plain['trust']['mode'] == 'unanchored-self-description'
    assert plain['checker']['location'] == 'outside-candidate' and plain['checker']['files']['inspect_writing_export.py']['sha256'] == _sha(SCRIPTS / 'inspect_writing_export.py')
    assert plain['journal']['sessions'][0] == {'id': 'WS1', 'project': 'first', 'provider': None, 'imported': True, 'bound': False} and plain['journal']['unsupported_kinds'] == {}
    assert plain['refused_count'] == 0 and plain['partial'] is False and _tree(export) == before
    # 2. anchored by the accepted identity supplied from outside: the one success that means acceptance identity
    code, anchored, _ = _run(trusted, export, poison, '--accepted-manifest-sha256', accepted)
    assert code == 0 and anchored['status'] == 'ACCEPTED_IDENTITY_AND_BYTES' and anchored['trust']['accepted_identity_match'] is True
    copy = tmp_path / 'accepted-copy.json'
    shutil.copyfile(export / 'release/export-manifest.json', copy)
    code, both, _ = _run(trusted, export, poison, '--accepted-manifest-sha256', accepted, '--accepted-manifest', str(copy))
    assert code == 0 and both['status'] == 'ACCEPTED_IDENTITY_AND_BYTES' and both['trust']['external_anchor']['copy']['sha256'] == accepted
    # 3. drift: one changed file, one missing file, an unknown journal row kind (the journal is itself a declared file)
    changed = export / 'projects/first/text/main.tex'
    changed.write_text('Edited after export.')
    (export / 'docs/writing-registry.md').unlink()
    with (export / 'contract/talk.jsonl').open('a') as stream:
        stream.write(json.dumps({'record': 'writing-unknown-kind', 'id': 'X1'}) + '\n')
    code, drifted, _ = _run(trusted, export, poison, '--accepted-manifest-sha256', accepted)
    assert code == 2 and drifted['status'] == 'DISCREPANCY' and drifted['partial'] is True
    assert set(drifted['files']['changed']) == {'projects/first/text/main.tex', 'contract/talk.jsonl'} and drifted['files']['missing'] == ['docs/writing-registry.md']
    assert drifted['journal']['unsupported_kinds'] == {'writing-unknown-kind': 1} and drifted['recovery'][0]['step'] == 'restore-declared-bytes'
    assert drifted['trust']['accepted_identity_match'] is True, 'the manifest itself is still the accepted one; its bytes drifted'
    # 4. the candidate rewrites its own manifest to match its drift: self-consistent again, and NOT the accepted export
    manifest_path = export / 'release/export-manifest.json'
    rewritten = json.loads(manifest_path.read_text())
    for row in rewritten['copied_files']:
        if row['path'] == 'projects/first/text/main.tex':
            row['sha256'] = exporter.digest(changed.read_bytes()); row['bytes'] = changed.stat().st_size
    rewritten['copied_files'] = [row for row in rewritten['copied_files'] if row['path'] != 'docs/writing-registry.md']
    rewritten['derived_files'] = [row for row in rewritten['derived_files'] if row['path'] != 'docs/writing-registry.md']
    manifest_path.write_text(json.dumps(rewritten))
    with (export / 'contract/talk.jsonl').open('r+') as stream:
        lines = stream.readlines(); stream.seek(0); stream.truncate(); stream.writelines(line for line in lines if 'writing-unknown-kind' not in line)
    code, self_certified, _ = _run(trusted, export, poison, '--accepted-manifest-sha256', accepted)
    assert self_certified['files']['consistent'] is True and code == 2 and self_certified['trust']['accepted_identity_match'] is False
    assert any('not the accepted one' in d for d in self_certified['discrepancies']) and 'cannot certify itself' in self_certified['trust']['statement']
    code, unanchored, _ = _run(trusted, export, poison)
    assert code == 0 and unanchored['status'] == 'DECLARED_BYTES_CONSISTENT_UNANCHORED' and 'not acceptance' in unanchored['trust']['statement']
    target = os.environ.get('LAPLACE_RECOVERY_EVIDENCE')
    if target:
        Path(target).mkdir(parents=True, exist_ok=True)
        (Path(target) / 'inspection.json').write_text(json.dumps({'plain': plain['status'], 'checker': plain['checker'], 'anchored': anchored['status'], 'both_anchors': both['status'],
                                                                  'drifted': {k: drifted[k] for k in ('status', 'discrepancies')}, 'self_certified': {'files_consistent': self_certified['files']['consistent'], 'status': self_certified['status'], 'trust': self_certified['trust']}}, indent=1))


def test_every_requested_anchor_and_package_condition_decides_the_verdict(scene):
    """W5-R1: a requested anchor that cannot be used, a conflicting pair, a copy inside the candidate, a malformed digest, a
    failed package check and a candidate-local checker with an anchor are all finite non-success; none falls back to the
    unanchored description."""
    export, report, poison, trusted, accepted, tmp_path = scene
    other = tmp_path / 'other-export'
    other_export, _ = _export(tmp_path / 'other')
    outcomes = {}
    # conflicting anchors: a digest and a copy that disagree (the copy is a valid manifest of another export)
    code, conflict, _ = _run(trusted, export, poison, '--accepted-manifest-sha256', accepted, '--accepted-manifest', str(other_export / 'release/export-manifest.json'))
    assert code == 2 and conflict['status'] == 'DISCREPANCY' and any('conflicting anchors' in p for p in conflict['trust']['problems']) and conflict['trust']['accepted_identity_match'] is None
    outcomes['conflicting'] = conflict['trust']['problems']
    # a missing copy
    code, missing, _ = _run(trusted, export, poison, '--accepted-manifest', str(tmp_path / 'absent.json'))
    assert code == 2 and missing['trust']['mode'] == 'anchor-failed' and any('not readable' in p for p in missing['trust']['problems']) and missing['files']['consistent'] is True
    # a malformed copy (readable, not a manifest)
    bad_copy = tmp_path / 'bad-copy.json'; bad_copy.write_text('{"schema": "something-else"}')
    code, malformed_copy, _ = _run(trusted, export, poison, '--accepted-manifest', str(bad_copy))
    assert code == 2 and any('not a supported export manifest' in p for p in malformed_copy['trust']['problems'])
    # a copy that lies inside the candidate: not external authority
    code, inside, _ = _run(trusted, export, poison, '--accepted-manifest', str(export / 'release/export-manifest.json'))
    assert code == 2 and any('inside the candidate' in p for p in inside['trust']['problems']) and inside['trust']['accepted_identity_match'] is None
    # a malformed digest
    code, shape, _ = _run(trusted, export, poison, '--accepted-manifest-sha256', 'sha256:not-a-digest')
    assert code == 2 and any('malformed' in p for p in shape['trust']['problems'])
    # a symlinked copy is not followed
    link = tmp_path / 'copy-link.json'; link.symlink_to(export / 'release/export-manifest.json')
    code, linked, _ = _run(trusted, export, poison, '--accepted-manifest', str(link))
    assert code == 2 and any('symbolic link' in p for p in linked['trust']['problems'])
    # --package is unsupported here (Root's simplification): refused explicitly, and nothing under it is opened (its manifest is a FIFO)
    package = tmp_path / 'package'; package.mkdir(); os.mkfifo(package / 'container-package.json')
    code, unsupported, _ = _run(trusted, export, poison, '--accepted-manifest-sha256', accepted, '--package', str(package), timeout=30)
    assert code == 2 and unsupported['status'] == 'UNSUPPORTED_OPTION' and 'writing_container_package.py' in unsupported['problem']
    # an accepted copy that is a regular file but cannot be read: the read contract's problem reaches the verdict
    unreadable_copy = tmp_path / 'unreadable-copy.json'; shutil.copyfile(export / 'release/export-manifest.json', unreadable_copy); unreadable_copy.chmod(0)
    try:
        code, unreadable, err = _run(trusted, export, poison, '--accepted-manifest', str(unreadable_copy))
    finally:
        unreadable_copy.chmod(0o600)
    assert code == 2 and 'Traceback' not in err and any('could not be read: unreadable: PermissionError' in p for p in unreadable['trust']['problems']), unreadable['trust']
    # the candidate-local checker: self-description is allowed and says so; an anchor requested from it is refused
    local = _checker_copy(export / 'scripts')
    code, local_plain, _ = _run(local, export, poison)
    assert code == 0 and local_plain['status'] == 'DECLARED_BYTES_CONSISTENT_UNANCHORED' and local_plain['checker']['location'] == 'inside-candidate'
    assert 'describe the candidate' in local_plain['checker']['statement']
    code, local_anchored, _ = _run(local, export, poison, '--accepted-manifest-sha256', accepted)
    assert code == 2 and any('checker runs from inside the candidate' in d for d in local_anchored['discrepancies']) and local_anchored['status'] == 'DISCREPANCY'
    outcomes.update(missing=missing['status'], malformed_copy=malformed_copy['status'], inside=inside['status'], shape=shape['status'], linked=linked['status'],
                    package_unsupported=unsupported['status'], unreadable_copy=unreadable['status'], candidate_local_unanchored=local_plain['status'], candidate_local_anchored=local_anchored['status'])
    target = os.environ.get('LAPLACE_RECOVERY_EVIDENCE')
    if target:
        Path(target).mkdir(parents=True, exist_ok=True)
        (Path(target) / 'anchors.json').write_text(json.dumps(outcomes, indent=1))


def test_the_admission_boundary_fences_every_candidate_coordinate_and_shapes_before_consumption(scene):
    """W5-R2: fixed coordinates that are symlinks are refused without an outside open (the targets are FIFOs: an open would
    block), and wrong-shaped metadata yields finite statuses instead of tracebacks."""
    export, report, poison, trusted, accepted, tmp_path = scene
    outside = tmp_path / 'outside'; outside.mkdir()
    fifos = {}
    for rel in ('contract/talk.jsonl', 'registry_projects.json', 'release/source-manifest.json', 'profiles/writing_sources.json', 'corpus_friction/work_orders.jsonl'):
        fifo = outside / rel.replace('/', '__')
        os.mkfifo(fifo)
        fifos[rel] = fifo
        path = export / rel
        if path.exists():
            path.unlink()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(fifo)
    code, fenced, _ = _run(trusted, export, poison, timeout=30)   # a single outside open would block past this timeout
    assert code == 2 and fenced['status'] == 'DISCREPANCY'
    refused = {row['path']: row['problem'] for row in fenced['refused']}
    assert set(refused) >= set(fifos) and all('symbolic link' in refused[rel] for rel in fifos), refused
    assert fenced['journal']['present'] is False and fenced['journal']['rows'] == 0 and fenced['work']['present'] is False
    assert fenced['manifest']['source_manifest']['identity_match'] is False and 'symbolic link' in fenced['manifest']['source_manifest']['problem']
    assert fenced['workspace_inputs']['registry_projects.json']['problem'] and 'symbolic link' in fenced['workspace_inputs']['registry_projects.json']['problem']
    assert any(d.startswith('repository configuration') for d in fenced['discrepancies'])
    for path in list(fifos.values()):
        (export / [k for k, v in fifos.items() if v == path][0]).unlink()
    # a declared row whose target is a directory, and a declared path that climbs out
    manifest_path = export / 'release/export-manifest.json'
    value = json.loads(manifest_path.read_text())
    value['copied_files'].append({'path': 'docs', 'sha256': 'sha256:' + 'a' * 64})
    value['copied_files'].append({'path': '../outside/secret', 'sha256': 'sha256:' + 'b' * 64})
    manifest_path.write_text(json.dumps(value))
    code, declared, _ = _run(trusted, export, poison)
    assert code == 2 and {row['path']: row['problem'] for row in declared['files']['refused']} == {'docs': 'not a regular file', '../outside/secret': 'coordinate is absolute or climbs out of the root'}
    # wrong shapes: each a finite status, never a traceback
    shapes = {}
    for label, text in (('empty-object', '{}'), ('scalar-copied-files', json.dumps({**report, 'copied_files': 1})), ('scalar-projects', json.dumps({**report, 'projects': 1})),
                        ('unsupported-schema', json.dumps({**report, 'schema': 'laplace.writing-evaluation-export/9'})), ('not-an-object', '[1, 2]'), ('not-json', '{not json')):
        manifest_path.write_text(text)
        code, shaped, err = _run(trusted, export, poison)
        assert code == 3 and shaped['status'] == 'MALFORMED' and 'Traceback' not in err, (label, err[-500:])
        shapes[label] = shaped['malformed'][0]['problem'][:80]
    manifest_path.write_text(json.dumps(report))
    (export / 'registry_projects.json').write_text(json.dumps({'projects': 1}))
    (export / 'profiles/writing_sources.json').write_text(json.dumps({'repositories': ['laplace']}))
    (export / 'contract/talk.jsonl').write_text(json.dumps({'record': 'writing-session', 'id': 'WS-good', 'project': 'first'}) + '\n'
                                                + json.dumps({'record': 'writing-session', 'id': ['not', 'a', 'string'], 'project': 'first'}) + '\n')
    code, wrong, err = _run(trusted, export, poison)
    assert code == 2 and wrong['status'] == 'DISCREPANCY' and 'Traceback' not in err
    assert 'malformed: projects must be a list' == wrong['workspace_inputs']['registry_projects.json']['problem']
    assert any('repositories must be an object' in d for d in wrong['discrepancies']) and wrong['journal']['malformed_rows_count'] == 1
    assert wrong['journal']['sessions_total'] == 1, 'the well-formed session row is still counted; the malformed one is named, not guessed'
    shapes['wrong-shapes'] = [d for d in wrong['discrepancies'] if 'malformed' in d or 'repositories' in d][:3]
    # the read contract: admitted regular candidate files whose bytes cannot be read are typed finite problems, never tracebacks
    (export / 'contract/talk.jsonl').write_text(json.dumps({'record': 'writing-session', 'id': 'WS-good', 'project': 'first'}) + '\n')
    (export / 'registry_projects.json').write_text(json.dumps({'projects': [{'name': 'first'}]}))
    (export / 'profiles/writing_sources.json').write_text(json.dumps({'repositories': {'laplace': '.'}}))
    (export / 'release/source-manifest.json').write_text('{}')   # present again (the FIFO control removed it), so the read, not the admission, is what fails
    locked = {rel: export / rel for rel in ('projects/first/text/main.tex', 'contract/talk.jsonl', 'release/source-manifest.json')}
    for path in locked.values():
        path.chmod(0)
    try:
        code, unreadable, err = _run(trusted, export, poison)
    finally:
        for path in locked.values():
            path.chmod(0o644)
    assert code == 2 and 'Traceback' not in err and unreadable['status'] == 'DISCREPANCY', err[-800:]
    assert {row['path']: row['problem'] for row in unreadable['files']['refused']}.items() >= {'projects/first/text/main.tex': 'unreadable: PermissionError', 'contract/talk.jsonl': 'unreadable: PermissionError'}.items()
    assert unreadable['journal']['problem'] == 'unreadable: PermissionError' and unreadable['manifest']['source_manifest']['problem'] == 'unreadable: PermissionError'
    assert unreadable['manifest']['source_manifest']['identity_match'] is False and any('unreadable' in d for d in unreadable['discrepancies'])
    manifest_path.chmod(0)
    try:
        code, unreadable_manifest, err = _run(trusted, export, poison)
    finally:
        manifest_path.chmod(0o644)
    assert code == 3 and unreadable_manifest['status'] == 'MALFORMED' and unreadable_manifest['malformed'][0]['problem'] == 'unreadable: PermissionError' and 'Traceback' not in err
    shapes['unreadable'] = {'declared': unreadable['files']['refused'], 'journal': unreadable['journal']['problem'], 'manifest': unreadable_manifest['malformed'][0]}
    target = os.environ.get('LAPLACE_RECOVERY_EVIDENCE')
    if target:
        Path(target).mkdir(parents=True, exist_ok=True)
        (Path(target) / 'boundary.json').write_text(json.dumps({'fenced': {'status': fenced['status'], 'refused': refused, 'journal_rows': fenced['journal']['rows']}, 'declared_refused': declared['files']['refused'], 'shapes': shapes}, indent=1))


def test_cold_invocation_writes_no_bytecode_under_the_candidate_or_the_trusted_location(tmp_path):
    """W5-R2: the documented in-export invocation and the trusted external checker, each from a fresh directory with no cache
    and the interpreter's default bytecode behaviour, leave both trees unchanged."""
    export, _ = _export(tmp_path)
    poison = _poisoned_kernel(tmp_path)
    local = _checker_copy(export / 'scripts')
    trusted = _checker_copy(tmp_path / 'trusted')
    accepted = _sha(export / 'release/export-manifest.json')
    assert not list(export.rglob('__pycache__')) and not list((tmp_path / 'trusted').rglob('__pycache__'))
    before_export, before_trusted = _tree(export), _tree(tmp_path / 'trusted')
    code, local_report, err = _run(local, export, poison, bytecode_default=True)
    assert code == 0 and local_report['checker']['location'] == 'inside-candidate', err[-500:]
    code, trusted_report, err = _run(trusted, export, poison, '--accepted-manifest-sha256', accepted, bytecode_default=True)
    assert code == 0 and trusted_report['status'] == 'ACCEPTED_IDENTITY_AND_BYTES', err[-500:]
    assert _tree(export) == before_export and _tree(tmp_path / 'trusted') == before_trusted
    assert not list(export.rglob('__pycache__')) and not list((tmp_path / 'trusted').rglob('__pycache__'))
    assert 'bytecode writing disabled' in trusted_report['writes'] and set(trusted_report['checker']['files']) == set(CHECKER_FILES)
