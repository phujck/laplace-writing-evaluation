"""Composed artifact result links across layouts, history and native/HTTP readers."""
from __future__ import annotations
import hashlib,json
from urllib.parse import parse_qs,urlsplit
import pytest
from laplace.native import tools
from laplace.web import research_surface as research
from laplace.writing import reads
from laplace.writing import session_reads
from laplace.core.records import journal

def projects(root):
 (root/'contract').mkdir()
 rows=[]
 for name,directory in [('alpha','owned bundle/nested α'),('beta','different/project root')]:
  base=root/directory;man=base/'manuscript';man.mkdir(parents=True);(man/'main.tex').write_text('\\documentclass{article}\n\\begin{document}Text\\end{document}\n')
  rows.append({'name':name,'kind':'conceptric','project_dir':directory,'tex_root':directory+'/manuscript'})
 (root/'registry_projects.json').write_text(json.dumps({'projects':rows}))
 return {r['name']:root/r['project_dir'] for r in rows}

def http(root,read,extra=None):
 q=parse_qs(urlsplit(read['url']).query)
 if extra:q.update({k:[v] for k,v in extra.items()})
 status,_,raw=research.handle('/research/artifact',q,'GET',b'',repo_root=root)
 return status,raw

def store(root,project,path='result notes/check α.txt',scope='project',content='Exact observation.\n'):
 return tools.execute(root,project,'work','store_artifact',{'path':path,'scope':scope,'before':None,'content':content,'reason':'Result-link integration fixture'})

@pytest.mark.parametrize('scope',['project','manuscript'])
def test_owner_link_native_and_http_use_same_pinned_bytes_across_registered_layouts(tmp_path,scope):
 projects(tmp_path);created=store(tmp_path,'alpha',scope=scope);read=tools.execute(tmp_path,'alpha','review','read_artifact',{'id':created['id']})
 assert read['human_read']==created['human_read']
 assert 'provider working directory' in read['link_instruction']
 assert read['human_read']['scope']==scope
 assert '%CE%B1' in read['human_read']['url'] and 'result+notes' in read['human_read']['url']
 status,raw=http(tmp_path,read['human_read']);assert status==200 and raw.decode()==read['content']
 status,raw=http(tmp_path,read['human_read'],{'format':'json'});assert status==200
 projection=json.loads(raw);assert projection['sha256']==read['human_read']['expected_sha256'] and projection['scope']==scope
 assert created['human_read']['artifact_id']==created['id']
 compact=tools._compact_write_response('alpha','store_artifact',{'path':'result notes/check α.txt'},created)
 assert compact['human_read']==created['human_read'] and compact['artifact_path']==created['artifact_path']
 with pytest.raises(ValueError,match='review'):store_payload={'path':'denied.txt','before':None,'content':'No','reason':'No'};tools.execute(tmp_path,'alpha','review','store_artifact',store_payload)


def test_receipt_route_cannot_change_project_scope_path_pin_or_escape_via_symlink(tmp_path):
 roots=projects(tmp_path);one=store(tmp_path,'alpha',content='Identical bytes\n');two=store(tmp_path,'beta',content='Identical bytes\n')
 assert http(tmp_path,one['human_read'])[1]==b'Identical bytes\n' and http(tmp_path,two['human_read'])[1]==b'Identical bytes\n'
 for edits in [{'project':'beta'},{'scope':'manuscript'},{'path':'../outside.txt'},{'path':two['path']},{'expected_sha256':'f'*64}]:
  assert http(tmp_path,one['human_read'],edits)[0]==422
 target=roots['alpha']/one['artifact_path'];target.unlink();outside=tmp_path/'outside.txt';outside.write_text('A\n');target.symlink_to(outside)
 assert http(tmp_path,one['human_read'])[0]==422


