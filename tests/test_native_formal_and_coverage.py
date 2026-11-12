"""Canonical theorem binding and truthful legacy dependency reconciliation."""
import json
from pathlib import Path

import pytest
from laplace.research import concepts as cs, mathematical_records as mr
from laplace.native import tools as writing_tools
from laplace.research import research_records
from laplace.research import research_catalogue
from laplace.research import research_observation
from laplace.pipeline import formal_verification as fv


def fixture(root):
    manuscript = root / 'paper/manuscript'; manuscript.mkdir(parents=True)
    (root/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'paper','kind':'conceptric',
        'project_dir':'paper','tex_root':'paper/manuscript','manifest':{'document':{'root':'paper/manuscript/main.tex'}}}]}))
    (manuscript/'main.tex').write_text('\\documentclass{article}\n\\begin{document}\nText.\n\\end{document}\n')
    original = root/'original'; original.mkdir()
    (root/'profiles').mkdir()
    (root/'profiles/writing_sources.json').write_text(json.dumps({'repositories':{'original':'original'}}))
    (original/'sum.tex').write_text('\\begin{theorem}\\label{thm:sum}\nFor natural numbers $a,b$, $a+b=b+a$.\n\\end{theorem}\n')
    state = cs.state('paper',root=root)
    status, out = cs.change({'project':'paper','operation':'add_node','node':'thm:sum','node_kind':'theorem',
        'essence':'Commutativity of natural addition','parent':'paper://','ref':'original:sum.tex#thm:sum','base_revision':state['revision']},root=root)
    assert status == 200, out
    formal = manuscript/'formal'; formal.mkdir()
    (formal/'Addition.lean').write_text('theorem addition_commutes (a b : Nat) : a + b = b + a := by\n  exact Nat.add_comm a b\n')
    (formal/'lean-toolchain').write_text('leanprover/lean4:v4.34.1\n')
    (formal/'lakefile.toml').write_text('name = "formalfixture"\nversion = "0.1.0"\ndefaultTargets = []\n')
    (formal/'lake-manifest.json').write_text(json.dumps({'version':'1.1.0','packagesDir':'.lake/packages','packages':[],'name':'formalfixture','lakeDir':'.lake'}))
    (formal/'manifest.json').write_text(json.dumps({'lean_toolchain':'formal/lean-toolchain',
        'lake_manifest':'formal/lake-manifest.json','project_root':'formal','approved_axioms':[]}))
    return manuscript


def check(root, target):
    return writing_tools.execute(root,'paper','work','proof_check',{'file':'formal/Addition.lean',
        'declaration':'addition_commutes','concept_id':target['id'],'concept_revision':target['revision'],
        'source_revision':target['source_revision']})


def test_native_concept_target_no_dummy_result_no_verification_recursion(tmp_path, monkeypatch):
    base = fixture(tmp_path)
    # A target is pure: reading it cannot enter formal.state, including when it
    # has explicit formal target metadata. This catches the recursive cycle.
    monkeypatch.setattr(fv, 'state', lambda *a,**kw: (_ for _ in ()).throw(AssertionError('recursive formal state')))
    target = fv.concept_target('paper','thm:sum',tmp_path)
    assert 'a+b=b+a' in target['statement_tex']
    assert target['source_locations'][0]['status'] == 'READ'
    monkeypatch.setattr(fv,'_tool_state',lambda root=None, lean_version=None:{'available':False,'reason':'isolated unavailable'})
    receipt = check(tmp_path,target)
    assert receipt['proof_status'] == 'UNAVAILABLE'
    assert receipt['concept']['id'] == 'thm:sum' and 'result' not in receipt
    assert not (base/'research_records.json').exists()
    assert not (base/'formal/results.json').exists()


