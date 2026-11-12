"""Public bounded declaration/selector controls; no semantic-store/provider or data export."""
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit, parse_qs

import pytest
from laplace.work import source_inventory as I, owner_discovery as O, source_contracts as C
from laplace.projects import writing_sources, library
from laplace import system

ROOT=Path(__file__).parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import writing_eval_manifest as M
import export_writing_evaluation as E
from test_writing_container_package import context_admits


def fixture(tmp_path):
 root=tmp_path/'public';(root/'src/laplace/system').mkdir(parents=True);(root/'src/example').mkdir()
 (root/'src/example/alpha.py').write_text('PUBLIC α = 7\n')
 (root/'src/example/beta.py').write_text('PUBLIC β = 8\n')
 (root/'docs').mkdir();(root/'docs/public.md').write_text('# Public source guide\n')
 (root/'tests').mkdir();(root/'tests/test_public.py').write_text('def test_public(): assert True\n')
 (root/'project').mkdir();(root/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'public','kind':'project','project_dir':'project'}]}))
 description={'schema_version':system.SCHEMA,'summary':'Public source declaration',
  'subsystems':[{'id':'core.public','kind':'core','summary':'Public fixture owner','modules':['example.*'],'files':[],
   'uses':[],'contracts':['src/example/alpha.py'],'explanation':['docs/public.md'],'evaluators':['tests/test_public.py']}],
  'capabilities':[],'distributions':[{'name':'public','declaration':'pyproject.toml','packages':['example']}]}
 (root/'src/laplace/system/description.json').write_text(json.dumps(description))
 reference=system.subsystem_reference(description['subsystems'][0]);return root,reference


def test_one_distribution_declaration_drives_both_selectors_and_no_private_admission(monkeypatch):
 assert E.OPERATIONAL_INPUTS is M.OPERATIONAL_INPUTS
 assert M.check_docker_selectors(ROOT)['ok']
 assert 'docs/pilot-session-settings.md' in E.OPERATIONAL_INPUTS
 assert 'docs/writing-source-inventory.md' in E.OPERATIONAL_INPUTS
 rules=M.dockerignore_text().splitlines()
 for rel in M.OPERATIONAL_INPUTS:
  if rel.startswith('docs/') and (rel.endswith('.md') or rel.endswith('.ini')) or rel.startswith('scripts/') and rel.endswith('.py'):
   assert context_admits(rules,rel),rel
 for rel in ['profiles/writing/sealed-reader-qualification.json','contract/talk.jsonl','.laplace-state/x','soul/x.md','private/x.md','.env','.auth/token','writing_projects/p/manuscript/main.tex','tests/test_author_history.py','scripts/wake.py']:
  assert not context_admits(rules,rel),rel
 monkeypatch.setattr(M,'OPERATIONAL_INPUTS',(*M.OPERATIONAL_INPUTS,'docs/public-new-guide.md','scripts/public_new_tool.py'))
 assert context_admits(M.dockerignore_text().splitlines(),'docs/public-new-guide.md')
 assert context_admits(M.dockerignore_text().splitlines(),'scripts/public_new_tool.py')


def test_operational_tool_selection_and_all_recipe_targets_follow_one_declaration(tmp_path,monkeypatch):
 tools=[p for p in M.OPERATIONAL_INPUTS if p.startswith('tools/')]
 assert tools==['tools/writing_verbs/gen_routes.py','tools/writing_verbs/reanchor_http_routes.py','tools/writing_verbs/http_routes.csv']
 rules=M.dockerignore_text().splitlines()
 assert all(context_admits(rules,p) for p in tools)
 assert all(not context_admits(rules,p) for p in ['tools/private.py','tools/writing_verbs/private.json','tools/.auth/token'])
 block=M._TOOLS_BEGIN+'\n'.join(M.operational_tool_copy_instructions())+'\n'+M._TOOLS_END
 for name in M.DOCKER_RECIPES:
  original=(ROOT/name).read_text();assert original.count(block)==original.count('COPY scripts ./scripts\n')
  # Generated blocks are the only addition to the original APP instruction stream.
  assert M._docker_recipe_projection(original.replace(block,''))==original
  target=tmp_path/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(original)
 for name in M.DOCKER_SELECTORS:(tmp_path/name).write_text(M.dockerignore_text())
 monkeypatch.setattr(M,'OPERATIONAL_INPUTS',(*M.OPERATIONAL_INPUTS,'tools/writing_verbs/public_added.py'))
 assert not M.check_docker_selectors(tmp_path)['ok']
 assert M.write_docker_selectors(tmp_path)['ok']
 assert context_admits(M.dockerignore_text().splitlines(),'tools/writing_verbs/public_added.py')
 for name in M.DOCKER_RECIPES:
  body=(tmp_path/name).read_text();assert body.count('COPY ["tools/writing_verbs/public_added.py",')==body.count('COPY scripts ./scripts\n')
 (tmp_path/'operational-tools-proof.json').write_text(json.dumps({'tools':tools,'exact_only':True,'clean_targets':4,'refresh_targets':1,'declaration_change_detected_and_generated':True}))


