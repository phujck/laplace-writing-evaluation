"""Empty canonical project homes survive a file-only Git/ZIP export (empty state homes, 2026-10-16).

Three imported projects of the research collection have a registered home with no exportable authored file (their
selected TeX lives elsewhere; the home held at most a runtime lock). A file-only export dropped those directories and
the re-export refused "registered project directory is missing". The exporter now writes a generated, declared
project-home marker into such a home; the manifest walk never counts it as authored, a different file at that reserved
path refuses, and the verifier checks homes and markers. Disposable fixtures only.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from test_writing_release_portability import _imported, _sha, exporter, m, verifier, write
from test_writing_eval_manifest import fixture

MARKER = 'writing_projects/imported/' + m.HOME_MARKER
TEX = '\\documentclass{article}\\begin{document}Imported text.\\end{document}\n'


def _empty_home_source(tmp_path):
    root = tmp_path / 'source'; root.mkdir(parents=True)
    intents = _imported(root, TEX)
    (root / 'writing_projects/imported/notes.md').unlink()
    (root / 'writing_projects/imported/.authoring.lock').write_text('runtime lock, never exported')
    return root, intents


def test_an_empty_separate_home_travels_as_its_declared_generated_marker_and_metadata_stays_unauthored(tmp_path):
    root, intents = _empty_home_source(tmp_path)
    target = tmp_path / 'export'
    report = exporter.export_projects(root, target, ['imported'], intents=intents)
    assert (target / MARKER).read_bytes() == exporter.inventory.home_marker('imported', 'writing_projects/imported')
    derived = {row['path']: row for row in report['derived_files']}
    assert derived[MARKER]['sha256'] == _sha(target / MARKER) and 'not authored research' in derived[MARKER]['derivation']
    assert MARKER not in {row['path'] for row in report['copied_files']}
    assert sorted(p.name for p in (target / 'writing_projects/imported').iterdir()) == [m.HOME_MARKER], 'nothing fabricated'
    assert (target / 'papers/imported/tex/main.tex').read_text() == TEX, 'the selected source is copied as before'
    verified = verifier.verify(target)
    assert verified['ok'], verified['failures']
    assert set(verified['per_project']['imported']['authored_metadata'].values()) == {'UNAUTHORED'}


def test_the_export_re_exports_directly_and_through_a_git_zip_archive(tmp_path):
    root, intents = _empty_home_source(tmp_path)
    first = tmp_path / 'first'
    exporter.export_projects(root, first, ['imported'], intents=intents)
    again = tmp_path / 'again'
    report = exporter.export_projects(first, again, ['imported'], intents=intents)
    assert (again / MARKER).read_bytes() == (first / MARKER).read_bytes(), 'the marker is regenerated, never copied as authored'
    assert MARKER not in {row['path'] for row in report['copied_files']}
    assert verifier.verify(again)['ok']
    if shutil.which('git') is None:
        pytest.skip('git unavailable')
    git = lambda *args: subprocess.run(['git', '-c', 'user.email=t@example.org', '-c', 'user.name=t', *args], cwd=first,
                                       check=True, capture_output=True)
    git('init', '-q'); git('add', '-A'); git('commit', '-q', '-m', 'export')
    archive = tmp_path / 'export.zip'
    git('archive', '--format=zip', '-o', str(archive), 'HEAD')
    unpacked = tmp_path / 'unpacked'
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(unpacked)
    assert (unpacked / MARKER).is_file(), 'the home survives Git and ZIP'
    exporter.export_projects(unpacked, tmp_path / 'from-zip', ['imported'], intents=intents)
    assert verifier.verify(tmp_path / 'from-zip')['ok']
    (unpacked / MARKER).unlink(); (unpacked / 'writing_projects/imported').rmdir()   # the earlier file-only shape
    with pytest.raises(ValueError, match='registered project directory is missing'):
        exporter.export_projects(unpacked, tmp_path / 'without-marker', ['imported'], intents=intents)


def test_a_home_with_an_exported_file_is_unchanged_and_gets_no_marker(tmp_path):
    root = tmp_path / 'source'; root.mkdir(); intents = _imported(root, TEX)
    target = tmp_path / 'export'
    report = exporter.export_projects(root, target, ['imported'], intents=intents)
    assert not (target / MARKER).exists() and (target / 'writing_projects/imported/notes.md').is_file()
    assert not any(row['path'].endswith(m.HOME_MARKER) for row in report['derived_files'])


def test_a_different_file_at_the_reserved_marker_path_refuses_and_a_canonical_one_is_not_authored(tmp_path):
    root, intents = _empty_home_source(tmp_path)
    write(root, MARKER, '{"schema": "laplace.writing-project-home/1", "project": "imported", "note": "authored?"}')
    with pytest.raises(ValueError, match='reserved project-home marker path is not the generated marker'):
        exporter.export_projects(root, tmp_path / 'export', ['imported'], intents=intents)
    assert not (tmp_path / 'export').exists()
    (root / MARKER).write_bytes(exporter.inventory.home_marker('imported', 'writing_projects/imported'))
    report = exporter.export_projects(root, tmp_path / 'export', ['imported'], intents=intents)
    assert MARKER not in {row['path'] for row in report['copied_files']} and MARKER in {row['path'] for row in report['derived_files']}


@pytest.mark.parametrize('case', ['tampered-marker', 'declared-forged-marker', 'missing-home'])
def test_the_verifier_requires_every_selected_home_and_an_exact_declared_marker(tmp_path, case):
    root, intents = _empty_home_source(tmp_path)
    target = tmp_path / 'export'
    exporter.export_projects(root, target, ['imported'], intents=intents)
    if case in {'tampered-marker', 'declared-forged-marker'}:
        (target / MARKER).write_text('{}')
        want = (MARKER, 'project-home marker is not the declared generated marker')
        if case == 'declared-forged-marker':   # the export manifest agrees with the forged bytes: only the content check remains
            path = target / 'release/export-manifest.json'; manifest = json.loads(path.read_text())
            row = next(item for item in manifest['derived_files'] if item['path'] == MARKER)
            row['sha256'] = _sha(target / MARKER); row['bytes'] = (target / MARKER).stat().st_size
            path.write_text(json.dumps(manifest))
    else:
        shutil.rmtree(target / 'writing_projects/imported')
        want = ('writing_projects/imported', 'registered project home is missing from the export')
    assert want in [(row.get('path'), row.get('reason')) for row in verifier.verify(target)['failures']]


# ---------------------------------------------------------------------------------------------- repair1 (Sol EH-R1a/b)

@pytest.mark.parametrize('case', ['other-project', 'other-home', 'malformed', 'canonical-plus-byte'])
def test_a_marker_is_admitted_only_as_the_registered_selected_owners_exact_bytes(tmp_path, case):
    root, intents = _empty_home_source(tmp_path)
    canonical = exporter.inventory.home_marker('imported', 'writing_projects/imported')
    (root / MARKER).write_bytes({'other-project': exporter.inventory.home_marker('different-project', 'writing_projects/imported'),
                                 'other-home': exporter.inventory.home_marker('imported', 'writing_projects/somewhere-else'),
                                 'malformed': b'{not json', 'canonical-plus-byte': canonical + b' '}[case])
    with pytest.raises(ValueError, match='not the generated marker of the selected project registered at that home'):
        exporter.export_projects(root, tmp_path / 'export', ['imported'], intents=intents)
    assert not (tmp_path / 'export').exists()


@pytest.mark.parametrize('child', [True, False])
def test_a_reserved_marker_directory_refuses_before_copy(tmp_path, child):
    root, intents = _empty_home_source(tmp_path)
    (root / MARKER).mkdir()
    if child:
        (root / MARKER / 'note.txt').write_text('ordinary retained content')
    with pytest.raises(ValueError, match='reserved project-home marker path is not a regular file'):
        exporter.export_projects(root, tmp_path / 'export', ['imported'], intents=intents)
    assert not (tmp_path / 'export').exists()


def test_a_deeper_directory_with_the_reserved_name_refuses(tmp_path):
    root = tmp_path / 'source'; root.mkdir(); intents = _imported(root, TEX)
    write(root, 'writing_projects/imported/data/' + m.HOME_MARKER + '/note.txt', 'ordinary content')
    with pytest.raises(ValueError, match='a directory uses the reserved project-home marker name'):
        exporter.export_projects(root, tmp_path / 'export', ['imported'], intents=intents)


@pytest.mark.parametrize('child', [True, False])
def test_the_verifier_reports_a_non_regular_marker_without_reading_it(tmp_path, child):
    root, intents = _empty_home_source(tmp_path)
    target = tmp_path / 'export'
    exporter.export_projects(root, target, ['imported'], intents=intents)
    (target / MARKER).unlink(); (target / MARKER).mkdir()
    if child:
        (target / MARKER / 'note.txt').write_text('injected')
    failures = verifier.verify(target)['failures']   # a finite failure list, never IsADirectoryError
    assert (MARKER, 'project-home marker is not a regular file') in [(row.get('path'), row.get('reason')) for row in failures]


def _nested(root):
    fixture(root)
    registry = json.loads((root / 'registry_projects.json').read_text())
    registry['projects'] += [{'name': 'outer', 'project_dir': 'writing_projects/outer', 'tex_root': 'papers/outer/tex'},
                             {'name': 'inner', 'project_dir': 'writing_projects/outer/inner', 'tex_root': 'papers/inner/tex'}]
    write(root, 'registry_projects.json', registry)
    write(root, 'writing_projects/outer/notes.md', 'Outer authored notes')
    (root / 'writing_projects/outer/inner').mkdir(parents=True)
    for name in ('outer', 'inner'):
        write(root, f'papers/{name}/tex/main.tex', TEX); (root / f'papers/{name}/tex/main.pdf').write_bytes(b'%PDF ' + name.encode())
    return {'outer': 'current-project-snapshot', 'inner': 'current-project-snapshot'}


def test_a_nested_selected_home_keeps_its_own_owner_marker_and_never_becomes_the_outer_projects_file(tmp_path):
    root = tmp_path / 'source'; root.mkdir(); intents = _nested(root)
    inner = 'writing_projects/outer/inner/' + m.HOME_MARKER
    first = tmp_path / 'first'
    exporter.export_projects(root, first, ['outer', 'inner'], intents=intents)
    assert (first / inner).read_bytes() == exporter.inventory.home_marker('inner', 'writing_projects/outer/inner')
    assert not (first / 'writing_projects/outer' / m.HOME_MARKER).exists(), 'the outer home holds an authored file'
    assert verifier.verify(first)['ok']
    report = exporter.export_projects(first, tmp_path / 'again', ['outer', 'inner'], intents=intents)
    assert inner not in {row['path'] for row in report['copied_files']} and inner in {row['path'] for row in report['derived_files']}
    assert verifier.verify(tmp_path / 'again')['ok']
    # without its selected owner the inner marker is not adopted as the outer project's content
    with pytest.raises(ValueError, match='not the generated marker of the selected project registered at that home'):
        exporter.export_projects(first, tmp_path / 'outer-only', ['outer'], intents={'outer': 'current-project-snapshot'})
