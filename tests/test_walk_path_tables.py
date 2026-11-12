"""Recognized literal paths compose with real table/container source grammar."""
from pathlib import Path
import hashlib
import pytest
from laplace.manuscript import walk


def blocks(source, known=None):
    return walk.blocks_for(source, file_rel='chapter.tex', repo_file='chapter.tex',
        md=Path('.'), corpus='', dir_param='', para_spans=[], known_macros=known or {})


@pytest.mark.parametrize('gap', ['\n', '\n\n  ', '% delimiter comment\n'])
@pytest.mark.parametrize('env,body,kind', [
    ('equation', 'x=1', 'equation'),
    ('center', '\\begin{tabular}{ll}\nA & B\\\\\n\\end{tabular}', 'table'),
])
def test_split_environment_closer_preserves_following_prose_and_exact_span(gap, env, body, kind):
    block = '\\begin{' + env + '}\n' + body + '\n\\end' + gap + '{' + env + '}'
    source = 'Before.\n\n' + block + '\n\nAfter must remain visible.'
    result = blocks(source)
    assert [item['kind'] for item in result] == ['para', kind, 'para']
    assert result[1]['tex'] == block
    assert result[1]['src']['line_end'] == 2 + len(block.split('\n'))
    assert walk._flatten_pieces(result[-1]['pieces']) == 'After must remain visible.'
    root = '\\documentclass{article}\n\\begin{document}\n' + source + '\n\\end{document}'
    selected, _ = walk.root_content(root)
    selected_blocks = blocks(selected)
    assert [item['kind'] for item in selected_blocks] == ['para', kind, 'para']
    assert walk._flatten_pieces(selected_blocks[-1]['pieces']) == 'After must remain visible.'


@pytest.mark.parametrize('path,content', [
    (r'\path{a_b%20.json}', 'a_b%20.json'),
    (r'\path{C:\owned_folder\}', 'C:\\owned_folder\\'),
    (r'\path|C:\folder\a_b%20&value\end{center}\end{tabular}\caption{fake}\label{fake}|',
     r'C:\folder\a_b%20&value\end{center}\end{tabular}\caption{fake}\label{fake}'),
    (r'\path%a_b&value%', 'a_b&value'),
    (r'\path!value{&$%\begin{tabular}\end{center}!', r'value{&$%\begin{tabular}\end{center}'),
    ('\\path{a_b%20/\n\\end{tabular}&literal.json}', 'a_b%20/\n\\end{tabular}&literal.json'),
])
def test_literal_path_inside_center_table_has_real_two_cells_and_exact_offsets(path, content):
    source = '\\begin{center}\n\\small\\begin{tabular}{ll}\n' + path + ' & Actual second cell\\\\\n\\end{tabular}\n\\end{center}'
    result = blocks('Before.\n\n' + source + '\n\nAfter.')
    assert [b['kind'] for b in result] == ['para', 'table', 'para']
    block = result[1]
    assert block['tex'] == source and len(block['rows']) == 1
    assert len(block['rows'][0]['cells']) == 2
    first, second = block['rows'][0]['cells']
    assert first['tex'] == path and second['tex'] == 'Actual second cell'
    piece = first['pieces'][0]
    assert piece['t'] == 'code' and piece['literal'] and piece['s'] == content
    assert source[piece['o_start']:piece['o_end']] == path
    assert all(source[c['o_start']:c['o_end']] == c['tex'] for row in block['rows'] for c in row['cells'])
    assert block['labels'] == [] and not block['caption']
    assert block['src']['line_start'] == 3 and block['src']['line_end'] == 2 + len(source.split('\n'))


@pytest.mark.parametrize('wrap', ['group', 'multicolumn', 'caption'])
def test_outer_braces_and_caption_keep_trailing_literal_backslash_without_extra_brace(wrap):
    path = r'\path{C:\folder\}'
    cell = r'\multicolumn{1}{c}{' + path + '}' if wrap == 'multicolumn' else path
    table = r'\begin{tabular}{ll}' + cell + r' & B\\\end{tabular}'
    if wrap == 'group':
        source = r'\begin{center}{\small' + table + r'}\end{center}'
    elif wrap == 'caption':
        source = r'\begin{table}\caption{Read ' + path + r'}\begin{center}' + table + r'\end{center}\end{table}'
    else:
        source = r'\begin{center}' + table + r'\end{center}'
    block = blocks(source)[0]
    assert block['kind'] == 'table' and block['tex'] == source
    first = block['rows'][0]['cells'][0]
    assert first['tex'] == path and walk._flatten_pieces(first['pieces']) == 'C:\\folder\\'
    assert source[first['o_start']:first['o_end']] == path
    if wrap == 'caption':
        code = next(p for p in block['caption_pieces'] if p['t'] == 'code')
        assert code['s'] == 'C:\\folder\\' and source[code['o_start']:code['o_end']] == path
        assert block['caption'] == 'Read ' + path


