"""Real workflow HTTP owner on a public synthetic root, with before-import containment.

Started by workflow_app.playwright.mjs. The server binds loopback only and starts
no provider. Source belongs to this checkout; every mutable root belongs to the
explicit evidence home. Reuses the existing runtime_guard provider/live-state fence.
"""
import importlib.machinery
import json
import os
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2]
HOME = Path(os.environ['WORKFLOW_EVIDENCE_HOME']).resolve()
FIXTURE_PARENTS = (Path('/tmp/laplace-programme-20261024/app-workflow-consumer'), Path('/tmp/laplace-programme-20261025/failed-review-continuation-consumer'))
assert any(HOME.is_relative_to(parent) for parent in FIXTURE_PARENTS)
(HOME / 'tmp').mkdir(parents=True, exist_ok=True)
os.environ.update(TMPDIR=str(HOME / 'tmp'), TMP=str(HOME / 'tmp'), TEMP=str(HOME / 'tmp'))
assert not any(name == 'laplace' or name.startswith('laplace.') for name in sys.modules)
sys.path.insert(0, str(SOURCE / 'tests'))
import runtime_guard
runtime_guard.install()
runtime_guard.ARMED = True
refusals = []


class SelectedSource:
    def find_spec(self, fullname, path=None, target=None):
        if fullname in ('laplace', 'atlas') or fullname.startswith(('laplace.', 'atlas.')):
            spec = importlib.machinery.PathFinder.find_spec(fullname, path)
            if spec and spec.origin and spec.origin not in ('built-in', 'frozen'):
                assert Path(spec.origin).resolve().is_relative_to(SOURCE / 'src'), (fullname, spec.origin)
            return spec


sys.meta_path.insert(0, SelectedSource())


def fixture_writes(event, args):
    targets = []
    if event == 'open' and args and not isinstance(args[0], int):
        mode, flags = args[1], args[2]
        if (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT)):
            targets.append((args[0], None))
    elif event in ('os.remove', 'os.rmdir'):
        targets.append((args[0], args[1]))
    elif event == 'os.mkdir':
        targets.append((args[0], args[2]))
    elif event == 'os.rename':
        targets.extend(((args[0], args[2]), (args[1], args[3])))
    for target, dir_fd in targets:
        if not isinstance(target, (str, bytes, os.PathLike)):
            continue
        resolved = Path(os.fsdecode(target))
        if not resolved.is_absolute() and isinstance(dir_fd, int) and dir_fd >= 0:
            resolved = Path(os.readlink('/proc/self/fd/%d' % dir_fd)) / resolved
        resolved = resolved.resolve()
        if not resolved.is_relative_to(HOME) and resolved != Path('/dev/null'):
            refusals.append({'event': event, 'path': str(resolved)})
            raise PermissionError('workflow fixture write outside evidence home: ' + str(resolved))


sys.addaudithook(fixture_writes)
from laplace.core import checkout
assert checkout.source_tree().resolve() == SOURCE
assert checkout.repo_root().resolve() == SOURCE
assert checkout.state_root().resolve() == HOME / 'state'
root = HOME / 'workspace'
root.mkdir(parents=True, exist_ok=True)
(root / 'node.py').write_text('VALUE = 1\n')
(root / 'registry_projects.json').write_text('{"projects": []}')
(root / 'profiles').mkdir(exist_ok=True)
cache = root / '.laplace-cache'
cache.mkdir(exist_ok=True)
(cache / 'writing-provider-catalogue.json').write_text(json.dumps({
    'schema_version': 'laplace.provider-catalogue/1', 'observed_at': 99999999999,
    'providers': [{'id': 'codex', 'available': True, 'models': []}, {'id': 'claude', 'available': True, 'models': []}]}))
os.environ.update(LAPLACE_REPO_ROOT=str(root), LAPLACE_ROOT=str(root),
                  LAPLACE_NO_PREWARM='1', LAPLACE_TEST_PROCESS='1',
                  LAPLACE_SESSION_WORKSPACES=str(HOME / 'session-workspaces'))