@pytest.mark.skipif(not Path('.laplace-tools/lean/v4.34.1/bin/lake').is_file(),reason='pinned Lean unavailable')
def test_real_lean_native_binding_and_source_content_invalidation(tmp_path, monkeypatch):
    base = fixture(tmp_path)
    monkeypatch.setenv('LAPLACE_LEAN_LAKE',str(Path('.laplace-tools/lean/v4.34.1/bin/lake').resolve()))
    target = writing_tools.execute(tmp_path,'paper','work','proof_targets',{'node':'thm:sum'})['targets'][0]
    focused = cs.state('paper','thm:sum',root=tmp_path)
    assert target['revision'] == focused['content_revision']
    receipt = check(tmp_path,target)
    assert receipt['proof_status'] == 'CHECKED', receipt
    assert receipt['informal_alignment'] == 'UNASSESSED'
    assert receipt['axioms_audit']['observed'] == [] and receipt['axioms_audit']['exit_code'] == 0
    state = fv.state('paper',repo_root=tmp_path)
    assert state['proof_status'] == 'CHECKED' and not state['receipts'][-1]['stale']
    record = cs.state('paper','thm:sum',root=tmp_path)['mathematical_record']
    assert record['verification']['status'] == 'CHECKED_DECLARATION'
    assert record['verification']['informal_alignment'] == 'UNASSESSED'
    assert fv.concept_target('paper','thm:sum',tmp_path)['revision'] == target['revision']
    assert not (base/'research_records.json').exists()
    # Canonical source content, independently of the Lean proof file, invalidates.
    source = tmp_path/'original/sum.tex'
    source.write_text(source.read_text().replace('natural numbers','integers'))
    assert fv.state('paper',repo_root=tmp_path)['receipts'][-1]['stale']
    assert cs.state('paper','thm:sum',root=tmp_path)['mathematical_record']['verification']['status'] == 'STALE'
    with pytest.raises(ValueError,match='stale'):
        check(tmp_path,target)
    refreshed = fv.concept_target('paper','thm:sum',tmp_path)
    assert refreshed['revision'] != target['revision'] and refreshed['source_revision'] != target['source_revision']


def test_native_target_rejects_changed_content_and_mixed_binding(tmp_path, monkeypatch):
    fixture(tmp_path)
    target = fv.concept_target('paper','thm:sum',tmp_path)
    with pytest.raises(ValueError,match='source_revision is stale'):
        check(tmp_path,{**target,'source_revision':'wrong'})
    with pytest.raises(ValueError,match='exactly one'):
        fv.check('paper',file='formal/Addition.lean',declaration='addition_commutes',
            concept_id='thm:sum',concept_revision=target['revision'],source_revision=target['source_revision'],
            result_id='unrelated-specimen',result_revision='fake',repo_root=tmp_path)
    current = cs.state('paper','thm:sum',root=tmp_path)
    status,out = cs.change({'project':'paper','operation':'set_mathematics','node':'thm:sum',
        'base_revision':current['revision'],'value':{'formal_targets':[{'file':'formal/Addition.lean',
            'declaration':'addition_commutes','concept_id':'thm:sum'}]}},root=tmp_path)
    assert status == 200, out
    assert fv.concept_target('paper','thm:sum',tmp_path)['revision'] != target['revision']


def test_authored_formal_target_is_checkable_without_external_source_but_origin_and_gaps_remain_explicit(tmp_path, monkeypatch):
    fixture(tmp_path)
    current=cs.state('paper',root=tmp_path)
    status,out=cs.change({'project':'paper','operation':'add_node','node':'thm:authored-sum',
        'node_kind':'theorem','essence':'Author-originated addition statement','parent':'paper://',
        'base_revision':current['revision']},root=tmp_path)
    assert status==200,out
    current=cs.state('paper','thm:authored-sum',root=tmp_path)
    status,out=cs.change({'project':'paper','operation':'set_mathematics','node':'thm:authored-sum',
        'base_revision':current['revision'],'value':{'statement_tex':'For all $a,b\\in\\mathbb{N}$, $a+b=b+a$.'}},root=tmp_path)
    assert status==200,out

    target=fv.concept_target('paper','thm:authored-sum',tmp_path)

    assert target['binding_ready'] is True
    assert target['statement_origin']=='AUTHORED' and target['origin_posture']=='AUTHOR_ORIGINATED'
    assert target['source_locations']==[]
    assert target['documentation_status']=='INCOMPLETE'
    assert 'externally established' in target['binding_reason']
    monkeypatch.setattr(fv,'_tool_state',lambda root=None, lean_version=None:{'available':False,'reason':'isolated unavailable'})
    receipt=writing_tools.execute(tmp_path,'paper','work','proof_check',{'file':'formal/Addition.lean',
        'declaration':'addition_commutes','concept_id':target['id'],'concept_revision':target['revision'],
        'source_revision':target['source_revision']})
    assert receipt['proof_status']=='UNAVAILABLE'
    assert receipt['concept']['id']=='thm:authored-sum'


