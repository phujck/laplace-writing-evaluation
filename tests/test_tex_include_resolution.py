"""One TeX include contract for source traversal, membership guards, outline and the build closure
(WORK-editor-tex-include-resolution-20261016, M5 2026-10-16).

TeX runs in the selected root's directory and resolves a relative \\input/\\include against it; the including file's
directory is not searched. The reached case: tex_v4/main.tex inputs sections/H.tex, which inputs tikz/fig.tex that
lives at tex_v4/tikz/fig.tex. Disposable synthetic trees only; no real project is read or copied.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from laplace.manuscript import manuscript_source, projection_viewer, tex_dependencies

ROOT = '\\documentclass{article}\n\\begin{document}\n\\input{sections/H}\n\\end{document}\n'


def _tree(tmp_path, files):
    base = tmp_path / 'paper' / 'tex_v4'
    for name, text in {'main.tex': ROOT, **files}.items():
        (base / name).parent.mkdir(parents=True, exist_ok=True)
        (base / name).write_text(text)
    return base


def _traverse(tmp_path, base):
    return manuscript_source.traversal(base / 'main.tex', repo_root=tmp_path)


def test_a_nested_input_resolves_against_the_compilation_directory_everywhere(tmp_path):
    base = _tree(tmp_path, {'sections/H.tex': 'Text.\n\\input{tikz/fig}\n\\input{tikz/net.tex}\n',
                            'tikz/fig.tex': 'figure', 'tikz/net.tex': 'network'})
    tree = _traverse(tmp_path, base)
    assert tree['diagnostics'] == []
    assert tree['files'] == ['paper/tex_v4/main.tex', 'paper/tex_v4/sections/H.tex', 'paper/tex_v4/tikz/fig.tex', 'paper/tex_v4/tikz/net.tex']
    assert [row['target'] for row in tree['includes']] == ['paper/tex_v4/sections/H.tex', 'paper/tex_v4/tikz/fig.tex', 'paper/tex_v4/tikz/net.tex']
    # the membership guard admits the nested member (it refused compile-root-membership-unproved before)
    scope = projection_viewer._compile_scope(base / 'tikz' / 'fig.tex', compile_root='paper/tex_v4/main.tex', repo_root=tmp_path)
    assert scope['compile_root'] == 'paper/tex_v4/main.tex'
    # the build closure declares the same members
    closure = tex_dependencies.prepare_closure('p', tmp_path, {'root': 'paper/tex_v4/main.tex'}, {})
    members = set(closure['members']) if isinstance(closure.get('members'), dict) else {row['path'] for row in closure['members']}
    assert {'paper/tex_v4/sections/H.tex', 'paper/tex_v4/tikz/fig.tex', 'paper/tex_v4/tikz/net.tex'} <= members
    assert not [d for d in closure.get('diagnostics', []) if d.get('code') in {'MISSING_DECLARATION', 'AMBIGUOUS_DECLARATION'}]


def test_an_include_only_relative_to_the_including_file_is_missing_with_a_hint(tmp_path):
    base = _tree(tmp_path, {'sections/H.tex': '\\input{tikz/fig}\n', 'sections/tikz/fig.tex': 'not read by TeX'})
    tree = _traverse(tmp_path, base)
    missing = [d for d in tree['diagnostics'] if d['kind'] == 'missing-include']
    assert len(missing) == 1 and missing[0]['target'] == 'paper/tex_v4/tikz/fig.tex' and missing[0]['alternate'] == 'paper/tex_v4/sections/tikz/fig.tex'
    with pytest.raises(projection_viewer.CompileRootRefused):
        projection_viewer._compile_scope(base / 'sections' / 'H.tex', compile_root='paper/tex_v4/main.tex', repo_root=tmp_path)
    closure = tex_dependencies.prepare_closure('p', tmp_path, {'root': 'paper/tex_v4/main.tex'}, {})
    row = next(d for d in closure['diagnostics'] if d.get('code') == 'MISSING_DECLARATION')
    assert row['paths'] == ['paper/tex_v4/tikz/fig.tex'] and row['including_relative'] == 'paper/tex_v4/sections/tikz/fig.tex'


def test_two_different_files_at_both_spellings_are_ambiguous_and_refused_but_identical_bytes_are_not(tmp_path):
    base = _tree(tmp_path, {'sections/H.tex': '\\input{tikz/fig}\n', 'tikz/fig.tex': 'compiled', 'sections/tikz/fig.tex': 'edited by mistake'})
    tree = _traverse(tmp_path, base)
    assert [d['kind'] for d in tree['diagnostics']] == ['ambiguous-include']
    assert 'paper/tex_v4/tikz/fig.tex' not in tree['files'], 'an ambiguous member is not proved'
    closure = tex_dependencies.prepare_closure('p', tmp_path, {'root': 'paper/tex_v4/main.tex'}, {})
    assert any(d.get('code') == 'AMBIGUOUS_DECLARATION' for d in closure['diagnostics'])
    (base / 'sections' / 'tikz' / 'fig.tex').write_text('compiled')
    assert _traverse(tmp_path, base)['diagnostics'] == []


@pytest.mark.parametrize('argument', ['../outside', '/etc/hostname', '  '])
def test_unsafe_include_arguments_are_refused_without_reading_outside(tmp_path, argument):
    base = _tree(tmp_path, {'sections/H.tex': '\\input{%s}\n' % argument})
    (tmp_path / 'paper' / 'outside.tex').write_text('outside the compilation directory')
    tree = _traverse(tmp_path, base)
    kinds = [d['kind'] for d in tree['diagnostics']]
    assert kinds and set(kinds) <= {'unsafe-include'} and 'paper/outside.tex' not in tree['files']


def test_deeper_nesting_and_repeated_includes_keep_compilation_directory_semantics(tmp_path):
    base = _tree(tmp_path, {'sections/H.tex': '\\input{sections/sub/A}\n\\input{tikz/fig}\n',
                            'sections/sub/A.tex': '\\input{tikz/fig}\n', 'tikz/fig.tex': 'figure'})
    tree = _traverse(tmp_path, base)
    assert tree['diagnostics'] == []
    assert [row['file'] for row in tree['sources']].count('paper/tex_v4/tikz/fig.tex') == 2, 'each occurrence retained'


def test_the_contract_itself(tmp_path):
    base = _tree(tmp_path, {'tikz/a.tex': 'a', 'sections/tikz/a.tex': 'a'})
    including = base / 'sections' / 'H.tex'
    found = tex_dependencies.tex_input('tikz/a', including=including, compile_dir=base, fence=base)
    assert found == {'status': 'resolved', 'path': base / 'tikz' / 'a.tex', 'alternate': None}
    assert tex_dependencies.tex_input('../x', including=including, compile_dir=base, fence=base)['status'] == 'unsafe'
    assert tex_dependencies.tex_input('nowhere', including=including, compile_dir=base, fence=base)['status'] == 'missing'


# ---- repair1 WR-R6 (Sol review 2026-10-16): the resolved-path fence -----------------------------------------------

SENTINEL = 'SYNTHETIC_OUTSIDE_FENCE_ONLY'


@pytest.mark.parametrize('kind', ['file', 'directory'])
def test_a_symlink_escaping_the_fence_is_refused_before_any_outside_read(tmp_path, kind, monkeypatch):
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'linked.tex').write_text(SENTINEL)
    base = _tree(tmp_path, {'sections/H.tex': '\\input{shared/linked}\n' if kind == 'directory' else '\\input{linked}\n'})
    if kind == 'directory':
        (base / 'shared').symlink_to(outside, target_is_directory=True)
    else:
        (base / 'linked.tex').symlink_to(outside / 'linked.tex')
    opened = []
    real = Path.read_bytes
    monkeypatch.setattr(Path, 'read_bytes', lambda self: (opened.append(self.resolve()), real(self))[1])
    found = tex_dependencies.tex_input('shared/linked' if kind == 'directory' else 'linked', including=base / 'sections/H.tex',
                                       compile_dir=base, fence=base)
    assert found['status'] == 'unsafe' and found['path'] is None
    tree = _traverse(tmp_path, base)
    assert [row['kind'] for row in tree['diagnostics']] == ['unsafe-include']
    assert all(SENTINEL not in row['text'] for row in tree['sources'])
    assert not any(path.is_relative_to(outside) for path in opened), 'no outside byte was read'


def test_an_inside_fence_alias_stays_usable_and_consistent(tmp_path):
    base = _tree(tmp_path, {'sections/H.tex': '\\input{alias}\n', 'real/body.tex': 'Body text.'})
    (base / 'alias.tex').symlink_to(base / 'real' / 'body.tex')
    found = tex_dependencies.tex_input('alias', including=base / 'sections/H.tex', compile_dir=base, fence=base)
    assert found['status'] == 'resolved' and found['path'] == base / 'alias.tex'
    tree = _traverse(tmp_path, base)
    assert tree['diagnostics'] == [] and tree['sources'][-1]['text'] == 'Body text.'


def test_an_alternate_spelling_outside_the_fence_is_never_compared(tmp_path, monkeypatch):
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'x.tex').write_text(SENTINEL)
    base = _tree(tmp_path, {'sections/H.tex': '\\input{x}\n', 'x.tex': 'Compile-directory x.'})
    (base / 'sections' / 'x.tex').symlink_to(outside / 'x.tex')
    opened = []
    real = Path.read_bytes
    monkeypatch.setattr(Path, 'read_bytes', lambda self: (opened.append(self.resolve()), real(self))[1])
    found = tex_dependencies.tex_input('x', including=base / 'sections/H.tex', compile_dir=base, fence=base)
    assert found == {'status': 'resolved', 'path': base / 'x.tex', 'alternate': None}
    assert not any(path.is_relative_to(outside) for path in opened)


def test_build_closure_and_declared_aliases_agree_on_inside_aliases_and_refuse_repository_escapes(tmp_path):
    repo = tmp_path / 'repo'
    base = repo / 'paper' / 'tex_v4'
    (base / 'real').mkdir(parents=True)
    (base / 'main.tex').write_text('\\documentclass{article}\\begin{document}\\input{alias}\\input{esc}\\end{document}\n')
    (base / 'real' / 'body.tex').write_text('Body')
    (base / 'alias.tex').symlink_to(base / 'real' / 'body.tex')
    (tmp_path / 'outside.tex').write_text(SENTINEL)
    (base / 'esc.tex').symlink_to(tmp_path / 'outside.tex')
    closure = tex_dependencies.prepare_closure('p', repo, {'root': 'paper/tex_v4/main.tex'}, {})
    members = {row['path']: row for row in closure['members']}
    assert members['paper/tex_v4/alias.tex']['canonical_path'] == 'paper/tex_v4/real/body.tex'
    assert 'paper/tex_v4/esc.tex' not in members and {'code': 'ESCAPING_DECLARATION', 'argument': 'esc', 'role': 'include'} in closure['diagnostics']
    aliases = {Path(k).relative_to(repo).as_posix(): Path(v).relative_to(repo).as_posix()
               for k, v in tex_dependencies.declared_aliases(base / 'main.tex', repo).items()}
    assert aliases == {'paper/tex_v4/alias.tex': 'paper/tex_v4/real/body.tex'}
    tree = manuscript_source.traversal(base / 'main.tex', repo_root=repo)
    # the traversal reads the inside alias at the same canonical file the closure maps it to
    assert [row['file'] for row in tree['sources']] == ['paper/tex_v4/main.tex', 'paper/tex_v4/real/body.tex']
    assert [row['kind'] for row in tree['diagnostics']] == ['unsafe-include']
