"""Generic small reproductions; no recovered private manuscript bodies are copied."""
import hashlib
from pathlib import Path
import pytest
from laplace.manuscript import manuscript_proposals as proposals, proposal_preflight as preflight
from laplace.writing import records as writing_records
from laplace.writing import session_reads
from laplace.writing.records import _fold as records_fold
from laplace.writing import turn_jobs
from test_writing_controller import _import_project,_seed_revision,_bind_rewrite_fixture,_apply_fixture

@pytest.fixture(autouse=True)
def _clear_owned_fixture_state():
    records_fold._CACHE.clear();turn_jobs._JOBS.clear()
    yield
    records_fold._CACHE.clear();turn_jobs._JOBS.clear()

def edit(file,before,after):return {'file':file,'line_start':1,'line_end':len(before.split('\n')),'before':before,'after':after,'reason':'Generic saved revision.'}

@pytest.mark.parametrize('anchor',[True,False])
@pytest.mark.parametrize('action',['accept','replace-current','merge'])
def test_old_whole_chapter_stub_cannot_be_rebased_to_grown_prefix(tmp_path,monkeypatch,anchor,action):
    stub='\\chapter{Finite case}\nStub prose.'
    manuscript,_=_import_project(tmp_path,files={'main.tex':'\\documentclass{book}\n\\begin{document}\n\\input{chapter}\n\\end{document}\n','chapter.tex':stub})
    change=edit('chapter.tex',stub,'\\chapter{Finite case}\nA complete proposed chapter.\n\\section{Results}\nMore science.')
    if anchor:change['source_anchor']=preflight.source_anchor(stub,1,2)
    turn=_seed_revision(tmp_path,'fixture',[change],selection={'files':['chapter.tex']})
    path=manuscript/'chapter.tex';path.write_text(stub+'\n\\section{Results}\nIndependent current science.\n')
    calls=_bind_rewrite_fixture(monkeypatch,manuscript)
    before=path.read_bytes();row=proposals.preview(tmp_path,'fixture',turn)['edits'][0]
    assert row['status']=='conflict' and not row.get('review_token')
    with pytest.raises(ValueError):proposals.decide(tmp_path,'fixture',{'turn_id':turn,'edit_id':row['edit_id'],'decision':action,'review_token':'cached-old-token','merged_after':change['after']})
    assert path.read_bytes()==before and not calls

@pytest.mark.parametrize('structural',['boundary','duplicate-label'])
def test_staged_invalid_bundle_refuses_before_first_owner_write(tmp_path,monkeypatch,structural):
    raw='\\documentclass{article}\n\\begin{document}\nExisting science.\n\\label{claim:one}\n\\end{document}\n'
    manuscript,_=_import_project(tmp_path,files={'main.tex':raw,'chapter.tex':'Current chapter.'})
    good=edit('chapter.tex','Current chapter.','Improved current chapter.')
    good['source_anchor']=preflight.source_anchor('Current chapter.',1,1)
    if structural=='boundary':bad={'file':'main.tex','line_start':1,'line_end':1,'before':'\\documentclass{article}','after':'\\documentclass{article}\n\\begin{document}\nInjected document.\n\\end{document}','reason':'Invalid prefix document.'}
    else:bad={'file':'main.tex','line_start':3,'line_end':3,'before':'Existing science.','after':'Existing science.\n\\label{claim:one}','reason':'Invalid duplicate identity.'}
    bad['source_anchor']=preflight.source_anchor(raw,bad['line_start'],bad['line_end'])
    turn=_seed_revision(tmp_path,'fixture',[good,bad],selection={'files':['chapter.tex','main.tex']})
    calls=_bind_rewrite_fixture(monkeypatch,manuscript)
    before={p.name:p.read_bytes() for p in manuscript.glob('*.tex')}
    with pytest.raises(ValueError,match='document boundary|duplicate canonical'):_apply_fixture(tmp_path,{'turn_id':turn})
    assert {p.name:p.read_bytes() for p in manuscript.glob('*.tex')}==before and not calls