def test_formal_target_exposes_readable_proof_and_explicit_empty_assumptions(tmp_path):
    fixture(tmp_path)
    current=cs.state('paper',root=tmp_path)
    status,out=cs.change({'project':'paper','operation':'add_node','node':'thm:reader-proof',
        'node_kind':'theorem','essence':'Readable proof target','parent':'paper://',
        'base_revision':current['revision']},root=tmp_path)
    assert status==200,out
    current=cs.state('paper','thm:reader-proof',root=tmp_path)
    status,out=cs.change({'project':'paper','operation':'set_mathematics','node':'thm:reader-proof',
        'base_revision':current['revision'],'value':{'statement_tex':'P \\to P','assumptions':[],
        'proof':{'text':'Assume $P$; the conclusion is immediate.'}}},root=tmp_path)
    assert status==200,out
    target=fv.concept_target('paper','thm:reader-proof',tmp_path)
    assert target['assumptions_authored'] is True and target['assumptions']==[]
    assert target['proof']['text']=='Assume $P$; the conclusion is immediate.'


def legacy_record(root, base, ident='result:old'):
    (base/'result.json').write_text('{"score": 2}\n')
    (base/'figure.txt').write_text('Observed drawing.\n')
    row = {'kind':'result','id':ident,'scope':'manuscript','result':'result.json','title':'Preserve title',
           'summary':'Preserve interpretation','limitations':'String-valued authored limits',
           'custom_scientific_metadata':{'units':'dimensionless'},
           'artifacts':[{'path':'figure.txt','label':'Drawing','caption':'Preserve this caption'}],
           'provenance':{'dependencies':[research_observation._relative_digest(base,'result.json')],'recorded_at':1.0}}
    row['revision']=research_records._record_revision(row)
    (base/'research_records.json').write_text(json.dumps({'records':[row],'history':[]}))
    return row


def test_legacy_added_coverage_is_untracked_reconcile_preserves_full_history(tmp_path):
    base=fixture(tmp_path); original=legacy_record(tmp_path,base)
    before=(base/'research_records.json').read_bytes()
    observed=research_catalogue.state_payload('paper',tmp_path)['results'][0]
    assert observed['currentness']=='UNTRACKED'
    assert observed['dependency_coverage']['newly_untracked'][0]['path']=='figure.txt'
    assert not observed['dependency_coverage']['changed_pins']
    assert (base/'research_records.json').read_bytes()==before  # reads never migrate
    out=writing_tools.execute(tmp_path,'paper','work','research_reconcile',{
        'records':[{'id':original['id'],'expected_revision':original['revision']}]})
    assert out['records'][0]['coverage_reconciliation']['historical_verification']=='NOT_ESTABLISHED'
    stored=json.loads((base/'research_records.json').read_text())
    current=stored['records'][0]
    assert {k:v for k,v in current.items() if k not in ('provenance','revision')}=={k:v for k,v in original.items() if k not in ('provenance','revision')}
    assert stored['history'][0]['record']==original
    assert current['provenance']['recorded_at']==1.0
    assert current['revision'] != original['revision']
    assert research_catalogue.state_payload('paper',tmp_path)['results'][0]['currentness']=='CURRENT'
    (base/'figure.txt').write_text('Changed after first observation.')
    assert research_catalogue.state_payload('paper',tmp_path)['results'][0]['currentness']=='STALE'