def test_exact_source_rows_paging_native_human_pins_and_kernel_unresolved(tmp_path):
 root,ref=fixture(tmp_path);payload={'facet':'source-inventory','reference':ref,'limit':2,'project_lens':'public'}
 original=(root/'src/example/alpha.py').read_bytes();one=I.read(root,O.owned_workspace('sdk'),payload)
 assert one['kernel']['state']=='UNRESOLVED' and not one['kernel']['lookup_performed']
 assert one['coverage']['known']==4 and len(one['items'])==2 and one['pagination']['next_read']
 seen=list(one['items']);next_request=one['pagination']['next_read']['request'];two=I.read(root,O.owned_workspace('sdk'),next_request)
 seen+=two['items'];assert len({r['path'] for r in seen})==4 and two['basis']==one['basis'] and two['pagination']['next_read'] is None
 row=next(r for r in seen if r['path']=='src/example/alpha.py')
 assert row['sha256']=='sha256:'+hashlib.sha256(original).hexdigest() and 'contract-source' in row['roles'] and row['classification']=='declaration-source'
 native=writing_sources.execute(root,row['read']['payload']);url=urlsplit(row['read']['http']['url']);code,_,raw=library.handle(url.path,parse_qs(url.query),'GET',b'',root)
 assert code==200 and json.loads(raw)['owner_result']['content']==native['content']==original.decode()
 assert row['read']['payload']['expected_sha256']==row['sha256']
 assert next(r for r in seen if r['path'].startswith('tests/'))['classification']=='evaluator-source-not-executed'
 one['items'][0]['roles'].clear();assert I.read(root,O.owned_workspace('sdk'),payload)['items'][0]['roles']
 assert (root/'src/example/alpha.py').read_bytes()==original
 (root/'source-inventory-proof.json').write_text(json.dumps({'first':one,'second':two,'source_read':native},indent=2,ensure_ascii=False))


def test_changed_source_refuses_old_cut_and_read_while_current_is_explicit(tmp_path):
 root,ref=fixture(tmp_path);payload={'facet':'source-inventory','reference':ref,'limit':20};one=I.read(root,O.owned_workspace('sdk'),payload)
 row=next(r for r in one['items'] if r['path']=='src/example/alpha.py');(root/row['path']).write_text('PUBLIC changed\n')
 with pytest.raises(ValueError,match='CHANGED_INPUT'):I.read(root,O.owned_workspace('sdk'),{**payload,'as_of':one['basis']})
 with pytest.raises(ValueError):writing_sources.execute(root,row['read']['payload'])
 current=I.read(root,O.owned_workspace('sdk'),one['pagination']['current_read']['request']);assert current['basis']!=one['basis']


def test_private_and_semantic_families_not_read_unknown_scope_and_budget_refuse(tmp_path,monkeypatch):
 root,ref=fixture(tmp_path);description=json.loads((root/'src/laplace/system/description.json').read_text());owner=description['subsystems'][0]
 (root/'src/laplace/pipeline/canon').mkdir(parents=True);(root/'src/laplace/pipeline/canon/private.md').write_text('PRIVATE_NEVER_READ')
 owner['files']=['src/laplace/pipeline/canon/**','docs/**'];(root/'src/laplace/system/description.json').write_text(json.dumps(description))
 actual=Path.open
 def guarded(path,*a,**k):
  if 'canon' in path.parts:pytest.fail('Semantic/private source body read')
  return actual(path,*a,**k)
 monkeypatch.setattr(Path,'open',guarded)
 value=I.read(root,O.owned_workspace('sdk'),{'facet':'source-inventory','reference':ref})
 assert value['state']=='PARTIAL' and len(value['coverage']['unavailable'])==2 and 'PRIVATE_NEVER_READ' not in json.dumps(value)
 with pytest.raises(ValueError):I.read(root,O.project_scope('elsewhere','native'),{'facet':'source-inventory','reference':ref,'project_lens':'public'})
 with pytest.raises(ValueError):I.read(root,O.owned_workspace('sdk'),{'facet':'source-inventory','reference':{**ref,'identity':{'id':'unknown'}}})
 monkeypatch.setattr(I,'MAX_FILES',1)
 with pytest.raises(ValueError,match='BUDGET'):I.read(root,O.owned_workspace('sdk'),{'facet':'source-inventory','reference':ref})


