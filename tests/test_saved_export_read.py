"""A saved export PDF is read by its own exact receipt (repair1 RP-R5, 2026-10-16).

export_pdf issues /projection/pdf?file=<exports/...pdf>&corpus=<project>; that saved artifact is not the selected
current manuscript output, so the compile-root membership of today's source must not decide it. The read verifies
the project's registered home, the sibling receipt's project/file/self identity and the recorded pin before serving,
and keeps every path fence. Disposable fixtures only.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from laplace.manuscript import document_style, projection_viewer


@pytest.fixture
def saved(tmp_path, monkeypatch):
    base = tmp_path / 'book/manuscript'; base.mkdir(parents=True)
    registry = {'projects': [
        {'name': 'book', 'project_dir': 'book', 'tex_root': 'book/manuscript',
         'manifest': {'document': {'root': 'book/manuscript/main.tex', 'edition': 'draft'}}},
        {'name': 'other', 'project_dir': 'other', 'tex_root': 'other/manuscript'}]}
    (tmp_path / 'registry_projects.json').write_text(json.dumps(registry))
    (tmp_path / 'other/manuscript').mkdir(parents=True)
    (base / 'main.tex').write_text('\\documentclass{article}\n\\begin{document}Current edition.\\end{document}\n')
    (base / 'main.pdf').write_bytes(b'%PDF-current-selected-edition')
    build = {'id': 'recompile', 'producer': 'fixture latexmk', 'state': 'done', 'ok': True, 'fresh': True, 'running': False,
             'pdf': 'book/manuscript/main.pdf', 'by': 'author', 'started': 10, 'finished': 11, 'built_ts': 11,
             'dependency_changes': [], 'reason': None}
    monkeypatch.setattr('laplace.manuscript.projection_viewer.recompile_status', lambda *_args, **_kwargs: dict(build))
    exported = document_style.export_pdf('book', tmp_path)
    monkeypatch.setattr(projection_viewer, '_repo_root', lambda: tmp_path)
    return tmp_path, exported


def _get(query):
    return projection_viewer.handle('/projection/pdf', {key: [value] for key, value in query.items()}, 'GET', b'')


def _issued(exported):
    return {key: values[0] for key, values in parse_qs(urlsplit(exported['url']).query).items()}


def _refusal(response):
    status, _ctype, body = response
    return status, json.loads(body).get('reason')


def test_the_owner_issued_url_and_the_earlier_embedded_url_read_the_exact_saved_bytes(saved):
    root, exported = saved
    issued = _issued(exported)
    assert issued == {'file': exported['file'], 'corpus': 'book', 'export_receipt': exported['receipt']}
    status, ctype, body = _get(issued)
    assert (status, ctype) == (200, 'application/pdf') and body == (root / exported['file']).read_bytes()
    legacy = {'file': exported['file'], 'corpus': 'book'}   # the form already embedded in existing papers
    assert _get(legacy)[2] == body
    assert (root / 'book/manuscript/main.pdf').read_bytes() == b'%PDF-current-selected-edition', 'the current PDF is untouched'


def test_the_export_stays_readable_after_another_current_source_is_selected(saved):
    root, exported = saved
    registry = json.loads((root / 'registry_projects.json').read_text())
    (root / 'book/manuscript/v2').mkdir()
    (root / 'book/manuscript/v2/main.tex').write_text('\\documentclass{article}\\begin{document}Next.\\end{document}\n')
    registry['projects'][0]['manifest']['document']['root'] = 'book/manuscript/v2/main.tex'
    (root / 'registry_projects.json').write_text(json.dumps(registry))
    status, _ctype, body = _get(_issued(exported))
    assert status == 200 and body == (root / exported['file']).read_bytes()


@pytest.mark.parametrize('case', ['wrong-project', 'wrong-path', 'wrong-receipt-name', 'receipt-changed', 'receipt-missing',
                                  'pin-changed', 'private', 'symlink-escape', 'stale-inspection'])
def test_every_mismatch_refuses_before_serving(saved, tmp_path, case):
    root, exported = saved
    query = _issued(exported)
    want = {'wrong-project': 'export-project-mismatch', 'wrong-path': 'export-receipt-missing',
            'wrong-receipt-name': 'export-receipt-mismatch', 'receipt-changed': 'export-receipt-mismatch',
            'receipt-missing': 'export-receipt-missing', 'pin-changed': 'export-pin-changed',
            'private': 'export-path-refused', 'symlink-escape': 'export-path-refused',
            'stale-inspection': 'output-revision-conflict'}[case]
    if case == 'wrong-project':
        query['corpus'] = 'other'
    elif case == 'wrong-path':
        query = {'file': str(Path(exported['file']).with_name('similar-name.pdf')), 'corpus': 'book'}
        (root / query['file']).write_bytes(b'%PDF-similar')
    elif case == 'wrong-receipt-name':
        query['export_receipt'] = 'book/manuscript/exports/another.json'
    elif case == 'receipt-changed':
        receipt = json.loads((root / exported['receipt']).read_text())
        receipt['exported_file'] = 'book/manuscript/exports/another.pdf'
        (root / exported['receipt']).write_text(json.dumps(receipt))
    elif case == 'receipt-missing':
        (root / exported['receipt']).unlink()
    elif case == 'pin-changed':
        (root / exported['file']).write_bytes(b'%PDF-altered')
    elif case == 'private':
        (root / 'book/private/exports').mkdir(parents=True)
        (root / 'book/private/exports/x.pdf').write_bytes(b'%PDF-private')
        query = {'file': 'book/private/exports/x.pdf', 'corpus': 'book'}
    elif case == 'symlink-escape':
        outside = tmp_path.parent / (tmp_path.name + '-outside.pdf'); outside.write_bytes(b'%PDF-OUTSIDE-SENTINEL')
        link = root / 'book/manuscript/exports/link.pdf'; os.symlink(outside, link)
        forged = {'project': 'book', 'exported_file': 'book/manuscript/exports/link.pdf',
                  'export_receipt': 'book/manuscript/exports/link.json',
                  'pdf_sha256': __import__('hashlib').sha256(b'%PDF-OUTSIDE-SENTINEL').hexdigest()}
        (root / 'book/manuscript/exports/link.json').write_text(json.dumps(forged))
        query = {'file': 'book/manuscript/exports/link.pdf', 'corpus': 'book'}
    else:
        query['expected_content_revision'] = 'sha256:' + '0' * 64
    assert _refusal(_get(query)) == (409, want)


def test_the_selected_current_pdf_keeps_its_compile_root_membership_rule(saved):
    root, _exported = saved
    (root / 'book/manuscript/older.pdf').write_bytes(b'%PDF-arbitrary-old-file')
    status, _ctype, body = _get({'file': 'book/manuscript/older.pdf', 'corpus': 'book'})
    assert status == 409 and json.loads(body)['reason'].startswith('compile-root'), body



# repair2 (Sol RP-R5-R1): an explicit export_receipt selects the saved owner and never falls back to a current PDF
@pytest.mark.parametrize('case,want', [('current-file', 'export-project-mismatch'), ('other-saved-file', 'export-receipt-mismatch'),
                                       ('nonexistent-receipt', 'export-project-mismatch'), ('missing-corpus', 'export-project-missing'),
                                       ('with-compile-root', 'export-selector-conflict'), ('with-build-target', 'export-selector-conflict'),
                                       ('legacy-with-compile-root', 'export-selector-conflict')])
def test_an_explicit_saved_receipt_never_falls_back_to_a_current_or_build_pdf(saved, case, want):
    root, exported = saved
    query = _issued(exported)
    if case == 'current-file':
        query['file'] = 'book/manuscript/main.pdf'
    elif case == 'other-saved-file':
        other = Path(exported['file']).with_name('another.pdf').as_posix(); (root / other).write_bytes(b'%PDF-other')
        query['file'] = other
    elif case == 'nonexistent-receipt':
        query = {'file': 'book/manuscript/main.pdf', 'corpus': 'book', 'export_receipt': 'book/manuscript/exports/does-not-exist.json'}
    elif case == 'missing-corpus':
        del query['corpus']
    elif case == 'with-compile-root':
        query['compile_root'] = 'book/manuscript/main.tex'
    elif case == 'with-build-target':
        query['build_target'] = 'anything'
    else:
        query = {'file': exported['file'], 'corpus': 'book', 'compile_root': 'book/manuscript/main.tex'}
    status, _ctype, body = _get(query)
    assert (status, json.loads(body).get('reason')) == (409, want)
    assert body != (root / 'book/manuscript/main.pdf').read_bytes()


def test_the_plain_current_pdf_and_both_saved_url_forms_keep_their_outcomes(saved):
    root, exported = saved
    assert _get(_issued(exported))[2] == (root / exported['file']).read_bytes()
    assert _get({'file': exported['file'], 'corpus': 'book'})[2] == (root / exported['file']).read_bytes()
    status, ctype, body = _get({'file': 'book/manuscript/main.pdf'})
    assert (status, ctype, body) == (200, 'application/pdf', b'%PDF-current-selected-edition'), 'plain current PDF unchanged'
