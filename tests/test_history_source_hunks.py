"""Recorded save deltas are shared evidence, not reconstructed live-source prose."""
import hashlib,json
from pathlib import Path
import pytest
from laplace.work import history as author_history
from laplace.manuscript import manuscript_fragments, manuscript_source, projection_viewer as pv, review_surface as rv
from laplace.pipeline import authoring
from test_editor_document_contract import fixture, read, save


def test_saved_delta_is_the_same_in_inline_history_exact_record_and_author_changes(tmp_path,monkeypatch):
    md=fixture(tmp_path);monkeypatch.setattr(pv,'_repo_root',lambda:tmp_path);monkeypatch.setattr(rv,'_repo_root',lambda:tmp_path)
    _,observed=read(tmp_path)
    original=observed['content']
    sentence='The history reader retains this exact inserted sentence.'
    code,saved=save(observed,original+sentence+'\n')
    assert code==200
    ident=saved['exemplar']['exemplar_id']
    item=authoring.history('paper',{'id':ident},repo_root=tmp_path)['item']
    assert item['baseline']['kind']=='guarded-save-preimage'
    before_files={str(path.relative_to(md)):path.read_bytes() for path in md.rglob('*') if path.is_file()}
    detail=author_history.detail('paper','activity:authoring:'+ident,tmp_path)
    exact=author_history.record('paper','activity:authoring:'+ident,tmp_path)
    inline=manuscript_fragments.change_preview('paper',{'id':ident},tmp_path)
    assert detail['comparisons']==exact['comparisons']
    assert detail['comparisons'][0]['before']==inline['hunks'][0]['before']==''
    assert detail['comparisons'][0]['after']==inline['hunks'][0]['after']==sentence
    assert detail['comparison']==detail['comparisons'][0]
    assert detail['hashes'][0]['status']=='recorded'
    assert detail['hashes'][1]['status']=='current'
    assert before_files=={str(path.relative_to(md)):path.read_bytes() for path in md.rglob('*') if path.is_file()}
    (md/'body.tex').write_text('A subsequent source version.\n')
    changed=author_history.detail('paper','activity:authoring:'+ident,tmp_path)
    assert changed['comparisons']==detail['comparisons']
    assert changed['hashes'][1]['status']=='changed'
    assert 'no stored source bytes' not in json.dumps(changed)


def test_recorded_delta_without_file_pins_keeps_text_without_inventing_a_snapshot(tmp_path):
    item={'anchor':{'file':'paper/body.tex'},'hunks':[{'start':2,'end':2,'before':['Old words.'],'after':['New words.']}]}
    comparison=manuscript_fragments.recorded_source_comparisons(item)
    assert comparison[0]['before']=='Old words.' and comparison[0]['after']=='New words.'
    result=author_history._detail('authoring',item,{'summary':'Recorded edit','targets':[]},tmp_path)
    assert result['comparisons']==comparison
    assert result['hashes'][0]['recorded'] is None
    assert not any(row.get('current') for row in result['hashes'])


def test_explicit_manifest_root_refuses_ineffective_alternate_selection_and_same_root_is_noop(tmp_path):
    md=fixture(tmp_path)
    alternate=md/'alternate.tex';alternate.write_text('\\documentclass{article}\n\\begin{document}\nA substantive alternative.\n\\end{document}\n')
    registry=(tmp_path/'registry_projects.json').read_bytes()
    with pytest.raises(ValueError,match='manifest fixes'):
        manuscript_source.select('paper','paper/alternate.tex',repo_root=tmp_path,expected_revision=hashlib.sha256(alternate.read_bytes()).hexdigest())
    assert not (md/'document_selection.json').exists()
    same=manuscript_source.select('paper','paper/main.tex',repo_root=tmp_path,expected_revision=hashlib.sha256((md/'main.tex').read_bytes()).hexdigest())
    assert same['root']=='paper/main.tex' and same['selection_changed'] is False
    assert not (md/'document_selection.json').exists() and (tmp_path/'registry_projects.json').read_bytes()==registry