def test_saved_receipt_link_refuses_changed_bytes_while_explicit_current_read_is_separate(tmp_path):
 roots=projects(tmp_path);created=store(tmp_path,'alpha');(roots['alpha']/created['artifact_path']).write_text('Changed after receipt.\n')
 status,raw=http(tmp_path,created['human_read']);assert status==409 and 'recorded bytes were not returned' in json.loads(raw)['error']
 read=tools.execute(tmp_path,'alpha','review','read_artifact',{'id':created['id']})
 assert read['recorded_revision']==created['revision'] and read['current_revision']!=created['revision']
 assert 'artifact_id' not in read['human_read']
 assert http(tmp_path,read['human_read'])[1]==b'Changed after receipt.\n'


def test_historical_turn_links_join_exact_store_action_without_rewriting_original_reply(tmp_path):
 roots=projects(tmp_path);created=store(tmp_path,'alpha');turn='WT-historical';session='WS-historical';bad='/made-up/provider/cwd/owned bundle/nested α/result notes/check α.txt'
 journal.bank_row('contract/talk.jsonl',{'record':'writing-session','id':session,'project':'alpha','role':'author'},root=tmp_path)
 journal.bank_row('contract/talk.jsonl',{'record':'writing-turn','id':turn,'session_id':session,'project':'alpha','text':'Save a result'},root=tmp_path)
 payload={'path':created['artifact_path'],'scope':'project'};summary=tools._action_summary('alpha','store_artifact',payload,created);summary.pop('human_read');summary['links']=[]
 journal.bank_row('contract/talk.jsonl',{'record':'writing-tool-action','id':'ACTION-historical','project':'alpha','turn_id':turn,'operation':'store_artifact','payload':payload,'outcome':summary},root=tmp_path)
 reply=f'[observation]({bad})';journal.bank_row('contract/talk.jsonl',{'record':'writing-reply','id':'WR-historical','project':'alpha','turn_id':turn,'session_id':session,'text':reply,'status':'completed'},root=tmp_path)
 observed=session_reads.session_turn_detail(tmp_path,'alpha',turn,view='summary')['turn']
 assert observed['reply']['text']==reply
 link=observed['result_links'][0];assert link['artifact_id']==created['id'] and link['expected_sha256']==created['revision']
 assert bad not in link['aliases'] and link['turn_id']==turn
 action=session_reads.session_turn_detail(tmp_path,'alpha',turn,view='actions')['items'][0];assert action['outcome']['human_read']['url']==link['url']
 assert http(tmp_path,link)[1]==b'Exact observation.\n'
 (roots['alpha']/created['artifact_path']).write_text('Changed.\n')
 later=session_reads.session_turn_detail(tmp_path,'alpha',turn,view='summary')['turn']['result_links'][0]
 assert later==link and http(tmp_path,later)[0]==409
 (roots['alpha']/created['artifact_path']).unlink();assert http(tmp_path,later)[0]==404
 assert session_reads.session_turn_detail(tmp_path,'alpha',turn,view='summary')['turn']['reply']['text']==reply


def test_duplicate_artifact_ids_are_project_scoped_and_ambiguous_within_one_project(tmp_path):
 roots=projects(tmp_path)
 for project,content in [('alpha','A\n'),('beta','B\n')]:
  (roots[project]/'same.txt').write_text(content)
  journal.bank_row('contract/talk.jsonl',{'record':'writing-artifact','id':'ART-shared','project':project,'path':str((roots[project]/'same.txt').relative_to(tmp_path)),'artifact_path':'same.txt','scope':'project','sha256':hashlib.sha256(content.encode()).hexdigest()},root=tmp_path)
 a=tools.execute(tmp_path,'alpha','review','read_artifact',{'id':'ART-shared'});b=tools.execute(tmp_path,'beta','review','read_artifact',{'id':'ART-shared'})
 assert http(tmp_path,a['human_read'])[1]==b'A\n' and http(tmp_path,b['human_read'])[1]==b'B\n'
 journal.bank_row('contract/talk.jsonl',{'record':'writing-artifact','id':'ART-shared','project':'alpha','path':'wrong.txt','sha256':'0'*64},root=tmp_path)
 assert http(tmp_path,a['human_read'])[0]==422


