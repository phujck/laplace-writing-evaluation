"""Rowbreak text and actual primitive starts use the same existing validator."""
import hashlib
import pytest
from laplace.pipeline import visual_production as vp

def picture(label):
    return r'\begin{tikzpicture}\node[align=center] {Produced proof' + label + r'};\end{tikzpicture}'

@pytest.mark.parametrize('slashes', [0, 2, 4])
def test_rowbreak_then_input_word_is_literal_and_exact_for_inline_and_source(tmp_path, slashes):
    text=picture('\\'*slashes+'input')
    expected=(text,hashlib.sha256(text.encode()).hexdigest())
    assert vp._tikz_snippet(tmp_path,{'tikz':text})==expected
    (tmp_path/'label.tikz').write_text(text)
    assert vp._tikz_snippet(tmp_path,{'source':'label.tikz'})==expected

@pytest.mark.parametrize('slashes', [1,3,5])
@pytest.mark.parametrize('primitive', ['documentclass','usepackage','input','include',
    'includegraphics','pgfplotstableread','openin','read','write','write18',
    'begin{document}','end{document}'])
def test_active_forbidden_families_remain_refused_after_paired_controls(tmp_path, slashes, primitive):
    with pytest.raises(ValueError,match='forbidden'):
        vp._tikz_snippet(tmp_path,{'tikz':picture('\\'*slashes+primitive)})

def test_control_word_boundaries_and_write_numeric_arguments(tmp_path):
    assert vp._tikz_snippet(tmp_path,{'tikz':picture(r'\inputting')})
    for tail in [r'\write18x',r'\WRITE 18',r'\begin {document}']:
        with pytest.raises(ValueError,match='forbidden'):
            vp._tikz_snippet(tmp_path,{'tikz':picture(tail)})

def test_unchanged_source_fence_size_and_picture_count(tmp_path):
    (tmp_path/'outside.tikz').write_text(picture('safe'))
    confined=tmp_path/'confined';confined.mkdir()
    with pytest.raises(ValueError,match='project-confined'):
        vp._tikz_snippet(confined,{'source':'../outside.tikz'})
    with pytest.raises(ValueError,match='too large'):
        vp._tikz_snippet(tmp_path,{'tikz':picture('a'*500001)})
    with pytest.raises(ValueError,match='exactly one'):
        vp._tikz_snippet(tmp_path,{'tikz':picture('a')+picture('b')})
