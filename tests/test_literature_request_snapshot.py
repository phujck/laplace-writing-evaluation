"""Fresh request snapshots reduce owner work without weakening completion standing."""
import hashlib,json
from laplace.research import literature_support as support, corpus_ingest
from laplace.work import project_work
from laplace.manuscript import project_structure, manuscript_source, proposal_basis, manuscript_structure
from laplace.research import research_records
from test_logical_planning import _fixture

def test_two_task_scopes_share_structure_then_new_reads_observe_claim_and_source_changes(tmp_path,monkeypatch):
    manuscript=_fixture(tmp_path)
    for ident in ('lit-one','lit-two'):
        project_work.task('logic',{'id':ident,'title':ident,'goal':'Inspect declared definition','kind':'literature-acquisition','logical_target':{'kind':'node','node_id':'def:one'}},tmp_path)
    calls=[];original=project_structure.state
    def observed(*args,**kwargs):calls.append(True);return original(*args,**kwargs)
    monkeypatch.setattr(project_structure,'state',observed)
    context={};one=support.scope('logic',tmp_path,task_id='lit-one',read_context=context);two=support.scope('logic',tmp_path,task_id='lit-two',read_context=context)
    assert len(calls)==1 and one['revision']==two['revision']
    assert one['task_id']=='lit-one' and two['task_id']=='lit-two'
    assert one['ready_for_completion'],one['gaps']
    for ident in ('lit-one','lit-two'):project_work.transition('logic',{'id':ident,'status':'done'},tmp_path)
    full=project_work.state('logic',tmp_path);summary=project_work.summary('logic',tmp_path)
    assert full['tasks']==summary['tasks'] and all(row['status']=='done' for row in summary['tasks'])
    corpus_ingest.rewire_add(tmp_path,'logic',{'kind':'edit-essence','node':'def:one','value':'A stronger definition now includes positivity.'})
    changed=support.scope('logic',tmp_path,task_id='lit-one',read_context={})
    assert changed['revision']!=one['revision']
    assert all(row['status']=='blocked' for row in project_work.summary('logic',tmp_path)['tasks'])
    before=changed['revision'];(manuscript/'main.tex').write_text('\\documentclass{article}\n\\begin{document}\nChanged selected source.\n\\end{document}\n')
    assert support.scope('logic',tmp_path,task_id='lit-one',read_context={})['revision']!=before

def test_fresh_result_observations_invalidate_evidence_bytes_without_rewriting_receipts(tmp_path):
    manuscript=_fixture(tmp_path)
    evidence=manuscript/'measurement.json';evidence.write_text('{"score":1}\n')
    status,recorded=research_records.record('logic',{'kind':'result','id':'measurement:one','result':'measurement.json'},tmp_path)
    assert status==201,recorded
    binding={'id':'measurement:one','revision':recorded['record']['revision']}
    assert corpus_ingest.rewire_add(tmp_path,'logic',{'kind':'set-projection','node':'def:one','value':{'result_bindings':[binding]}}).get('ok')
    first=support.scope('logic',tmp_path,node='def:one',read_context={})
    assert first['claims'][0]['own_evidence'][0]['currentness']=='CURRENT'
    evidence.write_text('{"score":2}\n')
    changed=support.scope('logic',tmp_path,node='def:one',read_context={})
    assert changed['claims'][0]['own_evidence'][0]['currentness']=='STALE_OR_UNRESOLVED'
    assert changed['revision']!=first['revision'] and changed['ready_for_completion'] is False
    assert changed['claims'][0]['own_evidence'][0]['revision']==binding['revision']

def test_many_citations_parse_and_normalize_source_heading_map_once_per_read(tmp_path,monkeypatch):
    manuscript=_fixture(tmp_path)
    path=manuscript/'main.tex';path.write_text('\\documentclass{article}\n\\begin{document}\n\\section{First}\n'+'\\cite{Fixture}.\n'*50+'\\section{Second}\n'+'\\cite{Fixture}.\n'*50+'\\end{document}\n')
    source,spans,_=__import__('laplace.research.references_surface',fromlist=['citation_spans']).citation_spans('logic',tmp_path)
    structure={'sections':[{'id':'first','title':'First','kind':'section','node_ids':['def:one'],'source':{'source_files':[spans[0]['file']]}},{'id':'second','title':'Second','kind':'section','node_ids':['result:one'],'source':{'source_files':[spans[0]['file']]}}]}
    parsed=[];normalized=[];resolve=[]
    old_parse=proposal_basis._heading_spans;old_normal=manuscript_structure._normal_title;old_resolve=manuscript_source.resolve
    monkeypatch.setattr(proposal_basis,'_heading_spans',lambda text:parsed.append(True) or old_parse(text))
    monkeypatch.setattr(manuscript_structure,'_normal_title',lambda title:normalized.append(title) or old_normal(title))
    monkeypatch.setattr(manuscript_source,'resolve',lambda *a,**k:resolve.append(True) or old_resolve(*a,**k))
    placed=support.citation_context('logic',tmp_path,spans,structure=structure,selected_source=source)
    assert len(parsed)==1 and len(normalized)==4 and not resolve
    assert [row['section_ids'] for row in placed]==[['first']]*50+[['second']]*50

def test_shared_snapshot_does_not_share_results_between_different_task_targets(tmp_path):
    _fixture(tmp_path)
    for ident,node in [('definition-task','def:one'),('result-task','result:one')]:
        project_work.task('logic',{'id':ident,'title':ident,'goal':'Inspect exact target','kind':'literature-acquisition','logical_target':{'kind':'node','node_id':node}},tmp_path)
    context={}
    definition=support.scope('logic',tmp_path,task_id='definition-task',read_context=context)
    result=support.scope('logic',tmp_path,task_id='result-task',read_context=context)
    assert [row['id'] for row in definition['claims']]==['def:one']
    assert [row['id'] for row in result['claims']]==['result:one']
    assert definition['revision']!=result['revision']
    assert definition['ready_for_completion'] and not result['ready_for_completion']
    assert result['revision']==support.scope('logic',tmp_path,node='result:one')['revision']
