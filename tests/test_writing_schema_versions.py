"""Source integrity across known, legacy, future, native/HTTP and closure paths."""
import hashlib,importlib.util,json
from pathlib import Path
import pytest
from laplace.web import authoring as session, research_surface as research
from laplace.manuscript import proposal_preflight as proposal
from laplace.native import tools as writing_tools
from laplace.research import research_records
from laplace.representation import writing_bodies
from laplace.writing.records import _bank as records_bank
from laplace.writing.records import _fold as records_fold
from laplace.writing import records as writing_records
from laplace.writing import session_reads
from laplace.core.records import journal
from laplace.pipeline import authoring
from laplace.core.bodies import REFERENCE_SCHEMA as PUBLIC_BODY_SCHEMA

ROOT=Path(__file__).parents[1]
def module(name,file):
 spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/file);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
inventory=module('version_test_inventory','writing_eval_manifest.py');export=module('version_test_export','export_writing_evaluation.py')

@pytest.fixture(autouse=True)
def clear_runtime_index():
 records_fold._CACHE.clear()
 yield
 records_fold._CACHE.clear()

def fixture(root):
 (root/'contract').mkdir();(root/'pyproject.toml').write_text('[project]\nname="version-fixture"\nversion="0.0.0"\n');md=root/'fixture/manuscript';md.mkdir(parents=True)
 (root/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'fixture','kind':'conceptric','project_dir':'fixture','tex_root':'fixture/manuscript'}]}))
 (md/'main.tex').write_text('\\documentclass{article}\n\\begin{document}\nFirst premise.\n\\end{document}\n')
 return md

def stamp(root):return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and not p.name.endswith('.lock') and p.name!='.authoring.lock'}

@pytest.mark.parametrize('tag',['laplace.authoring/99','laplace.authoring/x',None,99])
def test_authoring_future_or_malformed_refuses_before_normalization_native_http_and_write(tmp_path,monkeypatch,tag):
 md=fixture(tmp_path);path=md/'authoring.json';state=authoring._blank('fixture');state.update(schema_version=tag,future_semantics={'meaning':'must not be dropped'});path.write_text(json.dumps(state));before=stamp(tmp_path)
 for contexts in [True,False]:
  with pytest.raises(ValueError,match='Supported: laplace.authoring/1'):authoring._read(path,'fixture',tmp_path,contexts=contexts)
 with pytest.raises(ValueError,match='unsupported schema_version'):authoring.save('fixture',{'base_revision':0,'framing':{'purpose':'new'}},tmp_path)
 with pytest.raises(ValueError,match='unsupported schema_version'):writing_tools.execute(tmp_path,'fixture','work','framing',{'purpose':'new','base_revision':0})
 monkeypatch.setattr(session,'_root',lambda:tmp_path)
 status,_,body=session.handle('/authoring/argument',{},'POST',json.dumps({'project':'fixture','framing':{'purpose':'new'}}).encode())
 assert status==409 and 'Supported: laplace.authoring/1' in json.loads(body)['error']
 assert stamp(tmp_path)==before


def test_authoring_current_and_explicit_tagless_argument_inline_context_roundtrip(tmp_path):
 md=fixture(tmp_path);path=md/'authoring.json';legacy={'argument':{'text':'Exact old argument'},'revision':2,'contexts':[{'id':'CTX-old','structure':{'sections':['one']},'selection_spans':[]}],'framing':{'purpose':'old'}};path.write_text(json.dumps(legacy));original=path.read_bytes()
 loaded=authoring.load('fixture',tmp_path);assert loaded['argument']=='Exact old argument' and path.read_bytes()==original
 saved=authoring.save('fixture',{'base_revision':2,'framing':{'purpose':'new'}},tmp_path);assert saved['argument']=='Exact old argument'
 stored=json.loads(path.read_text());assert stored['schema_version']==authoring.AUTHORING_SCHEMA and stored['contexts']==legacy['contexts']
 assert authoring.load('fixture',tmp_path)['revision']==3