assert checkout.repo_root().resolve() == root
# Deterministic recorded-child fixture; actual native preparation/HTTP reads, no provider process.
tex=root/'synthetics papers/book/manuscript/tex';tex.mkdir(parents=True)
(tex/'main.tex').write_text('\\documentclass{article}\n\\begin{document}Public workflow fixture.\\end{document}\n')
(root/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'book','kind':'conceptric','tex_root':str(tex.relative_to(root))}]}))
from laplace.pipeline import workflow_definitions as definitions
from laplace.writing import provider,provider_catalogue,records,child_hosts,workflow_dispatch
from laplace.work import owner_discovery
from laplace.native import tools
from laplace.projects import artifacts
catalogue={'schema_version':'laplace.provider-catalogue/1','observed_at':99999999999,'providers':[{'id':'codex','available':True,'auth_state':'UNVERIFIED','models':[{'id':'fixture-model','name':'Fixture model (no provider)','efforts':['low'],'default_effort':'low','supports_effort':True}]}]}
(cache/'writing-provider-catalogue.json').write_text(json.dumps(catalogue))
body={'schema_version':definitions.SCHEMA,'title':'Prepare and inspect a public result','description':'A saved builder and independent review; authored synthesis stays separate.','settings':{'provider':'codex','model':'fixture-model','effort':'low'},'layout':{},'steps':[
 {'id':'author','title':'Author','parent_id':None,'assignment':{'role':'builder','instructions':'Inspect and write the complete public result.','settings':{}}},
 {'id':'critic','title':'Critic','parent_id':None,'assignment':{'role':'adversary','instructions':'Independently review the exact public result.','settings':{}}},
 {'id':'synthesis','title':'Synthesis','parent_id':None,'assignment':{'role':'synthesis','instructions':'Retain this authored synthesis assignment.','settings':{}}}],
 'edges':[{'id':'review','from':'author','to':'critic','kind':'control'}]}
saved=definitions.save(root,owner_discovery.project_scope('book','sdk'),{'request_id':'fixture-save','expected_revision':None,'definition':body})
records.bank(root,{'record':'writing-session','id':'WS-parent','project':'book','role':'author','provider':'codex','model':'fixture-model','effort':'low'})
records.bank(root,{'record':'writing-turn','id':'WT-prepare','session_id':'WS-parent','project':'book','mode':'work','text':'Public synthetic native preparation.','provider_settings':{'provider':'codex','model':'fixture-model','effort':'low'}})
child_hosts._begin_child_execution(root,'WS-parent',{'state':'RUNNING','turn_id':'WT-prepare','project':'book','session_id':'WS-parent','host':child_hosts._process_identity()})
original=provider.capabilities
provider.capabilities=lambda *a,**k:catalogue
try:
 prepared=tools.execute(root,'book','work','workflow_definition_change',{'action':'prepare','profile':definitions.APP_PROFILE,'request_id':'fixture-prepare','reference':saved['reference'],'step_ids':['author','critic'],'goal':'Inspect public outcome and independent review','fan_out_max':2},turn_id='WT-prepare')
