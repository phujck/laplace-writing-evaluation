"""Generic layout tables use the existing rows and exact source edit boundary."""
from pathlib import Path
import hashlib
import pytest
from laplace.manuscript import walk

TABLE = r'\begin{tabular}{ll}\textbf{Candidate} & \textbf{Action}\\ Generated & Keep $x$\\\end{tabular}'


def blocks(text):
    return walk.blocks_for(text, file_rel='chapter.tex', repo_file='chapter.tex',
        md=Path('.'), corpus='', dir_param='', para_spans=[], known_macros={})


def cells(block):
    return [[cell['tex'] for cell in row['cells']] for row in block['rows']]


@pytest.mark.parametrize('text', [
    r'\begin{center}\small' + TABLE + r'\end{center}',
    '\\begin{center}\n\\small\n' + TABLE + '\n\\end{center}',
    r'\begin{center}{\footnotesize' + TABLE + r'}\end{center}',
    r'\begin{center}\begin{table}[t]\centering\small' + TABLE + r'\end{table}\end{center}',
    r'\begin{table}[ht]\begin{center}\small' + TABLE + r'\end{center}\caption{Lifecycle}\label{tab:lifecycle}\end{table}',
    r'\begin{center}\begin{center}\small' + TABLE + r'\end{center}\end{center}',
])
def test_layout_table_rows_keep_every_wrapper_and_cell_offset(text):
    block = blocks(text)[0]
    assert block['kind'] == 'table' and block['tex'] == text
    assert cells(block) == [[r'\textbf{Candidate}', r'\textbf{Action}'], ['Generated', 'Keep $x$']]
    assert block['rows'][0]['header'] is True
    assert block['src']['line_start'] == 1 and block['src']['line_end'] == len(text.split('\n'))
    for row in block['rows']:
        for cell in row['cells']:
            assert text[cell['o_start']:cell['o_end']] == cell['tex']
    if r'\caption' in text:
        assert block['caption'] == 'Lifecycle'
        assert text[block['caption_pieces'][0]['o_start']:block['caption_pieces'][0]['o_end']] == 'Lifecycle'


def test_centered_star_table_multicolumn_offsets_do_not_consume_layout():
    text = r'\begin{center}\small\begin{tabular*}{\linewidth}{lc}\multicolumn{2}{c}{Kept \& joined}\\ A & $u&v$\\\end{tabular*}\end{center}'
    block = blocks(text)[0]
    assert block['kind'] == 'table'
    assert cells(block) == [[r'Kept \& joined'], ['A', '$u&v$']]
    assert block['rows'][0]['cells'][0]['colspan'] == 2
    assert all(text[cell['o_start']:cell['o_end']] == cell['tex'] for row in block['rows'] for cell in row['cells'])


def test_fake_commented_environment_delimiters_do_not_change_recognition_or_span():
    text = ('\\begin{center}\n% \\begin{tabular}{c} fake \\end{center}\n'
            '\\small\n\\begin{tabular}{ll}\n% \\end{tabular}\n'
            'A & B\\\\\n\\end{tabular}\n% \\begin{center} \\end{tabular}\n\\end{center}')
    projected = blocks('Before.\n\n' + text + '\n\nAfter.')
    assert [block['kind'] for block in projected] == ['para', 'table', 'para']
    block = projected[1]
    assert block['tex'] == text and len(block['rows']) == 1
    assert block['src']['line_start'] == 3 and block['src']['line_end'] == 11
    assert 'fake' not in walk._flatten_pieces(block['rows'][0]['cells'][0]['pieces'])
    assert all(text[cell['o_start']:cell['o_end']] == cell['tex'] for row in block['rows'] for cell in row['cells'])


@pytest.mark.parametrize('text', [
    r'\begin{center}Before. ' + TABLE + r'\end{center}',
    r'\begin{center}' + TABLE + r' After.\end{center}',
    r'\begin{center}' + TABLE + TABLE + r'\end{center}',
    r'\begin{center}\resizebox{\linewidth}{!}{' + TABLE + r'}\end{center}',
    r'\begin{center}\begin{tabular}{ll}A & {broken\\\end{tabular}\end{center}',
    r'\begin{center}\begin{tabular}{ll}A & B\\\end{center}',
    r'\begin{table}Before. ' + TABLE + r'\end{table}',
    TABLE + ' Same-line authored suffix.',
    r'\begin{center}\caption{First}' + TABLE + r'\caption{Second}\end{center}',
])
def test_mixed_or_unsupported_table_keeps_whole_inspectable_source(text):
    block = blocks(text)[0]
    assert block['kind'] == 'raw'
    assert block['tex'] == text
    assert 'source' in block['reason'] or 'safely' in block['reason']
    assert block['src']['line_start'] == 1 and block['src']['line_end'] == len(text.split('\n'))