def test_read_only_import_uses_its_declared_state_workspace_in_both_readers(tmp_path):
 roots=projects(tmp_path);registry=json.loads((tmp_path/'registry_projects.json').read_text());registry['projects'][0]['manifest']={'document':{'read_only':True,'state_dir':'engine state/alpha'}}
 (tmp_path/'registry_projects.json').write_text(json.dumps(registry));state=tmp_path/'engine state/alpha';state.mkdir(parents=True)
 original=(roots['alpha']/'manuscript/main.tex').read_bytes();created=store(tmp_path,'alpha')
 assert (state/created['artifact_path']).is_file() and not (roots['alpha']/created['artifact_path']).exists()
 read=tools.call(tmp_path,'alpha','review',{'operation':'read_artifact','payload':{'id':created['id']}})
 assert http(tmp_path,read['human_read'])[1]==read['content'].encode()
 # An unindexed path read publishes a current-byte URL using the SAME state root.
 path_read=tools.call(tmp_path,'alpha','review',{'operation':'read_artifact','payload':{'path':created['artifact_path'],'scope':'project'}})
 assert 'artifact_id' not in path_read['human_read'];assert http(tmp_path,path_read['human_read'])[1]==read['content'].encode()
 assert http(tmp_path,path_read['human_read'],{'path':'authoring.json'})[0]==422
 with pytest.raises(ValueError,match='read-only'):store(tmp_path,'alpha',path='forbidden.txt',scope='manuscript')
 assert (roots['alpha']/'manuscript/main.tex').read_bytes()==original
 # Existing source-companion project reads keep their original registered root.
 (roots['alpha']/'source-note.txt').write_text('Original imported companion.\n')
 status,_,raw=research.handle('/research/artifact',{'project':['alpha'],'scope':['project'],'path':['source-note.txt']},'GET',b'',repo_root=tmp_path)
 assert status==200 and raw==b'Original imported companion.\n'


def test_result_projection_does_not_adopt_other_turn_or_missing_ambiguous_receipt():
 turn={'id':'WT-selected','project':'alpha','tool_actions':[{'id':'ACTION-one','project':'alpha','turn_id':'WT-selected','operation':'store_artifact','payload':{'path':'same.txt','scope':'project'},'outcome':{'receipts':['ART-one'],'revisions':{'revision':'a'*64}}}]}
 record={'project':'alpha','id':'ART-one','artifact_path':'same.txt','scope':'project','sha256':'a'*64,'turn_id':'WT-other'}
 records={'artifact_records':{('alpha','ART-one'):record},'artifact_ambiguities':set()}
 assert session_reads._artifact_result_links(turn,records)==[]
 record['turn_id']='WT-selected';assert len(session_reads._artifact_result_links(turn,records))==1
 records['artifact_ambiguities'].add(('alpha','ART-one'));assert session_reads._artifact_result_links(turn,records)==[]


def test_human_route_is_presentation_and_does_not_change_prior_consumed_read_digest(tmp_path):
 projects(tmp_path);created=store(tmp_path,'alpha');value=tools.execute(tmp_path,'alpha','review','read_artifact',{'id':created['id']})
 old={k:v for k,v in value.items() if k not in {'human_read','link_instruction'}}
 assert reads.read_output_digest('read_artifact',value)==reads.output_digest(old)
 relocated={**value,'human_read':{**value['human_read'],'url':'/different/presentation/url'},'link_instruction':'Changed guidance'}
 assert reads.read_output_digest('read_artifact',relocated)==reads.read_output_digest('read_artifact',value)
 changed={**value,'revision':'f'*64,'content':'Changed semantic content'}
 assert reads.read_output_digest('read_artifact',changed)!=reads.read_output_digest('read_artifact',value)