finally:provider.capabilities=original
assert prepared['effect']=='prepared' and prepared['provider_started'] is False
assert len(records.fold_records(root)['sessions'])==1
(HOME/'preparation.json').write_text(json.dumps(prepared,indent=2))
records.bank(root,{'record':'writing-reply','id':'REPLY-prepared','project':'book','turn_id':'WT-prepare','session_id':'WS-parent','status':'completed','text':'Prepared only; this fixture invoked no provider.'})
child_hosts._finish_child_execution(root,'WS-parent','WT-prepare','completed')
run=definitions.read(root,owner_discovery.project_scope('book','sdk'),prepared['read']['request'])
packet=run['step_packets']['author']
records.bank(root,{'record':'writing-session','id':'WS-recordedchild','project':'book','role':'author','dispatch_id':prepared['work']['id'],'packet':packet,'provider':'codex','model':'fixture-model','effort':'low'})
records.bank(root,{'record':'writing-turn','id':'WT-recordedchild','session_id':'WS-recordedchild','project':'book','mode':'work','dispatch_id':prepared['work']['id'],'parent_turn_id':'WT-prepare','text':'Complete public recorded request.','provider_settings':{'provider':'codex','model':'fixture-model','effort':'low'}})
public_text='FULL_PUBLIC_BEGIN\n'+('Retained public paragraph. '+('完整结果。'*8)+'\n')*600+'FULL_PUBLIC_END'
records.bank(root,{'record':'writing-reply','id':'REPLY-recordedchild','project':'book','turn_id':'WT-recordedchild','session_id':'WS-recordedchild','status':'completed','text':public_text})
records.bank(root,{'record':'writing-tool-action','id':'ACTION-recorded','project':'book','turn_id':'WT-recordedchild','operation':'store_artifact','payload':{'path':'public-result.json'},'outcome':{'status':'RECORDED','public_note':'FULL_PUBLIC_ACTION_END'}})
# A retained but incomplete typed artifact is readable evidence, never accepted completion.
_,relative=workflow_dispatch._keys('book','fixture-prepare')
plan=json.loads(artifacts.resolve_path(root,'book',relative).read_text())
returned=artifacts.resolve_path(root,'book',plan['packets'][0]['return_path']);returned.write_text('{"schema_version":"laplace.packet-return/2","status":"BLOCKED","summary":"Public fixture incomplete typed return"}')
if os.environ.get('WORKFLOW_FAILED_REVIEW_FIXTURE') == '1':
 from laplace.work import project_work as W
 from laplace.writing import dispatch_execution as E
 task=W._tasks('book',root)[prepared['work']['id']]
 _,pin,art=workflow_dispatch._checked(root,'book',task)
 W.transition('book',{'id':task['id'],'status':'in-progress'},root,dispatch_receipt={
  'dispatch_admitted':True,'dispatch_parent_turn_id':'WT-prepare','dispatch_launch_state':'STARTED','dispatch_plan_sha256':art['revision']})
 report=artifacts.store(root,'book',{'path':'development/report.md','before':None,'content':'Retained worker report.\n'*600,'reason':'Public continuation fixture.'},'WT-recordedchild')
 source={'path':art['path'],'sha256':art['revision']};output={'path':report['path'],'sha256':report['revision']}
 worker={'schema_version':'laplace.packet-return/2','packet':plan['packets'][0]['packet'],'role':'build','status':'COMPLETE','goal':plan['goal'],'inputs':[source],
  'source':{'kind':'artifacts','root':str(root),'artifacts':[source,output]},'output':output,'files_written':[report['path']],
  'summary':'Complete public worker output retained.','most_important':['Exact report remains available.'],'residuals':[],'remaining_work':[],'continuation':None,
  'scripted_check':{'kind':'command','state':'PASSED','command':'fixture exact bytes','exit_code':0,'output_tail':'Retained public report.'}}
 artifacts.store(root,'book',{'path':plan['packets'][0]['return_path'],'before':returned.read_text(),'content':json.dumps(worker),'reason':'Public valid typed worker fixture.'},'WT-recordedchild')
 child_hosts._begin_child_execution(root,'WS-recordedchild',{'state':'FINISHED','turn_id':'WT-recordedchild','session_id':'WS-recordedchild','project':'book'})
 judge='WS-recordedjudge';old='WT-recordedjudge-first'
 records.bank(root,{'record':'writing-session','id':judge,'project':'book','role':'review','dispatch_id':task['id'],'packet':plan['packets'][1]['packet'],'provider':'codex','model':'fixture-model','effort':'low'})
 records.bank(root,{'record':'writing-turn','id':old,'session_id':judge,'project':'book','mode':'review','dispatch_id':task['id'],'parent_turn_id':'WT-prepare','text':'First exact public review request.'})
 records.bank(root,{'record':'writing-reply','id':'REPLY-judge-first','project':'book','session_id':judge,'turn_id':old,'status':'failed','text':'Earlier failed review.\n'*50+'FAILED_REVIEW_FIRST_END'})
 child_hosts._begin_child_execution(root,judge,{'state':'FINISHED','turn_id':old,'session_id':judge,'project':'book'})
 parent='WT-explicit-failed-review-fixture'
 records.bank(root,{'record':'writing-turn','id':parent,'session_id':'WS-parent','project':'book','mode':'work','work_id':task['id'],'text':'Continue only the exact public failed judge.'})
 child_hosts._begin_child_execution(root,'WS-parent',{'state':'RUNNING','turn_id':parent,'session_id':'WS-parent','project':'book','host':child_hosts._process_identity()})
 def fixture_start(selected,payload,*,dispatch):
  turn=E.continuation_turn_id(root,'book',judge,payload['request_id'],dispatch)
  records.bank(root,{'record':'writing-turn','id':turn,'session_id':judge,'project':'book','mode':'review','request_id':payload['request_id'],'text':payload['text'],**dispatch})
  child_hosts._begin_child_execution(root,judge,{'state':'RUNNING','turn_id':turn,'session_id':judge,'project':'book','host':child_hosts._process_identity()})
  return {'turn_id':turn,'session_id':judge}
 original_start=E.turn_admission.start_turn;original_capabilities=provider.capabilities
 E.turn_admission.start_turn=fixture_start;provider.capabilities=lambda *a,**k:catalogue
 try:
  offer=E.continuation_offer(root,'book',task['id'],plan['packets'][1]['packet']);assert offer['available'],offer
  receipt=tools.execute(root,'book','work','dispatch_continue',{**offer['payload'],'request_id':'fixture-earlier-continuation'},turn_id=parent)
 finally:E.turn_admission.start_turn=original_start;provider.capabilities=original_capabilities
 current=receipt['current_attempt']['turn_id']
 records.bank(root,{'record':'writing-reply','id':'REPLY-judge-current','project':'book','session_id':judge,'turn_id':current,'status':'failed','text':'Current failed review public paragraph.\n'*400+'FAILED_REVIEW_CURRENT_END'})
 child_hosts._finish_child_execution(root,judge,current,'failed')
 records.bank(root,{'record':'writing-reply','id':'REPLY-parent-fixture','project':'book','session_id':'WS-parent','turn_id':parent,'status':'completed','text':'Public deterministic continuation receipt retained; no provider was invoked.'})
 child_hosts._finish_child_execution(root,'WS-parent',parent,'completed')
 (HOME/'continuation-fixture-receipt.json').write_text(json.dumps(receipt,indent=2))

from laplace.web import scanner


def origins():
    loaded = {name: str(Path(module.__file__).resolve()) for name, module in sys.modules.items()
              if (name in ('laplace', 'atlas') or name.startswith(('laplace.', 'atlas.'))) and getattr(module, '__file__', None)}
    assert all(Path(path).is_relative_to(SOURCE / 'src') for path in loaded.values()), loaded
    return loaded


server = ThreadingHTTPServer(('127.0.0.1', 0), scanner.make_handler())
threading.Thread(target=server.serve_forever, daemon=True).start()
print(json.dumps({'port': server.server_address[1], 'root': str(root), 'source': str(SOURCE),'definition_id':saved['definition_id'],'version':saved['version'],'work_id':prepared['work']['id']}), flush=True)
try:
    sys.stdin.read()
finally:
    server.shutdown()
    server.server_close()
    (HOME / 'guard.json').write_text(json.dumps({'source': str(SOURCE), 'workspace': str(root),
        'state': str(checkout.state_root()), 'origins': origins(), 'refusals': refusals,
        'runtime_refusals': runtime_guard.DENIALS,'provider_starts':0,'fixture':'Actual native preparation plus synthetic banked child/public reply; no actual execution/provider inference'}, indent=2))