def test_real_owned_pins_are_projected_as_inverse_basis_not_postimage_preimage(tmp_path,monkeypatch):
    raw='\\documentclass{article}\n\\begin{document}\nA current claim.\n\\end{document}\n'
    manuscript,_=_import_project(tmp_path,files={'main.tex':raw})
    change={'file':'main.tex','line_start':3,'line_end':3,'before':'A current claim.','after':'A revised claim.','reason':'Clarify.'}
    turn=_seed_revision(tmp_path,'fixture',[change],selection={'files':['main.tex']})
    _bind_rewrite_fixture(monkeypatch,manuscript)
    application=_apply_fixture(tmp_path,{'turn_id':turn})
    from laplace.manuscript import projection_viewer
    version=projection_viewer.bank_editor_save(manuscript,manuscript/'main.tex',(manuscript/'main.tex').read_bytes(),author='fixture',surface='walk',source='rewrite')['version_id']
    application={**application,'id':'WA-postimage-fixture','receipts':[{**application['receipts'][0],'version_id':version}]}
    writing_records.bank(tmp_path,application)
    exact=session_reads.session_turn_detail(tmp_path,'fixture',turn,'application',item_id=application['id'])
    basis=exact['application']['edits'][0]['undo_basis']
    assert basis['preimage_version_id'] is None and basis['postimage_version_id']==version
    assert basis['before_sha256']=='sha256:'+hashlib.sha256(raw.encode()).hexdigest()
    assert basis['after_sha256']=='sha256:'+hashlib.sha256((manuscript/'main.tex').read_bytes()).hexdigest()

def test_cross_file_duplicate_label_is_refused_before_bundle_write(tmp_path,monkeypatch):
    root_source='\\documentclass{article}\n\\begin{document}\n\\input{one}\n\\input{two}\n\\end{document}\n'
    manuscript,_=_import_project(tmp_path,files={'main.tex':root_source,'one.tex':'One.','two.tex':'Two.'})
    changes=[edit(name,text,text+'\n\\label{claim:duplicate}') for name,text in [('one.tex','One.'),('two.tex','Two.')]]
    for change in changes:change['source_anchor']=preflight.source_anchor(change['before'],1,1)
    turn=_seed_revision(tmp_path,'fixture',changes,selection={'files':['one.tex','two.tex']})
    calls=_bind_rewrite_fixture(monkeypatch,manuscript)
    with pytest.raises(ValueError,match='duplicate canonical labels across'):_apply_fixture(tmp_path,{'turn_id':turn})
    assert not calls and (manuscript/'one.tex').read_text()=='One.' and (manuscript/'two.tex').read_text()=='Two.'

@pytest.mark.parametrize('legacy',[False,True])
def test_visible_full_file_eof_excludes_final_empty_line_but_does_not_allow_growth(tmp_path,monkeypatch,legacy):
    stub='\\chapter{Finite case}\nA short old file.\n'
    manuscript,_=_import_project(tmp_path,files={'main.tex':'\\documentclass{book}\n\\begin{document}\n\\input{chapter}\n\\end{document}\n','chapter.tex':stub})
    change=edit('chapter.tex',stub.rstrip('\n'),'\\chapter{Finite case}\nWhole replacement with no duplicate labels.')
    change['source_anchor']=preflight.source_anchor(stub,1,len(stub.splitlines()))
    if legacy:
        change['source_anchor']['at_end']=False;change['source_anchor'].pop('schema_version',None)
    turn=_seed_revision(tmp_path,'fixture',[change],selection={'files':['chapter.tex']})
    path=manuscript/'chapter.tex';path.write_text(stub+'\nNew distinct tail.\n\\label{tail:new}\n')
    calls=_bind_rewrite_fixture(monkeypatch,manuscript);before=path.read_bytes()
    row=proposals.preview(tmp_path,'fixture',turn)['edits'][0]
    assert not row.get('review_token') and row['status']=='conflict'
    with pytest.raises(ValueError):_apply_fixture(tmp_path,{'turn_id':turn})
    assert not calls and path.read_bytes()==before

