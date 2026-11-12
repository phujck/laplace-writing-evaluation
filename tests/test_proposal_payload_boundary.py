"""Lineage declarations cannot disappear through an ignored proposal field."""
from laplace.manuscript import proposal_preflight
from test_literature_joined_workflow import project


def fixture(tmp_path,monkeypatch):
    project(tmp_path,monkeypatch)
    turn={'selection':{'files':['chapters/chapter-01.tex']}}
    edit={'file':'chapters/chapter-01.tex','line_start':2,'line_end':2,'before':'First passage.','after':'Revised passage.','reason':'Clarify'}
    return turn,edit


def test_top_level_lineage_is_rejected_with_precise_per_edit_recovery(tmp_path,monkeypatch):
    turn,edit=fixture(tmp_path,monkeypatch)
    for key in ('develops','evidence_refs'):
        out=proposal_preflight.preflight(tmp_path,'joined',turn,{'edits':[edit],key:[{'id':'not silently lost'}]})
        assert not out['valid']
        assert 'inside each edits[] item' in out['errors'][0]
        assert 'Example:' in out['errors'][0]
        assert out['proposal'][key]==[{'id':'not silently lost'}]


def test_unknown_proposal_and_edit_fields_never_change_intended_effect_silently(tmp_path,monkeypatch):
    turn,edit=fixture(tmp_path,monkeypatch)
    assert not proposal_preflight.preflight(tmp_path,'joined',turn,{'edits':[edit],'claims':['unconsumed']})['valid']
    bad=proposal_preflight.preflight(tmp_path,'joined',turn,{'edits':[{**edit,'develop':['misspelled']}]})
    assert not bad['valid'] and 'unknown edit fields' in bad['errors'][0]


def test_legacy_optional_answer_and_recorded_source_anchor_remain_accepted(tmp_path,monkeypatch):
    turn,edit=fixture(tmp_path,monkeypatch)
    first=proposal_preflight.preflight(tmp_path,'joined',turn,{'edits':[edit]})
    assert first['valid']
    second=proposal_preflight.preflight(tmp_path,'joined',turn,{'answer':'Recorded rationale','edits':first['proposal']['edits']})
    assert second['valid']
    assert second['proposal']['answer']=='Recorded rationale'
    assert second['proposal']['edits'][0]['source_anchor']


def test_apply_wrapper_cannot_silently_discard_lineage(tmp_path):
    import pytest
    from laplace.manuscript import source_application
    with pytest.raises(ValueError,match='inside each edits'):
        source_application.apply_revision(tmp_path,'missing','missing',{'proposal':{'edits':[]},'develops':[{'id':'lost'}]})
