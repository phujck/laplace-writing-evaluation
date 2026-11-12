"""Typed scientific records must expose their basis without awarding proof."""
import json

import pytest

from laplace.research import concepts as cs, mathematical_records as mr
from laplace.native import tools as writing_tools
from laplace.pipeline import formal_verification


def project(root):
    manuscript=root/'paper'/'manuscript'; manuscript.mkdir(parents=True)
    (root/'registry_projects.json').write_text(json.dumps({'projects':[{
        'name':'paper','project_dir':'paper','tex_root':'paper/manuscript',
        'manifest':{'document':{'root':'paper/manuscript/main.tex'}}}]}))
    (manuscript/'main.tex').write_text('\\documentclass{article}\n\\begin{document}\nA.\n\\end{document}\n')
    sources=root/'original'; sources.mkdir()
    (root/'profiles').mkdir()
    (root/'profiles'/'writing_sources.json').write_text(json.dumps({'repositories':{'original':'original'}}))
    (sources/'law.tex').write_text(r'''% \label{thm:law} is a comment, not a duplicate
\begin{theorem}[Sum]
\label{thm:law}
For $a,b\in\mathbb{N}$,
\begin{equation}\label{eq:law}a+b=b+a.\end{equation}
\end{theorem}
% The adjacent proof belongs to this statement.
\begin{proof}
Use commutativity.
\end{proof}
\begin{theorem}\label{thm:second}Another statement.\end{theorem}
A separating paragraph.
\begin{proof}This must not be silently attached.\end{proof}
''')
    current=cs.state('paper',root=root)
    status,result=cs.change({'project':'paper','operation':'add_node','node':'thm:law',
        'node_kind':'theorem','essence':'Sum law','parent':'paper://',
        'ref':'original:law.tex#thm:law','base_revision':current['revision']},root=root)
    assert status==200,result
    return sources


def test_source_backed_statement_proof_are_read_but_not_certified(tmp_path):
    project(tmp_path)
    focused=cs.state('paper','thm:law',root=tmp_path)
    record=focused['mathematical_record']
    assert 'a+b=b+a' in record['statement_tex']
    assert record['proof']['text']=='Use commutativity.'
    assert record['proof']['status']=='SOURCE_UNREVIEWED'
    assert record['verification']['status']=='NOT_CHECKED'
    assert record['qualification']['status']=='SOURCE_DOCUMENTED_UNREVIEWED'
    assert record['source_locations'][0]['line_start']==2
    assert record['source_locations'][0]['line_end']==10
    assert not record['qualification']['missing']
    assert 'explicit assumptions' in ' '.join(record['qualification']['indexing_gaps'])


def test_writing_tool_record_roundtrip_preserves_other_projection(tmp_path):
    project(tmp_path)
    before=writing_tools.execute(tmp_path,'paper','work','concept',{'node':'thm:law'})
    result=writing_tools.execute(tmp_path,'paper','work','concept_change',{
        'operation':'set_projection','node':'thm:law','base_revision':before['revision'],
        'value':{'term':'Sum'}})
    saved=writing_tools.execute(tmp_path,'paper','work','concept_change',{
        'operation':'set_mathematics','node':'thm:law','base_revision':result['state']['revision'],
        'value':{'domain':'Natural numbers','assumptions':[{'text':'Peano arithmetic'}],
                 'limitations':['Ordinary addition only.']}})
    assert saved['state']['mathematics']['qualification']=='SOURCE_DOCUMENTED_UNREVIEWED'
    assert saved['read_more']=={'operation':'concept','payload':{'node':'thm:law'}}
    assert 'mathematical_record' not in saved['state']
    assert 'projection' not in saved['state']['focus']
    read=writing_tools.execute(tmp_path,'paper','work','concept',{'node':'thm:law'})
    record=read['mathematical_record']
    assert read['node']['projection']['term']=='Sum'
    assert record['qualification']['status']=='SOURCE_DOCUMENTED_UNREVIEWED'
    assert record['statement_origin']=='SOURCE'
    assert record['verification']['status']=='NOT_CHECKED'
    assert read['mathematical_record']['domain']=='Natural numbers'
    assert 'domain' in read['mathematical_record']['authored_fields']
    # Exact help is the same nested schema the mutation validates.
    help_value=writing_tools.execute(tmp_path,'paper','work','help',{'operation':'concept_change'})
    # `requested_payload_contract` is gone: it returned the owner's whole contract a
    # SECOND time beside the copy inside `action`, which was 75.3 per cent of
    # help structure_change. The property that mattered is unchanged and asserted
    # here instead: every variant help serves is BUILT from the owner's own
    # contract, so the owner is still the one source.
    from laplace.native import declarations as writing_declarations
    variant=writing_declarations.variants('concept_change')['set_mathematics']
    assert variant['properties']['value']==mr.schema()