def test_active_comments_and_delimiters_outside_literal_still_govern_real_table():
    source = ('\\begin{center}\n% \\path|ignored| \\end{center}\n\\begin{tabular}{ll}\n'
              '\\path{a%&\\end{center}} & B\\\\% \\end{tabular}\n'
              'C\\% & D\\\\\n\\end{tabular}\n\\end{center}')
    block = blocks(source)[0]
    assert block['kind'] == 'table' and len(block['rows']) == 2
    assert all(len(row['cells']) == 2 for row in block['rows'])
    assert walk._flatten_pieces(block['rows'][1]['cells'][0]['pieces']) == 'C%'
    assert block['tex'] == source
    masked = walk._masked_tex_comments(r'\path{a%&\end{center}} & Actual % \end{center}')
    assert ' & Actual ' in masked and r'\end{center}' not in masked
    escaped = r'\\path{ordinary%comment}'
    assert '\\\\path{ordinary' in walk._masked_tex_comments(escaped)
    assert 'comment' not in walk._masked_tex_comments(escaped)


def test_literal_fake_longtable_markers_do_not_create_sections_or_headers():
    path = r'\path|x\endhead\endfirsthead\midrule&%y|'
    source = r'\begin{longtable}{ll}Header & Value\\\endfirsthead' + path + r' & Kept\\\end{longtable}'
    block = blocks(source)[0]
    assert block['kind'] == 'table'
    assert [row['role'] for row in block['rows']] == ['first-header', 'body']
    assert block['rows'][1]['header'] is False
    assert block['rows'][1]['cells'][0]['tex'] == path
    assert source[block['rows'][1]['cells'][0]['o_start']:block['rows'][1]['cells'][0]['o_end']] == path


@pytest.mark.parametrize('path,known', [
    (r'\path{broken%content', {}),
    (r'\path*{a%content}', {}),
    (r'\path{a%content}', {r'\path': r'\mathsf{#1}'}),
    (r'\path|unclosed', {}),
    (r'\textbf{\path|unclosed}', {}),
])
def test_unsupported_literal_does_not_receive_standard_masking_authority(path, known):
    source = r'\begin{center}\begin{tabular}{ll}' + path + r' & B\\\end{tabular}\end{center}'
    block = blocks(source, known)[0]
    assert block['kind'] == 'raw' and block['tex'] == source
    assert 'source' in block['reason'] or 'safely' in block['reason']


def test_real_guarded_cell_source_edit_preserves_literal_and_all_enclosing_bytes(tmp_path, monkeypatch):
    from test_writing_controller import _import_project
    from laplace.manuscript import review_surface, projection_viewer
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / 'state'))
    monkeypatch.setattr(review_surface, '_repo_root', lambda: tmp_path)
    monkeypatch.setattr(projection_viewer, '_repo_root', lambda: tmp_path)
    table = r'\begin{center}{\small\begin{tabular}{ll}\path|C:\owned_folder\review%20&literal.json| & B\\\end{tabular}}\end{center}'
    original = 'Before.\n\n' + table + '\n\nAfter.\n'
    md, _ = _import_project(tmp_path, name='path-table-fixture', files={
        'main.tex': '\\documentclass{article}\n\\usepackage{url}\n\\begin{document}\n\\input{chapter}\n\\end{document}\n',
        'chapter.tex': original})
    block = blocks(original)[1]
    piece = block['rows'][0]['cells'][0]['pieces'][0]
    content_start = piece['o_end'] - 1 - len(piece['s'])
    start = content_start + piece['s'].index('review')
    after = table[:start] + 'accepted' + table[start + len('review'):]
    payload = {'verb': 'rewrite', 'by': 'fixture-author', 'file': 'chapter.tex',
        'line_start': block['src']['line_start'], 'line_end': block['src']['line_end'],
        'before': table, 'after': after, 'expected_source_digest': hashlib.sha256(original.encode()).hexdigest()}
    result = review_surface.adjudicate(md, 'path-table-fixture', payload)
    assert result.get('ok') and not result.get('pending'), result
    expected = original.replace(table, after)
    assert (md / 'chapter.tex').read_text() == expected
    reread = blocks(expected)[1]
    assert reread['kind'] == 'table' and len(reread['rows'][0]['cells']) == 2
    assert reread['rows'][0]['cells'][0]['pieces'][0]['s'] == 'C:\\owned_folder\\accepted%20&literal.json'
    cached = review_surface.adjudicate(md, 'path-table-fixture', {**payload, 'after': table.replace('review', 'cached')})
    assert cached.get('pending') or not cached.get('ok'), cached
    assert (md / 'chapter.tex').read_text() == expected