def test_missing_source_never_falls_back_and_symlink_refuses(tmp_path):
 root=tmp_path/'empty';root.mkdir();ref={'schema_version':'laplace.reference/1','owner':'core.identity','kind':'subsystem','identity':{'id':'core.public'}}
 result=I.read(root,O.owned_workspace('sdk'),{'facet':'source-inventory','reference':ref});assert result['state']=='UNAVAILABLE' and result['basis'] is None
 root,ref=fixture(tmp_path);(root/'src/example/alpha.py').unlink();(root/'src/example/alpha.py').symlink_to(root/'docs/public.md')
 with pytest.raises(ValueError,match='symlink'):I.read(root,O.owned_workspace('sdk'),{'facet':'source-inventory','reference':ref})


def test_existing_contract_provider_registry_semantics_preserved():
 assert C.declarations()==[provider() for provider in C.providers()]
 assert [C.key(r) for r in C.declarations()]==['domain.work:work_review.followup','domain.work:development_source']


def test_registered_contract_versions_are_declaring_source_bound_not_acceptance(tmp_path):
 root=tmp_path/'declared';(root/'src/laplace/system').mkdir(parents=True);(root/'src/laplace/work').mkdir()
 desc={'schema_version':system.SCHEMA,'summary':'Selected public Work declarations',
  'subsystems':[{'id':'domain.work','kind':'domain','summary':'Public Work source','modules':['laplace.work.*'],'files':[],
    'uses':[],'contracts':[],'explanation':[],'evaluators':[]}],
  'capabilities':[],'distributions':[{'name':'public','declaration':'pyproject.toml','packages':['laplace']}]}
 (root/'src/laplace/system/description.json').write_text(json.dumps(desc))
 for provider in C.providers():
  rel=Path('src')/Path(provider.__module__.replace('.','/')).with_suffix('.py')
  (root/rel).write_bytes((ROOT/rel).read_bytes()) # exactly two public code files, never a source archive/fixture copy
 payload={'facet':'source-inventory','reference':system.subsystem_reference(desc['subsystems'][0]),'limit':20}
 value=I.read(root,O.owned_workspace('sdk'),payload)
 assert len(value['contracts'])==2
 for item,declaration in zip(value['contracts'],C.declarations()):
  assert item['state']=='CURRENT_DECLARATION_ONLY' and item['observed_version']==C.version(declaration)
  assert item['segment_bases']==C.bases(declaration) and item['relation_counts']==C.inspect(declaration)['relations']
  assert 'relations' not in item and item['coverage']['known_relations']==len(declaration['relations']) and item['coverage']['inline_relation_rows']==0
  template=item['segment_reads'];selected=next(iter(template['values']));read={**template['request'],template['field']:template['values'][selected]}
  held=O.request(root,O.owned_workspace('sdk'),read)
  assert held['reference']['version']['declaration']==item['observed_version'] and held['item']['basis']==item['segment_bases'][selected]
  assert held['item']['consumers']==[r for r in declaration['relations'] if selected in r['segments']]
  from laplace.web import project_work_surface
  url=urlsplit(template['http']['url']);query=parse_qs(url.query);query[template['query_field']]=[template['values'][selected]]
  code,_,raw=project_work_surface.handle(url.path,query,'GET',repo_root=root)
  assert code==200 and json.loads(raw)['item']==held['item']
  assert item['read']['request']['reference'].get('version') is None # current facts are not a fabricated retained version
  assert item['kernel']['state']=='UNRESOLVED'
  assert item['runtime_source_linkage']['state']=='UNVERIFIED_LOADED_CODE' and not item['runtime_source_linkage']['loaded_code_asserted']
 target=root/'src/laplace/work/development_source.py';target.write_bytes(target.read_bytes()+b'\n# Another source edition\n')
 newer=I.read(root,O.owned_workspace('sdk'),payload)
 missing=[r for r in newer['contracts'] if r['state']=='UNAVAILABLE'];assert len(missing)==1 and 'edition' in missing[0]['reason']
 assert 'observed_version' not in missing[0] and newer['basis']!=value['basis']
 (root/'declaring-source-proof.json').write_text(json.dumps({'matched':value,'different':newer},indent=2))


def test_configured_source_route_is_part_of_observation_cut(tmp_path):
 root,ref=fixture(tmp_path);payload={'facet':'source-inventory','reference':ref};first=I.read(root,O.owned_workspace('sdk'),payload)
 (root/'profiles').mkdir();(root/'profiles/writing_sources.json').write_text(json.dumps({'repositories':{'explicit-source':'.'}}))
 with pytest.raises(ValueError,match='CHANGED_INPUT'):I.read(root,O.owned_workspace('sdk'),{**payload,'as_of':first['basis']})
 current=I.read(root,O.owned_workspace('sdk'),payload)
 assert current['basis']!=first['basis'] and all(r['read']['payload']['repository']=='explicit-source' for r in current['items'])