def test_reconcile_refuses_changed_pins_and_batch_is_atomic(tmp_path):
    base=fixture(tmp_path); original=legacy_record(tmp_path,base)
    (base/'result.json').write_text('{"score":999}')
    assert research_records._currentness(base,[original],base.parent)['status']=='STALE'
    before=(base/'research_records.json').read_bytes()
    status,result=research_records.reconcile('paper',{'records':[{'id':original['id'],'expected_revision':original['revision']}]},tmp_path)
    assert status==409 and 'changed' in result['error']
    assert (base/'research_records.json').read_bytes()==before
    (base/'result.json').write_text('{"score": 2}\n')
    status,result=research_records.reconcile('paper',{'records':[{'id':original['id'],'expected_revision':original['revision']},
        {'id':'missing','expected_revision':'not-present'}]},tmp_path)
    assert status==404 and (base/'research_records.json').read_bytes()==before


def test_partial_record_renewal_preserves_scope_result_title_limits_and_custom_fields(tmp_path):
    base=fixture(tmp_path); original=legacy_record(tmp_path,base)
    status,result=research_records.record('paper',{'record':{'id':original['id'],'kind':'result','summary':'Updated interpretation'},
        'expected_revision':original['revision']},tmp_path)
    assert status==200
    current=result['record']
    for key in ('result','title','limitations','scope','custom_scientific_metadata','artifacts'):
        assert current[key]==original[key]
    assert current['summary']=='Updated interpretation'
    from laplace.native.contracts import exact_contract
    contract=exact_contract('research_record',permitted=True)['input']['properties']['record']['properties']
    assert 'result' in contract and 'title' in contract and contract['limitations']['type']==['string','array']


@pytest.mark.skipif(not Path('.laplace-tools/lean/v4.34.1/bin/lake').is_file(),reason='pinned Lean unavailable')
def test_axiom_audit_belongs_to_checked_declaration_not_an_earlier_print(tmp_path, monkeypatch):
    base=fixture(tmp_path)
    monkeypatch.setenv('LAPLACE_LEAN_LAKE',str(Path('.laplace-tools/lean/v4.34.1/bin/lake').resolve()))
    manifest=base/'formal/manifest.json'
    configuration=json.loads(manifest.read_text());configuration['approved_axioms']=['propext']
    manifest.write_text(json.dumps(configuration))
    (base/'formal/Addition.lean').write_text('#print axioms propext\ntheorem addition_commutes : True := Classical.choice (show Nonempty True from ⟨True.intro⟩)\n')
    target=fv.concept_target('paper','thm:sum',tmp_path)
    receipt=check(tmp_path,target)
    assert receipt['proof_status']=='REJECTED'
    assert 'Classical.choice' in receipt['axioms_audit']['forbidden']


def test_formal_target_reader_title_kind_and_parent_do_not_enter_the_binding_handle(tmp_path):
    import hashlib
    fixture(tmp_path)
    current=cs.state('paper','thm:sum',root=tmp_path)
    status,out=cs.change({'project':'paper','operation':'set_projection','node':'thm:sum',
        'base_revision':current['revision'],'value':{'title':'Natural addition commutes'}},root=tmp_path)
    assert status==200,out
    target=fv.concept_target('paper','thm:sum',tmp_path)
    assert target['title']=='Natural addition commutes'
    assert target['concept_kind']=='theorem' and target['kind']=='concept'
    assert target['parent']=='paper://'
    reader_fields={'handle','title','concept_kind','parent','proof','limitations','assumptions_authored'}
    binding={key:value for key,value in target.items() if key not in reader_fields}
    expected='sha256:'+hashlib.sha256(json.dumps(binding,sort_keys=True,default=str).encode()).hexdigest()
    assert target['handle']==expected
    changed_reader={**target,'title':'Another display name','concept_kind':'lemma','parent':'somewhere'}
    assert {key:value for key,value in changed_reader.items() if key not in reader_fields}==binding