@pytest.mark.parametrize('value',[
    {'verification':{'status':'CHECKED'}}, {'proof':{'text':'QED','status':'CHECKED'}},
    {'assumptions':[{'text':'Something','node_id':'missing'}]},
    {'sources':[{'path':'law.tex','line_start':4}]},
    {'sources':[{'path':'law.tex','line_start':8,'line_end':4}]},
    {'sources':[{'path':'law.tex','line_start':1,'line_end':2}],'primary_source':1},
    {'formal_targets':[{'file':'Theorem.lean','declaration':'theorem'}]},
])
def test_invalid_or_self_awarded_fields_refused_even_through_projection(tmp_path,value):
    project(tmp_path)
    before=cs.state('paper','thm:law',root=tmp_path)
    for operation,payload in [('set_mathematics',value),('set_projection',{'mathematics':value})]:
        status,result=cs.change({'project':'paper','operation':operation,'node':'thm:law',
            'base_revision':before['revision'],'value':payload},root=tmp_path)
        assert status==422,result
    assert cs.state('paper','thm:law',root=tmp_path)['revision']==before['revision']


def test_source_edit_changes_record_digest_and_missing_labels_do_not_fabricate(tmp_path):
    sources=project(tmp_path)
    initial=cs.state('paper','thm:law',root=tmp_path)
    one=initial['mathematical_record']
    p=sources/'law.tex';p.write_text(p.read_text().replace('Use commutativity.','Use induction.'))
    current=cs.state('paper','thm:law',root=tmp_path)
    two=current['mathematical_record']
    assert one['revision']!=two['revision'] and two['proof']['text']=='Use induction.'
    assert initial['content_revision'] != current['content_revision']
    source=mr.resolve_source('paper','original:law.tex#missing',tmp_path)
    assert source['status']=='UNRESOLVED' and 'label' in source['error']
    assert 'statement_tex' not in source
    source=mr.resolve_source('paper','original:law.tex#thm:second',tmp_path)
    assert source['status']=='READ' and 'proof_text' not in source


def test_authored_mathematics_source_fingerprint_changes_node_content_revision(tmp_path):
    sources = project(tmp_path)
    before = cs.state('paper', 'thm:law', root=tmp_path)
    status, saved = cs.change({'project': 'paper', 'operation': 'set_mathematics', 'node': 'thm:law',
        'base_revision': before['revision'], 'value': {'sources': [
            {'repository': 'original', 'path': 'law.tex', 'label': 'thm:second'}]}}, root=tmp_path)
    assert status == 200, saved
    first = cs.state('paper', 'thm:law', root=tmp_path)
    path = sources / 'law.tex'
    path.write_text(path.read_text(encoding='utf-8').replace('Another statement.', 'Changed authored source.'),
                    encoding='utf-8')
    second = cs.state('paper', 'thm:law', root=tmp_path)
    assert first['content_revision'] != second['content_revision']


def test_equation_label_resolves_containing_theorem_and_source_escape_refused(tmp_path):
    project(tmp_path)
    result=mr.resolve_source('paper','original:law.tex#eq:law',tmp_path)
    assert result['environment']=='theorem' and result['proof_text']=='Use commutativity.'
    escape=mr.resolve_source('paper',{'repository':'original','path':'../registry_projects.json','line_start':1,'line_end':1},tmp_path)
    assert escape['status']=='UNRESOLVED' and 'escapes' in escape['error']


def test_concept_tool_reads_a_label_only_through_its_recorded_source_locator(tmp_path):
    project(tmp_path)
    row = writing_tools.execute(tmp_path, 'paper', 'work', 'concept',
                                {'node': 'thm:law', 'source_index': 0, 'label': 'eq:law'})
    assert row['project'] == 'paper' and row['node'] == 'thm:law'
    assert row['source_index'] == 0 and row['label'] == 'eq:law'
    assert row['status'] == 'READ' and row['environment'] == 'theorem'
    assert row['repository'] == 'original' and row['path'] == 'law.tex'
    assert row['statement_tex'] and row['proof_text']=='Use commutativity.'


def test_follow_source_reference_uses_existing_locator_only(tmp_path):
    project(tmp_path)
    status,_,body=cs.handle('/concepts/source',{'project':'paper','node':'thm:law',
        'source_index':'0','label':'eq:law'},'GET',b'',repo_root=tmp_path)
    result=json.loads(body)
    assert status==200 and result['status']=='READ'
    assert result['label']=='eq:law' and result['environment']=='theorem'
    status,_,body=cs.handle('/concepts/source',{'project':'paper','node':'thm:law',
        'source_index':'44','label':'eq:law'},'GET',b'',repo_root=tmp_path)
    assert status==422