def test_byte_bounded_source_page_keeps_exact_continuation(tmp_path):
 root,ref=fixture(tmp_path)
 for i in range(30):(root/f'src/example/long_public_module_{i:03d}.py').write_text('PUBLIC = 1\n')
 request={'facet':'source-inventory','reference':ref,'limit':20};value=I.read(root,O.owned_workspace('sdk'),request)
 assert len(json.dumps(value,ensure_ascii=False).encode())<=I.MAX_RESPONSE
 assert 0<len(value['items'])<=20 and value['pagination']['next_read']
 next_page=I.read(root,O.owned_workspace('sdk'),value['pagination']['next_read']['request'])
 assert not ({r['path'] for r in value['items']} & {r['path'] for r in next_page['items']})
 assert next_page['basis']==value['basis']


def test_exact_missing_module_and_input_are_unavailable_not_complete(tmp_path):
 root,ref=fixture(tmp_path);path=root/'src/laplace/system/description.json';desc=json.loads(path.read_text());owner=desc['subsystems'][0]
 owner['modules']=['example.alpha','example.absent'];owner['files']=['deploy/public-missing.toml'];path.write_text(json.dumps(desc))
 value=I.read(root,O.owned_workspace('sdk'),{'facet':'source-inventory','reference':ref})
 missing={x['declaration']:x for x in value['coverage']['unavailable']}
 assert value['state']=='PARTIAL' and set(missing)=={'example.absent','deploy/public-missing.toml'}
 assert all(x['state']=='UNAVAILABLE' for x in missing.values())
 assert all(x['path']!='src/example/beta.py' for x in value['items'])
 (root/'missing-declared-input-proof.json').write_text(json.dumps(value,indent=2))


def test_generated_engineering_owner_output_is_optional_exact_and_no_private_release_widening(tmp_path,monkeypatch):
 from laplace.work import project_work as W
 from laplace.projects import project_handover as H
 carrier=tmp_path/'carrier';carrier.mkdir();assert M.generated_release_files(carrier)==[] and M.generated_release_copy_instructions(carrier)==[]
 root=tmp_path/'origin';root.mkdir();(root/'p').mkdir();(root/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'p','kind':'general','project_dir':'p'}]}))
 W.task('p',{'id':'engineering','title':'Public selected engineering','goal':'One inert owner snapshot Ω'},root)
 scope=O.owned_workspace('sdk');ref=O.work_reference('p','engineering');basis=O.request(root,scope,{'facet':'object','reference':ref})['basis']
 prepared=H.object_request(root,scope,{'project':'p','action':'prepare','request_id':'generated-engineering-output','entries':[{'class':'included','reference':ref,'expected_basis':basis,'permit_export':True}],'max_files':30,'max_rows':30,'max_bytes':200000},door={'origin':'sdk'})
 folder=carrier/M.GENERATED_RELEASE_INPUTS[0];folder.parent.mkdir(parents=True)
 H.object_request(root,scope,{'project':'p','action':'export','reference':prepared['reference'],'expected_basis':prepared['basis'],'destination':str(folder)},door={'origin':'sdk'})
 admitted=M.generated_release_files(carrier);assert admitted and all(path.is_relative_to(folder) for path in admitted)
 assert len(admitted)==json.loads((folder/H.MANIFEST).read_text())['counts']['files']
 assert len(M.generated_release_copy_instructions(carrier))==1 and '--chown=laplace:laplace' in M.generated_release_copy_instructions(carrier)[0]
 rules=M.dockerignore_text().splitlines();assert context_admits(rules,M.GENERATED_RELEASE_INPUTS[0]+'/contract/talk.jsonl')
 assert not context_admits(rules,'release/unrelated/private.json') and not context_admits(rules,'contract/talk.jsonl')
 private=folder/'unlisted-private-name.txt';private.write_text('PRIVATE_MUST_NOT_BE_OPENED')
 actual=Path.open
 def refuse(path,*a,**kw):
  if path==private:pytest.fail('Unlisted private generated file body opened')
  return actual(path,*a,**kw)
 monkeypatch.setattr(Path,'open',refuse)
 with pytest.raises(ValueError,match='unlisted or missing'):M.generated_release_files(carrier)
 (tmp_path/'generated-release-proof.json').write_text(json.dumps({'admitted':[p.relative_to(carrier).as_posix() for p in admitted],'optional_absent':True,'no_broad_release_admission':True,'unlisted_private_body_opened':False},indent=2))
