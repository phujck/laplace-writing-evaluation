"""Logical plan IDs remain separate from physical source and PDF occurrences."""
from pathlib import Path
from laplace.manuscript import projection_viewer, review_surface, walk
from laplace.pipeline import edits, nodemap, dispatch
from test_edits import _verb_md


def test_merged_edit_protects_all_ids_and_split_scalar_read_refuses(tmp_path):
    text='% PLAN:N2\n% N1-p123456789012345678901234567890123456789\n% N2-p7\nMerged body.\n\n% N2-p7\nSecond physical piece.\n'
    md=_verb_md(tmp_path,text)
    result=review_surface.adjudicate(md,'projX',{'by':'author','verb':'edit-in-place','section':'N1',
        'paragraph':'N1-p123456789012345678901234567890123456789','before':'Merged body.','after':'Edited body.'},repo_root=tmp_path)
    record=result['record']
    assert record['anchor']['spec_ids']==['N1-p123456789012345678901234567890123456789','N2-p7']
    assert ('N1','N2-p7') in edits.protected_units([record])
    assert review_surface._node_protected('N2-p7',edits.protected_units([record]),set())
    assert review_surface._paragraph_char_span(text,'N2-p7') is None
    blocks=walk.blocks_for(text,file_rel='N1.tex',repo_file='N1.tex',md=md,corpus='',dir_param='',
        para_spans=projection_viewer.parse_paragraphs(text),known_macros={})
    body=next(row for row in blocks if row['tex']=='Merged body.')
    assert body['spec_ids']==record['anchor']['spec_ids'] and body['source_section']=='N2'
    units=dispatch._fragment_paragraph_units(text)
    assert units[0]['spec_ids']==record['anchor']['spec_ids'] and len(units)==2


def test_pdf_occurrence_keys_and_injection_do_not_collapse_split_units(tmp_path):
    source=tmp_path/'source';source.mkdir()
    (source/'main.tex').write_text('\\documentclass{article}\n\\begin{document}\n% PLAN:sec:intro\n% sec:intro-p99999999999999999999999\nFirst physical piece.\n\n% sec:intro-p99999999999999999999999\nSecond physical piece.\n\\end{document}\n')
    specs,_=nodemap.discover_specs(source,tiers=('T2',))
    assert len(specs)==2 and len({row.key for row in specs})==2
    assert all(row.source_section=='sec:intro' for row in specs)
    result=nodemap.inject(source,tmp_path/'instrumented',specs)
    placements=[row['at'] for row in result['applied'] if row['kind']=='paragraph']
    assert len(set(placements))==2


def test_first_pdf_anchor_uses_explicit_location_not_numeric_suffix():
    entries={'old-p99999999999999999999999':[{'page':1,'y0':10,'section':'new'}],
             'new-p1':[{'page':2,'y0':10,'section':'new'}]}
    assert review_surface._section_first_para(entries,'new')=='old-p99999999999999999999999'
    assert review_surface._section_first_para({'N1-p1':[{'page':1}]},'N1') is None


def test_fragment_reader_strips_canonical_non_n_merged_markers(tmp_path):
    md=tmp_path/'manuscript';md.mkdir()
    (md/'main.tex').write_text('\\documentclass{article}\n\\begin{document}\n\\input{first}\n\\end{document}\n')
    (md/'first.tex').write_text('% PLAN:first\n% first-p12345678901234567890\n% sec:intro-p7\nMerged physical prose.\n')
    view=review_surface.fragment_view(md,'first','first-p12345678901234567890')
    assert view['ok'] and view['before']=='Merged physical prose.'
    assert view['line_start']==4 and view['spec_ids']==['first-p12345678901234567890','sec:intro-p7']
    assert view['source_section']=='first'