def test_lean_status_uses_only_exact_current_linked_receipt(tmp_path,monkeypatch):
    target={'file':'Sum.lean','declaration':'sum_comm','result_id':'sum','result_revision':'r2'}
    receipt={'file':'Sum.lean','declaration':'sum_comm','result':{'id':'sum','revision':'r2'},
             'proof_status':'CHECKED','stale':False,'superseded':False}
    monkeypatch.setattr(formal_verification,'state',lambda *a,**k:{'proof_status':'CHECKED','receipts':[receipt]})
    node={'kind':'theorem','projection':{'mathematics':{'formal_targets':[target]}}}
    record=mr.read('paper','thm:sum',node,tmp_path)
    assert record['verification']['status']=='CHECKED_DECLARATION'
    assert record['verification']['informal_alignment']=='UNASSESSED'
    assert record['qualification']['status']=='INCOMPLETE'
    node['projection']['mathematics']['formal_targets'].append({**target,'declaration':'unproved'})
    assert mr.read('paper','thm:sum',node,tmp_path)['verification']['status']=='PARTIALLY_CHECKED'
    node['projection']['mathematics']['formal_targets'].pop()
    receipt['stale']=True
    assert mr.read('paper','thm:sum',node,tmp_path)['verification']['status']=='STALE'
    receipt['stale']=False;receipt['result']['revision']='r1'
    assert mr.read('paper','thm:sum',node,tmp_path)['verification']['status']=='NOT_CHECKED'


def test_shared_result_cannot_attribute_unrelated_lean_theorem(tmp_path,monkeypatch):
    receipt={'file':'Other.lean','declaration':'other','result':{'id':'shared','revision':'r1'},
             'proof_status':'CHECKED','stale':False}
    monkeypatch.setattr(formal_verification,'state',lambda *a,**k:{'proof_status':'CHECKED','receipts':[receipt]})
    node={'kind':'theorem','projection':{'result_bindings':[{'id':'shared','revision':'r1'}]}}
    verification=mr.read('paper','thm:sum',node,tmp_path)['verification']
    assert verification['status']=='RELATED_FORMAL_RECEIPT'
    assert verification['receipts']==[] and verification['related_receipts']==[receipt]


def test_changed_authored_statement_cannot_inherit_original_source_proof(tmp_path):
    project(tmp_path)
    node={'kind':'theorem','ref':'original:law.tex#thm:law',
          'projection':{'mathematics':{'statement_tex':'All numbers are prime.'}}}
    record=mr.read('paper','thm:changed',node,tmp_path)
    assert record['statement_origin']=='AUTHORED'
    assert record['proof']=={'text':'','status':'NOT_RECORDED'}
    assert record['qualification']['status']=='INCOMPLETE'
    assert record['source_locations'][0]['proof_text']=='Use commutativity.'


def test_equivalent_source_locators_are_deduped_and_result_environment_is_supported(tmp_path):
    sources=project(tmp_path)
    p=sources/'law.tex';p.write_text(p.read_text().replace('{theorem}','{result}'))
    node={'kind':'result','ref':'original:law.tex#thm:law','projection':{'mathematics':{
        'sources':[{'repository':'original','path':'law.tex','label':'thm:law'}]}}}
    record=mr.read('paper','result:law',node,tmp_path)
    assert len(record['source_locations'])==1
    assert record['sources_omitted']==0
    assert record['source_locations'][0]['environment']=='result'
    assert record['proof']['text']=='Use commutativity.'


def test_differing_source_theorems_require_an_explicit_primary_source(tmp_path):
    sources=project(tmp_path)
    (sources/'other.tex').write_text(r'''\begin{theorem}\label{thm:other}
Every natural number is even.
\end{theorem}
\begin{proof}This fixture proof is intentionally different.\end{proof}
''')
    first={'repository':'original','path':'law.tex','label':'thm:law'}
    second={'repository':'original','path':'other.tex','label':'thm:other'}
    ambiguous={'kind':'theorem','projection':{'mathematics':{'sources':[first,second]}}}

    record=mr.read('paper','thm:ambiguous',ambiguous,tmp_path)

    assert record['statement_tex']==''
    assert record['proof']=={'text':'','status':'NOT_RECORDED'}
    assert len(record['source_ambiguity'])==2
    assert 'unambiguous primary' in ' '.join(record['qualification']['missing'])

    selected={'kind':'theorem','projection':{'mathematics':{
        'sources':[first,second],'primary_source':1}}}
    chosen=mr.read('paper','thm:ambiguous',selected,tmp_path)
    assert 'Every natural number is even' in chosen['statement_tex']
    assert chosen['proof']['text']=='This fixture proof is intentionally different.'
    assert not chosen['source_ambiguity']
