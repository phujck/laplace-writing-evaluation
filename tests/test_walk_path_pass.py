"""Per-pass literal projection must not invent structure or amplify source scans."""
from pathlib import Path
import pytest
from laplace.manuscript import walk


def blocks(source):
    return walk.blocks_for(source, file_rel='chapter.tex', repo_file='chapter.tex',
        md=Path('.'), corpus='', dir_param='', para_spans=[], known_macros={})


@pytest.mark.parametrize('literal', [
    'folder/\n\\section{literal}/end',
    'folder/\n\\begin{equation}x=2\\end{equation}/end',
    'folder/\n\\[x=2\\]/end',
    'folder/\n\n%literal\n\\par\n/end',
    'folder/\n\\begin{center}\n\\begin{tabular}{cc}a&b\\\\\\end{tabular}\n\\end{center}/end',
])
def test_multiline_supported_path_stays_one_source_mapped_prose_block(literal):
    source = 'Read \\path|' + literal + '| after.'
    projected = blocks(source)
    assert len(projected) == 1 and projected[0]['kind'] == 'para'
    block = projected[0]
    assert block['tex'] == source and block['src']['line_end'] == len(source.split('\n'))
    path = next(p for p in block['pieces'] if p.get('command') == 'path')
    assert path['t'] == 'code' and path['s'] == literal and path['literal']
    assert source[path['o_start']:path['o_end']] == '\\path|' + literal + '|'


def test_real_heading_equation_and_paragraph_boundary_after_literal_remain_active():
    source = ('Read \\path|folder/\n\\section{literal}/end| after.\n\n'
              '\\section{Actual}\n\\begin{equation}x=3\\end{equation}\n\nActual prose.')
    projected = blocks(source)
    assert [b['kind'] for b in projected] == ['para', 'head', 'equation', 'para']
    assert projected[1]['title'] == 'Actual' and projected[2]['math'] == 'x=3'


def test_active_heading_with_inline_path_and_escaped_noncommand_are_not_suppressed():
    source = '\\section{Actual \\path{a_b%20.json}}\n\\\\path{ordinary}\n\\section{Next}'
    projected = blocks(source)
    assert [b['kind'] for b in projected] == ['head', 'para', 'head']
    assert projected[0]['title'] == 'Actual a_b%20.json' and projected[-1]['title'] == 'Next'


@pytest.mark.parametrize('source', [
    'Read \\path{broken\n\\section{not proven}',
    'Read \\path|broken\n\\begin{equation}not proven\\end{equation}',
])
def test_unsupported_available_path_source_does_not_create_partial_fake_structure(source):
    projected = blocks(source)
    assert len(projected) == 1 and projected[0]['kind'] == 'para' and projected[0]['tex'] == source
    assert next(p for p in projected[0]['pieces'] if p.get('command') == 'path')['t'] == 'raw'


def test_root_content_pass_keeps_literal_plumbing_and_uses_real_document_boundaries():
    literal = 'folder/\n\\clearpage\n\\input{literal}\n\\begin{equation}literal\\end{equation}\n\\end{document}/end'
    source = '\\documentclass{article}\n\\begin{document}\nRead \\path|' + literal + '| after.\n\\section{Actual}\n\\end{document}'
    masked, skipped = walk.root_content(source)
    assert '\\path|' + literal + '|' in masked
    projected = blocks(masked)
    assert [b['kind'] for b in projected] == ['para', 'head']
    assert projected[-1]['title'] == 'Actual'
    assert '\\clearpage' not in skipped


@pytest.mark.parametrize('unit,kind', [
    ('\\begin{equation}\nx=1\n\\end{equation}\n', 'equation'),
    ('\\begin{center}\\begin{tabular}{ll}A & B\\\\\\end{tabular}\\end{center}\n', 'table'),
])
def test_environment_mask_scan_counts_scale_with_source_not_remaining_suffixes(monkeypatch, unit, kind):
    actual = walk._masked_tex_comments
    scans = []
    def observed(tex, *args, **kwargs):
        scans.append(len(tex))
        return actual(tex, *args, **kwargs)
    monkeypatch.setattr(walk, '_masked_tex_comments', observed)
    totals = []
    for count in (100, 200, 400):
        source = unit * count
        scans.clear()
        result = blocks(source)
        assert len(result) == count and all(block['kind'] == kind for block in result)
        total = sum(scans)
        totals.append(total)
        # One full source mask per pass, with only constant-size block scans after it.
        assert sum(size == len(source) for size in scans) == 1
    assert totals[1] == 2 * totals[0] and totals[2] == 2 * totals[1]


def test_root_environment_pass_reuses_one_source_mask(monkeypatch):
    actual = walk._masked_tex_comments
    scans = []
    def observed(tex, *args, **kwargs):
        scans.append(len(tex))
        return actual(tex, *args, **kwargs)
    monkeypatch.setattr(walk, '_masked_tex_comments', observed)
    unit = '\\begin{equation}x=1\\end{equation}\n'
    totals = []
    for count in (100, 200, 400):
        source = '\\begin{document}\n' + unit * count + '\\end{document}'
        scans.clear()
        result, _ = walk.root_content(source)
        assert result.count('\\begin{equation}') == count
        totals.append(sum(scans))
        assert sum(size == len(source) for size in scans) == 1
    assert totals[2] - totals[1] == 2 * (totals[1] - totals[0])
