"""The portable index stays bounded for a full collection (full-collection index, 2026-10-16).

The 21-project research collection wrote an 8.6 MB writing-portability.json (20,252 aliases; 19,185 of them a copied
file's own current-root spelling, which directory_aliases already resolves to the same exported path, pinned again in
copied_files) and the resolver's 4 MiB guard refused it. The index now lists only aliases that say more than the
directory alias, and carries its proofs beside it, pinned. Resolution of every recorded spelling is unchanged, the
guard is unchanged, and the verifier checks the proofs. Disposable fixtures only.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from laplace.projects import writing_portability
from test_writing_release_portability import _portable_first, exporter, verifier, write
from test_writing_eval_manifest import fixture


def _export(tmp_path, extra_files):
    root = tmp_path / 'source'; root.mkdir(parents=True); fixture(root); _portable_first(root)
    for index in range(extra_files):
        write(root, f'projects/first/results/run-{index:05d}.json', json.dumps({'run': index}))
    target = tmp_path / 'export'
    report = exporter.export_projects(root, target, ['first'])
    return root.resolve(), target, report


def test_the_index_does_not_grow_with_copied_files_and_every_original_spelling_still_resolves(tmp_path):
    _small_root, small, _ = _export(tmp_path / 'small', 0)
    root, target, report = _export(tmp_path / 'large', 2000)
    small_index = json.loads((small / 'writing-portability.json').read_text())
    index = json.loads((target / 'writing-portability.json').read_text())
    assert len(index['source_aliases']) == len(small_index['source_aliases']), 'per-file primaries are not repeated'
    assert index['directory_covered']['files'] - small_index['directory_covered']['files'] == 2000
    assert (target / 'writing-portability.json').stat().st_size < 64 * 1024
    for row in report['copied_files']:
        spelling = str(root / row['path'])
        assert writing_portability.source_path(spelling, target) == (target / row['path']).resolve()
        assert writing_portability.source_path(spelling, target, sha256=row['sha256']) == (target / row['path']).resolve()
    recorded = '/historical/root/projects/first/text/source.txt'
    assert index['source_aliases'][recorded]['path'] == 'projects/first/text/source.txt', 'proven historical aliases stay'
    assert verifier.verify(target)['ok']


def test_resolution_parses_the_index_once_per_identity_and_rereads_only_after_it_changes(tmp_path, monkeypatch):
    root, target, report = _export(tmp_path, 300)
    writing_portability._manifest.cache_clear()
    parses = []
    real = json.loads
    monkeypatch.setattr(writing_portability.json, 'loads', lambda text, *a, **k: (parses.append(len(text)), real(text, *a, **k))[1])
    started = time.perf_counter()
    for row in report['copied_files']:
        writing_portability.source_path(str(root / row['path']), target)
    elapsed = time.perf_counter() - started
    assert len(parses) == 1, 'one bounded parse serves every lookup'
    assert elapsed < 5, elapsed
    index = target / 'writing-portability.json'
    index.write_text(index.read_text() + ' ')   # a new identity (size/mtime/ctime) resets the cached parse
    writing_portability.source_path(str(root / report['copied_files'][0]['path']), target)
    assert len(parses) == 2


def test_the_reader_guard_is_unchanged_and_still_refuses_an_oversized_index(tmp_path):
    (tmp_path / 'writing-portability.json').write_text(json.dumps({'schema': 'laplace.writing-portability/1',
                                                                    'source_aliases': {}, 'pad': 'x' * (4 * 1024 * 1024)}))
    with pytest.raises(ValueError, match='portable source manifest exceeds size limit'):
        writing_portability.source_path('/original/a.txt', tmp_path)


@pytest.mark.parametrize('case', ['tampered', 'missing', 'count'])
def test_the_verifier_checks_the_proofs_carried_beside_the_index(tmp_path, case):
    _root, target, _report = _export(tmp_path, 0)
    proofs = target / 'release/alias-proofs.json'
    manifest_path = target / 'release/export-manifest.json'
    manifest = json.loads(manifest_path.read_text())
    row = next(item for item in manifest['derived_files'] if item['path'] == 'release/alias-proofs.json')
    if case == 'missing':
        proofs.unlink()
        want = 'alias proofs are not the declared exported file named by the index'
    else:
        value = json.loads(proofs.read_text())
        if case == 'tampered':
            value['proofs'] = [*value['proofs'], {'recorded': '/forged', 'path': 'x'}]
            want = 'alias proofs are not the declared exported file named by the index'   # the index pin no longer matches
        else:
            value['proofs'] = value['proofs'][:-1] if value['proofs'] else [{'recorded': '/forged'}]
            want = 'alias proofs do not match the portability index'
        proofs.write_text(json.dumps(value))
        # keep the export manifest consistent with the new bytes so ONLY the index's own pin/count can catch it
        row['sha256'] = 'sha256:' + __import__('hashlib').sha256(proofs.read_bytes()).hexdigest(); row['bytes'] = proofs.stat().st_size
        manifest_path.write_text(json.dumps(manifest))
        if case == 'count':
            index_path = target / 'writing-portability.json'
            index = json.loads(index_path.read_text()); index['alias_proofs']['sha256'] = row['sha256']
            index_path.write_text(json.dumps(index))
            row = next(item for item in manifest['derived_files'] if item['path'] == 'writing-portability.json')
            row['sha256'] = 'sha256:' + __import__('hashlib').sha256(index_path.read_bytes()).hexdigest(); row['bytes'] = index_path.stat().st_size
            manifest_path.write_text(json.dumps(manifest))
    reasons = [row.get('reason') for row in verifier.verify(target)['failures']]
    assert want in reasons, reasons