def test_pure_center_prose_is_not_promoted_by_a_commented_fake_table():
    text = '\\begin{center}\n% \\begin{tabular}{c} ignored\nVisible prose.\n\\end{center}'
    block = blocks(text)[0]
    assert block['kind'] != 'table' and block['tex'] == text
    assert 'Visible prose.' in walk._flatten_pieces(block['pieces'])


def test_commented_fake_caption_does_not_replace_the_authored_table_caption():
    text = ('\\begin{center}\n% \\caption{Not authored}\n' + TABLE +
            '\n\\caption{Actual caption}\n\\end{center}')
    block = blocks(text)[0]
    assert block['kind'] == 'table' and block['caption'] == 'Actual caption'
    assert all(text[piece['o_start']:piece['o_end']] == piece['s']
               for piece in block['caption_pieces'] if piece['t'] == 'text')


def test_row_terminator_comment_ignores_fake_delimiters_but_escaped_percent_is_content():
    text = ('\\begin{center}\n\\small\\begin{tabular}{ll}\n'
            'A & 50\\%\\\\% \\end{center} \\end{tabular} \\begin{longtable}\n'
            'B & 75\\%\\\\\n\\end{tabular}\n\\end{center}')
    block = blocks(text)[0]
    assert block['kind'] == 'table' and block['tex'] == text
    assert len(block['rows']) == 2
    assert all(text[cell['o_start']:cell['o_end']] == cell['tex'] for row in block['rows'] for cell in row['cells'])
    assert '50%' in walk._flatten_pieces(block['rows'][0]['cells'][1]['pieces'])
    assert 'fake' not in walk._flatten_pieces(block['rows'][1]['cells'][0]['pieces'])
    masked = walk._masked_tex_comments(r'50\% remains. % \end{center}')
    assert masked.startswith(r'50\% remains. ') and r'\end{center}' not in masked
    assert len(masked) == len(r'50\% remains. % \end{center}')


def test_guarded_author_cell_edit_preserves_wrapper_and_refuses_cached_source(tmp_path, monkeypatch):
    from test_writing_controller import _import_project
    from laplace.manuscript import review_surface, projection_viewer
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / 'state'))
    monkeypatch.setattr(review_surface, '_repo_root', lambda: tmp_path)
    monkeypatch.setattr(projection_viewer, '_repo_root', lambda: tmp_path)
    table = '\\begin{center}\n\\small\n' + TABLE + '\n\\end{center}'
    original = 'Before.\n\n' + table + '\n\nAfter.\n'
    md, _ = _import_project(tmp_path, name='centered-fixture', files={
        'main.tex': '\\documentclass{article}\n\\begin{document}\n\\input{chapter}\n\\end{document}\n',
        'chapter.tex': original})
    block = blocks(original)[1]
    cell = block['rows'][1]['cells'][0]
    after = table[:cell['o_start']] + 'Author edited' + table[cell['o_end']:]
    payload = {'verb': 'rewrite', 'by': 'fixture-author', 'file': 'chapter.tex',
        'line_start': block['src']['line_start'], 'line_end': block['src']['line_end'],
        'before': table, 'after': after, 'expected_source_digest': hashlib.sha256(original.encode()).hexdigest()}
    result = review_surface.adjudicate(md, 'centered-fixture', payload)
    assert result.get('ok') and not result.get('pending'), result
    saved = (md / 'chapter.tex').read_text()
    assert saved == original.replace(table, after)
    assert r'\begin{center}' in saved and r'\small' in saved and r'\end{center}' in saved
    cached = review_surface.adjudicate(md, 'centered-fixture', {**payload, 'after': table.replace('Generated', 'Wrong cached edit')})
    assert not cached.get('ok') or cached.get('pending'), cached
    assert (md / 'chapter.tex').read_text() == saved
