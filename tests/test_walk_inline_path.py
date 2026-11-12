"""Standard path syntax projects literal bytes, with no link/prose inference."""
from pathlib import Path
import hashlib
import pytest
from laplace.manuscript import walk


@pytest.mark.parametrize('command,content', [
    (r'\path{manuscript-integrity/lifecycle/review.json}', 'manuscript-integrity/lifecycle/review.json'),
    (r'\path{a_b/%20/$value/#id/&x/~user/--/``quoted\file}', r'a_b/%20/$value/#id/&x/~user/--/``quoted\file'),
    (r'\path{C:\folder\}', 'C:\\folder\\'),
    (r'\path{root/{group}/review.json}', 'root/{group}/review.json'),
    (r'\path|C:\folder\a_b%20.json|', 'C:\\folder\\a_b%20.json'),
    (r'\path+literal{brace}/review.json+', 'literal{brace}/review.json'),
    (r'\path!https://example.invalid/a_b?x=20%!', 'https://example.invalid/a_b?x=20%'),
    (r'\path%a_b/c%', 'a_b/c'),
    (r'\path[a_b/c[', 'a_b/c'),
    ('\\path {line one\nline_two%}.', 'line one\nline_two%'),
    (r'\path{}', ''),
])
def test_literal_path_uses_existing_code_atom_and_exact_whole_command_offsets(command, content):
    source = 'Before 🧪 ' + command + ' After.'
    pieces = walk.tex_pieces(source, base=17)
    piece = next(piece for piece in pieces if piece.get('command') == 'path')
    assert piece['t'] == 'code' and piece['s'] == content and piece['literal'] is True
    assert 'url' not in piece and 'pieces' not in piece
    exact = source[piece['o_start'] - 17:piece['o_end'] - 17]
    assert exact == command.rstrip('.')  # trailing prose is outside the path command
    assert content in walk._flatten_pieces(pieces)
    assert not any(piece['t'] in {'url', 'href', 'math', 'macro'} for piece in pieces)
    assert all(a['o_end'] <= b['o_start'] for a, b in zip(pieces, pieces[1:]))


@pytest.mark.parametrize('source', [r'\path{broken', r'\path{one{nested}',
    r'\path|missing%delimiter', r'\path*{not-a-standard-starred-form}', r'\path}bad}'])
def test_unsupported_path_remains_marked_exact_source_without_partial_literal_guess(source):
    pieces = walk.tex_pieces(source)
    assert len(pieces) == 1 and pieces[0]['t'] == 'raw'
    assert pieces[0]['s'] == source and pieces[0]['reason'].startswith('Unsupported')
    assert pieces[0]['o_start'] == 0 and pieces[0]['o_end'] == len(source)


def test_literal_brace_lexer_does_not_change_existing_escape_behavior():
    source = r'{a\}b}'
    assert walk._brace_arg(source, 0) == (r'a\}b', len(source))
    assert walk._brace_arg(source, 0, literal=True, require_closed=True) == ('a\\', 4)
    assert walk._brace_arg('{a{b}', 0, literal=True, require_closed=True) == ('', 0)


def test_standard_url_and_texttt_keep_their_existing_distinct_semantics():
    source = r'\url{https://example.invalid/a_b} \texttt{A\_B} \path{A\_B}'
    pieces = walk.tex_pieces(source)
    assert pieces[0]['t'] == 'url' and pieces[0]['url'] == 'https://example.invalid/a_b'
    code = [piece for piece in pieces if piece['t'] == 'code']
    assert code[0]['s'] == 'A_B' and code[0]['pieces']
    assert code[1]['s'] == r'A\_B' and 'pieces' not in code[1]


def test_authored_path_redefinition_is_not_guessed_as_standard_literal_semantics():
    source = r'\path{scientific object}'
    pieces = walk.tex_pieces(source, {r'\path': r'\mathsf{#1}'})
    assert pieces[0]['t'] == 'raw' and pieces[0]['s'] == source
    assert 'redefined' in pieces[0]['reason']


def test_guarded_source_substring_edit_keeps_path_delimiters_and_literal_register(tmp_path, monkeypatch):
    from test_writing_controller import _import_project
    from laplace.manuscript import review_surface, projection_viewer
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / 'state'))
    monkeypatch.setattr(review_surface, '_repo_root', lambda: tmp_path)
    monkeypatch.setattr(projection_viewer, '_repo_root', lambda: tmp_path)
    source = r'Inspect \path{C:\owned_folder\review%20.json} before the conclusion.'
    md, _ = _import_project(tmp_path, name='path-fixture', files={
        'main.tex': '\\documentclass{article}\n\\usepackage{url}\n\\begin{document}\n\\input{chapter}\n\\end{document}\n',
        'chapter.tex': source + '\n'})
    path = next(piece for piece in walk.tex_pieces(source) if piece.get('command') == 'path')
    body_start = path['o_end'] - 1 - len(path['s'])
    start = body_start + path['s'].index('review')
    changed = source[:start] + 'accepted' + source[start + len('review'):]
    assert changed == source.replace('review', 'accepted')
    payload = {'verb': 'rewrite', 'by': 'fixture-author', 'file': 'chapter.tex',
        'line_start': 1, 'line_end': 1, 'before': source, 'after': changed,
        'expected_source_digest': hashlib.sha256((source + '\n').encode()).hexdigest()}
    result = review_surface.adjudicate(md, 'path-fixture', payload)
    assert result.get('ok') and not result.get('pending'), result
    assert (md / 'chapter.tex').read_text() == changed + '\n'
    assert r'\path{C:\owned_folder\accepted%20.json}' in changed
    cached = review_surface.adjudicate(md, 'path-fixture', {**payload, 'after': source.replace('review', 'cached')})
    assert cached.get('pending') or not cached.get('ok'), cached
    assert (md / 'chapter.tex').read_text() == changed + '\n'