@pytest.mark.parametrize('literal',[r'\verb|\end{document}\label{same}\label{same}|',r'\begin{verbatim}\end{document}\label{same}\label{same}\end{verbatim}',r'\begin{lstlisting}\begin{document}\end{document}\label{same}\label{same}\end{lstlisting}',r'\begin{minted}{tex}\begin{document}\end{document}\label{same}\label{same}\end{minted}'])
def test_literal_tex_examples_are_not_active_boundaries_or_labels(literal):
    before='\\documentclass{article}\n\\begin{document}\nExample.\n\\end{document}\n'
    after=before.replace('Example.',literal)
    assert not preflight.staged_integrity_errors(before,after,is_root=True)
    assert not preflight.duplicate_label_errors({'a':before},{'a':after})

def test_version_qualified_reanchor_cannot_lend_new_prefix_authority_to_old_whole_file(tmp_path,monkeypatch):
    stub='\\chapter{Finite case}\nOld stub.\n'
    manuscript,_=_import_project(tmp_path,files={'main.tex':'\\documentclass{book}\n\\begin{document}\n\\input{chapter}\n\\end{document}\n','chapter.tex':stub})
    old=edit('chapter.tex',stub.rstrip('\n'),'\\chapter{Replacement}\nWhole old chapter.')
    old['source_anchor']=preflight.source_anchor(stub,1,len(stub.splitlines()))
    turn=_seed_revision(tmp_path,'fixture',[old],selection={'files':['chapter.tex']})
    original=proposals.preview(tmp_path,'fixture',turn);v1=original['proposal_version']
    path=manuscript/'chapter.tex';grown=stub+'\n\\section{Expansion}\nTail target.\nCurrent science.\n';path.write_text(grown)
    fresh={**old,'source_anchor':preflight.source_anchor(grown,1,old['line_end'])}
    line=grown.split('\n').index('Tail target.')+1
    tail={'file':'chapter.tex','line_start':line,'line_end':line,'before':'Tail target.','after':'Improved tail.','reason':'Fresh disjoint edit.','source_anchor':preflight.source_anchor(grown,line,line)}
    candidate={'answer':'Different current-prefix proposal','edits':[fresh,tail]};v2=records_fold._proposal_digest(candidate)
    from laplace.pipeline import authoring
    current_context=authoring.build_context('fixture',{'files':['chapter.tex']},repo_root=tmp_path)
    writing_records.bank(tmp_path,{'record':'writing-turn-context-baseline','id':'CTX-v2','turn_id':turn,'project':'fixture',
        **{key:current_context.get(key) for key in ('context_id','dependencies','document','selection')}})
    writing_records.bank(tmp_path,{'record':'writing-proposal','id':'PROP-current-v2','turn_id':turn,'project':'fixture','proposal':candidate})
    calls=_bind_rewrite_fixture(monkeypatch,manuscript)
    current=proposals.preview(tmp_path,'fixture',turn,v2);v2=current['proposal_version'];tail_row=next(row for row in current['edits'] if row['edit_id']==proposals.edit_id(tail))
    proposals.decide(tmp_path,'fixture',{'turn_id':turn,'proposal_version':v2,'edit_id':tail_row['edit_id'],'decision':'accept'})
    before=path.read_bytes();retained=proposals.preview(tmp_path,'fixture',turn,v1)['edits'][0]
    assert retained['status']=='conflict' and not retained.get('review_token') and retained['source_anchor']['at_end']
    with pytest.raises(ValueError):proposals.decide(tmp_path,'fixture',{'turn_id':turn,'proposal_version':v1,'edit_id':retained['edit_id'],'decision':'accept'})
    assert path.read_bytes()==before and len(calls)==1
    # The exact same-version sibling still has valid derived source authority.
    sibling=proposals.preview(tmp_path,'fixture',turn,v2)['edits'][0]
    assert sibling['status']=='pending' and sibling.get('review_token')

