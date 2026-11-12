"""A fresh partial PDF cannot hide a required bibliography/TeX phase failure."""
from pathlib import Path

import pytest

from laplace.manuscript import projection_viewer as viewer


def fixture(tmp_path, monkeypatch, *, bib_ok=True, tex_failure=None):
    path = tmp_path / 'main.tex'
    path.write_text('\\documentclass{article}\n\\begin{document}\nText.\n\\end{document}\n')
    path.with_suffix('.aux').write_text('\\bibdata{references}\n')
    path.with_suffix('.bbl').write_text('Previous successful bibliography.\n')
    calls = []
    tex_pass = 0
    monkeypatch.setattr(viewer, '_latexmk_bin', lambda: 'latexmk')
    monkeypatch.setattr(viewer, '_pdflatex_bin', lambda: 'pdflatex')
    monkeypatch.setattr(viewer, '_bibtex_bin', lambda: 'bibtex')

    def run(command, cwd, timeout):
        nonlocal tex_pass
        calls.append(command[0])
        if command[0] == 'latexmk':
            return False, '__MISSING__ latexmk'
        if command[0] == 'bibtex':
            return (True, 'Bibliography built.') if bib_ok else (False, 'BibTeX rejected references.bib')
        tex_pass += 1
        # TeX often leaves an apparently fresh PDF even after an error, and
        # can compile against an obsolete .bbl despite a failed BibTeX run.
        path.with_suffix('.pdf').write_bytes(b'%PDF-1.5\npartial fixture\n')
        return tex_pass != tex_failure, f'TeX pass {tex_pass}'

    monkeypatch.setattr(viewer, '_run', run)
    return path, calls


def test_bibliography_failure_refuses_fresh_pdf_and_retains_diagnostic(tmp_path, monkeypatch):
    path, calls = fixture(tmp_path, monkeypatch, bib_ok=False)
    result = viewer.compile_tex('main.tex', repo_root=tmp_path)
    assert result['ok'] is False and result['pdf'] is None
    assert 'BibTeX rejected references.bib' in result['log_tail']
    assert calls == ['latexmk', 'pdflatex', 'bibtex']
    assert path.with_suffix('.bbl').read_text() == 'Previous successful bibliography.\n'


@pytest.mark.parametrize('phase', [1, 2, 3])
def test_required_tex_failure_cannot_be_replaced_by_later_success(tmp_path, monkeypatch, phase):
    path, calls = fixture(tmp_path, monkeypatch, tex_failure=phase)
    ok, log = viewer._pdflatex_sequence(path, tmp_path)
    assert not ok and f'TeX pass {phase}' in log
    assert calls.count('pdflatex') == phase


def test_successful_fallback_retains_bibliography_log_and_all_passes(tmp_path, monkeypatch):
    path, calls = fixture(tmp_path, monkeypatch)
    ok, log = viewer._pdflatex_sequence(path, tmp_path)
    assert ok and 'Bibliography built.' in log
    assert calls == ['pdflatex', 'bibtex', 'pdflatex', 'pdflatex']