@pytest.mark.parametrize('tag',['laplace.research-records/99','laplace.research-records/x',None,99])
def test_research_future_container_read_record_reconcile_native_http_preserve_bytes(tmp_path,tag):
 md=fixture(tmp_path);path=md/'research_records.json';path.write_text(json.dumps({'schema_version':tag,'records':[],'history':[],'future_semantics':{'proof':'unknown'}}));before=stamp(tmp_path)
 assert research_records._records(md)[1] and 'Supported: laplace.research-records/1' in research_records._records(md)[1]
 payload={'kind':'experiment','id':'experiment:one','question':'Measure bounded fixture','config':'config.json'}
 assert research_records.record('fixture',payload,tmp_path)[0]==409
 status,_,raw=research.handle('/research/record',{'project':['fixture']},'POST',json.dumps(payload).encode(),repo_root=tmp_path);assert status==409 and 'unsupported schema_version' in json.loads(raw)['error']
 with pytest.raises(ValueError,match='unsupported schema_version'):writing_tools.execute(tmp_path,'fixture','work','research_record',payload)
 assert research_records.reconcile('fixture',{'records':[{'id':'experiment:one','expected_revision':'old'}]},tmp_path)[0]==409
 assert stamp(tmp_path)==before

@pytest.mark.parametrize('tag',[None,'laplace.research-records/1'])
def test_current_and_tagless_research_containers_remain_usable(tmp_path,tag):
 md=fixture(tmp_path);data={'records':[],'history':[]}
 if tag:data['schema_version']=tag
 (md/'research_records.json').write_text(json.dumps(data));status,out=research_records.record('fixture',{'kind':'experiment','id':'experiment:one','question':'Measure','config':'config.json'},tmp_path);assert status==201
 assert research_records._records(md)[1] is None and research_records._records(md)[0][0]['id']=='experiment:one'
 saved=writing_tools.execute(tmp_path,'fixture','work','store_artifact',{'path':'observer.txt','content':'Exact scoped result.','before':None,'reason':'HTTP reader then record'})
 status,_,raw=research.handle('/research/artifact',{'project':['fixture'],'scope':['project'],'path':['observer.txt'],'artifact_id':[saved['id']],'expected_sha256':[saved['revision']]},'GET',b'',repo_root=tmp_path);
 assert status==200 and raw==b'Exact scoped result.',(status,raw)
 payload={'kind':'experiment','id':'experiment:two','question':'Valid HTTP record','config':'config.json'}
 status,_,raw=research.handle('/research/record',{'project':['fixture']},'POST',json.dumps(payload).encode(),repo_root=tmp_path);assert status==201 and json.loads(raw)['record']['id']=='experiment:two'
 assert writing_tools.execute(tmp_path,'fixture','review','research',{})['project']=='fixture'

@pytest.mark.parametrize('tag',['laplace.writing-public-body-ref/99','laplace.writing-public-body-ref/x','laplace.writing-public-body-ref',' laplace.writing-public-body-ref/99 ','LAPLACE.WRITING-PUBLIC-BODY-REF/99'])
def test_reserved_future_body_family_strict_refusal_quarantine_and_export_unresolved(tmp_path,tag):
 fixture(tmp_path);ref={'schema_version':tag,'content_handle':'sha256:'+'a'*64,'store':'contract/writing_bodies','bytes':123,'encoding':'application/json'};row={'record':'writing-proposal','id':'WP-one','project':'fixture','proposal':{'edits':[{'body':ref}]}};original=json.dumps(row);before=stamp(tmp_path)
 with pytest.raises(ValueError,match='Supported: '+PUBLIC_BODY_SCHEMA):writing_bodies.resolve_fields(row,tmp_path,strict=True)
 loose=writing_bodies.resolve_fields(row,tmp_path,strict=False);assert loose['proposal']==row['proposal'] and loose['_custody_errors']
 assert json.dumps(row)==original
 with pytest.raises(ValueError,match='unsupported schema_version'):writing_records.bank(tmp_path,row)
 assert stamp(tmp_path)==before
 bodies,missing,unresolved=inventory._body_closure(tmp_path,[row]);assert not bodies and not missing and len(unresolved)==1 and unresolved[0]['reference']==ref
 # Raw fixture row models an existing unsupported historical reference, not a new accepted write.
 md=tmp_path/'fixture/manuscript'
 for name,data in [('projection_plan.json',{'sections':[]}),('references.json',{'associations':[]}),('research_records.json',{'records':[]}),('figure_manifest.json',{'figures':[]})]:(md/name).write_text(json.dumps(data))
 (md/'main.pdf').write_bytes(b'Bounded closure fixture; not a rendered-PDF acceptance.')
 journal.bank_row('contract/talk.jsonl',row,root=tmp_path);destination=tmp_path.parent/(tmp_path.name+'-blocked-export')
 with pytest.raises(ValueError,match='body closure is incomplete'):export.export(tmp_path,destination,'fixture')
 assert not destination.exists()