def test_unqualified_legacy_reanchor_is_retained_but_not_actionable(tmp_path):
    stub='\\chapter{Finite case}\nOld stub.\n'
    manuscript,_=_import_project(tmp_path,files={'main.tex':'\\documentclass{book}\n\\begin{document}\n\\input{chapter}\n\\end{document}\n','chapter.tex':stub})
    change=edit('chapter.tex',stub.rstrip('\n'),'Whole replacement.');change['source_anchor']=preflight.source_anchor(stub,1,len(stub.splitlines()))
    turn=_seed_revision(tmp_path,'fixture',[change],selection={'files':['chapter.tex']})
    path=manuscript/'chapter.tex';grown=stub+'\nNew current tail.\n';path.write_text(grown)
    source_anchor=preflight.source_anchor(grown,1,change['line_end'])
    writing_records.bank(tmp_path,{'record':'writing-proposal-anchor','id':'ANCHOR-unqualified','turn_id':turn,'project':'fixture','edit_id':proposals.edit_id(change),'source_anchor':source_anchor,'caused_by':'WA-unknown'})
    row=proposals.preview(tmp_path,'fixture',turn)['edits'][0]
    assert row['status']=='conflict' and not row.get('review_token') and row['source_anchor']['at_end']
    assert session_reads._records(tmp_path)['turns'][turn]['proposal_anchors'][row['edit_id']]==source_anchor

@pytest.mark.parametrize('comment',[r'% \begin{verbatim}',r'% \verb|ignored| \begin{verbatim}',r'\\% \begin{lstlisting}'])
def test_commented_literal_openers_cannot_hide_active_boundaries_or_labels(tmp_path,monkeypatch,comment):
    raw='\\documentclass{article}\n'+comment+'\n\\begin{document}\nCurrent science.\n\\label{claim:one}\n\\end{document}\n'
    manuscript,_=_import_project(tmp_path,files={'main.tex':raw})
    actual=(manuscript/'main.tex').read_text()
    change={'file':'main.tex','line_start':4,'line_end':4,'before':'Current science.','after':'Changed.\n\\begin{document}\n\\label{claim:one}','reason':'Invalid active structure.','source_anchor':preflight.source_anchor(actual,4,4)}
    assert preflight.staged_integrity_errors(raw,raw.replace('Current science.',change['after']),is_root=True)
    turn=_seed_revision(tmp_path,'fixture',[change],selection={'files':['main.tex']});calls=_bind_rewrite_fixture(monkeypatch,manuscript)
    before=(manuscript/'main.tex').read_bytes()
    with pytest.raises(ValueError,match='document boundary|duplicate canonical'):_apply_fixture(tmp_path,{'turn_id':turn})
    assert not calls and (manuscript/'main.tex').read_bytes()==before

@pytest.mark.parametrize('literal',[r'\verb|literal % \begin{document}\label{same}\label{same}|',r'\verb%\begin{document}\label{same}\label{same}%',r'\begin{verbatim}% ordinary literal percent\n\begin{document}\label{same}\label{same}\end{verbatim}'])
def test_literal_percent_does_not_turn_literal_content_into_active_commands(literal):
    before='\\documentclass{article}\n\\begin{document}\nExample.\n\\end{document}\n';after=before.replace('Example.',literal)
    assert not preflight.staged_integrity_errors(before,after,is_root=True)
    assert not preflight.duplicate_label_errors({'a':before},{'a':after})

def test_escaped_percent_does_not_hide_active_commands():
    before='\\documentclass{article}\n\\begin{document}\nExample.\n\\end{document}\n'
    after=before.replace('Example.',r'\% \begin{document}')
    assert preflight.staged_integrity_errors(before,after,is_root=True)