def test_known_body_reference_and_unrelated_inline_json_share_runtime_export_discriminator(tmp_path):
 fixture(tmp_path);ordinary={'schema_version':'other.family/99','nested':['legacy inline']};row={'record':'writing-proposal','proposal':ordinary}
 assert writing_bodies.resolve_fields(row,tmp_path)==row and inventory._body_closure(tmp_path,[row])==([],[],[])
 stored=records_bank.prepare_custody_row(tmp_path,{'record':'writing-artifact','id':'ART-one','project':'fixture','after':'Exact retained body — '*100})
 assert stored['after']['schema_version']==PUBLIC_BODY_SCHEMA
 assert writing_bodies.resolve_fields(stored,tmp_path)['after']=='Exact retained body — '*100
 bodies,missing,unresolved=inventory._body_closure(tmp_path,[stored]);assert len(bodies)==1 and not missing and not unresolved

@pytest.mark.parametrize('tag',['laplace.source-anchor/99','laplace.source-anchor/x',None,99])
def test_unknown_anchor_never_gains_authority_from_current_sha_or_neighbor_match(tmp_path,tag):
 md=fixture(tmp_path);raw=(md/'main.tex').read_text();anchor=proposal.source_anchor(raw,3,3);anchor['schema_version']=tag;edit={'file':'main.tex','line_start':3,'line_end':3,'before':'First premise.','after':'Revised premise.','source_anchor':anchor}
 assert proposal.proven_current_span(raw,edit) is None
 assert proposal._anchored_matches(raw,edit['before'],anchor)==[]
 turn={'selection':{'files':['main.tex']},'document':{'root':'fixture/manuscript/main.tex','revision':hashlib.sha256(raw.encode()).hexdigest()}}
 checked=proposal.preflight(tmp_path,'fixture',turn,{'edits':[edit]});assert checked['valid'] is False and 'Supported: laplace.source-anchor/1, laplace.source-anchor/2' in checked['errors'][0]
 assert (md/'main.tex').read_text()==raw

@pytest.mark.parametrize('tag',['laplace.source-anchor/1','laplace.source-anchor/2','untagged'])
def test_explicit_supported_and_tagless_anchor_exact_sha_legacy_proofs_remain(tmp_path,tag):
 raw='First line\nLast line';anchor=proposal.source_anchor(raw,1,1)
 if tag=='untagged':anchor.pop('schema_version')
 else:anchor['schema_version']=tag
 assert proposal.proven_current_span(raw,{'before':'First line','source_anchor':anchor})==(1,1)


def test_unknown_retained_anchor_refuses_full_http_application_and_preserves_original_source(tmp_path,monkeypatch):
 from test_writing_controller import _import_project,_seed_revision
 from laplace.manuscript import manuscript_proposals
 records_fold._CACHE.clear()
 md,_=_import_project(tmp_path,files={'main.tex':'\\documentclass{article}\n\\begin{document}\nFirst premise.\n\\end{document}\n'})
 raw=(md/'main.tex').read_text();anchor=proposal.source_anchor(raw,3,3);anchor['schema_version']='laplace.source-anchor/99'
 edit={'file':'main.tex','line_start':3,'line_end':3,'before':'First premise.','after':'Changed premise.','source_anchor':anchor}
 turn=_seed_revision(tmp_path,'fixture',[edit],selection={'files':['main.tex']},suffix='unknown-anchor')
 record=session_reads._records(tmp_path)['turns'][turn];version=manuscript_proposals.proposal_version(record)[0];before=stamp(tmp_path)
 monkeypatch.setattr(session,'_root',lambda:tmp_path)
 status,_,body=session.handle('/authoring/apply',{},'POST',json.dumps({'project':'fixture','turn_id':turn,'proposal_version':version}).encode())
 assert status==409 and 'laplace.source-anchor/99' in json.loads(body)['error']
 assert (md/'main.tex').read_text()==raw and stamp(tmp_path)==before
 records_fold._CACHE.clear()
