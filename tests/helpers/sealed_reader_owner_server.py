"""Full app with real sealed-reader input/admission/read owners; fake process only."""
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
HOME = Path(os.environ['SEALED_READER_EVIDENCE_HOME']).resolve()
assert HOME.is_relative_to(Path('/tmp/laplace-programme-20261025/sealed-text-reader-consumer'))
HOME.mkdir(parents=True,exist_ok=False)
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
assert checkout.source_tree().resolve()==SOURCE and checkout.state_root().resolve()==HOME/'state'
root=HOME/'workspace';root.mkdir()
os.environ.update(LAPLACE_REPO_ROOT=str(root),LAPLACE_ROOT=str(root),LAPLACE_SESSION_WORKSPACES=str(HOME/'sessions'),LAPLACE_NO_PREWARM='1',LAPLACE_TEST_PROCESS='1')
assert checkout.repo_root()==root
import pytest
from test_sealed_text_reader import case, qualify, Input
from laplace.writing import sealed_reader as S, records, turn_execution as E, provider, turn_jobs, turn_admission as T
from laplace.projects import library
patch=pytest.MonkeyPatch();fixture=case.__wrapped__(root,patch);_,payload,primary,reference=next(fixture)
# Deliberately public long Unicode input exercises the existing owner pager.
primary+='PUBLIC_UNICODE é中🌱\n'*1200
(root/'inputs/primary.txt').write_text(primary)
payload['primary']['expected_sha256']=S.identity.bytes_digest((root/'inputs/primary.txt').read_bytes())
# The real Material owner issues and consumes these exact public references.
for selected in [payload['primary'],*payload['references']]:
 observed=library.material_references('book',root,view='preview',target=selected['target'])
 library.change_material_reference('book',{'action':'attach','target':selected['target'],'consumed_revision':observed['current_revision'],'expected_revision':observed['revision']},root)
# This certificate resolves retained PUBLIC SYNTHETIC observation bodies. It does
# not qualify a real CLI. Its bytes and all reads remain with the actual owner.
qualified=qualify(root);assert qualified['state']=='QUALIFIED'
artifact=root/'synthetics papers/book/development/exact-public.md';artifact.parent.mkdir(parents=True,exist_ok=True);artifact.write_text('PUBLIC EXACT ARTIFACT é中🌱\nSelected through its existing artifact owner.\n')
registry_before=S.identity.bytes_digest((root/'registry_projects.json').read_bytes())
starts=[];workers=[]
def execute_fixture(launch):
 proof={'turn_id':launch.turn_id,'session_id':launch.session_id,'prompt':launch.prompt,'reader_profile':launch.reader_profile,'provider_processes':0}
 assert all(value not in launch.prompt for value in ('EXCLUDED_PROJECT_GUIDANCE','EXCLUDED_STYLE_CONTEXT','EXCLUDED_HISTORY','EXCLUDED_UNSELECTED_FILE'))
 starts.append(proof)
 def work():
  try:
   if launch.prompt.startswith('READER TASK\nHold this public synthetic attempt'):
    import time
    deadline=time.monotonic()+30
    while not launch.job.get('interrupt_requested') and time.monotonic()<deadline:time.sleep(.02)
    answer={'status':'interrupted','text':'Public synthetic partial report retained after the explicit Stop.'}
   else:
    report='PUBLIC_SELECTED_TEXT_REPORT é中🌱\nPublic synthetic fake-process report; no provider was invoked.\n'+'Public report text. Selected packet only.\n'*300+'PUBLIC_REPORT_END é中🌱'
    messages=[{'type':'system','subtype':'init','session_id':'public-reader-native','model':'fixture-reader','tools':[],'mcp_servers':[],'slash_commands':[],'agents':[],'skills':[],'plugins':[],'output_style':'default'}, {'type':'assistant','message':{'model':'fixture-reader','content':[{'type':'text','text':report}]}},{'type':'result','subtype':'success','is_error':False,'result':report,'usage':{'input_tokens':1,'output_tokens':1}}]
    processes=[]
    class Process:
     pid=999999999
     def __init__(self,argv,**kwargs):
      assert argv[0]==str(root/'fixture-claude');S.validate_arguments(argv[1:],'fixture-reader','low')
      self.argv=argv;self.stdin=Input();self.stdout=iter(json.dumps(row,ensure_ascii=False)+'\n' for row in messages);processes.append(self)
     def wait(self,timeout=None):return 0
     def poll(self):return 0
    live=provider.WritingTurn(root,'claude','fixture-reader','low',None,lambda event:None,'review',project='book',session_id=launch.session_id)
    live.reader_profile=launch.reader_profile;live.operating_brief=launch.operating_brief
    with patch.context() as process_patch:
     process_patch.setattr(provider.subprocess,'Popen',Process);answer=live.run(launch.prompt)
    assert processes[0].stdin.getvalue()==launch.prompt
    answer['delivery_receipt']=live.delivery;proof.update(argv=processes[0].argv,delivery=live.delivery,fake_process_boundaries=len(processes))
   E._bank_reply(launch,answer);E._finish(launch,answer);proof['status']=answer['status']
  except Exception as error:
   proof['error']=str(error);E._bank_reply(launch,{'status':'failed','text':'Public synthetic boundary failed.','error':str(error)});E._finish(launch,{'status':'failed'})
  finally:
   with (HOME/'admissions.jsonl').open('a') as stream:stream.write(json.dumps(proof,ensure_ascii=False)+'\n')
 thread=threading.Thread(target=work,daemon=True);workers.append(thread);thread.start()
patch.setattr(E,'start',execute_fixture)
seed=None
if os.environ.get('SEALED_READER_SEED_READER')=='1':
 selected=S.prepare(root,payload);seed=T.start_turn(root,{**selected['start']['payload'],'request_id':'public-seeded-reader-for-remaining-segment'})
 for worker in workers:worker.join(timeout=3)
 assert all(not worker.is_alive() for worker in workers) and starts[0].get('status')=='completed'
from laplace.web import scanner
requests=[];Base=scanner.make_handler()
class Handler(Base):
 def do_GET(self):requests.append({'method':'GET','path':self.path});return super().do_GET()
 def do_POST(self):requests.append({'method':'POST','path':self.path});return super().do_POST()
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
info={'port':server.server_port,'pid':os.getpid(),'source':str(SOURCE),'source_commit':os.environ['SEALED_READER_SOURCE_COMMIT'],'root':str(root),'project':'book','registry_sha256':registry_before,'artifact_path':'development/exact-public.md','source_file':str(root/'inputs/primary.txt'),'url':'http://127.0.0.1:%d/project?workspace=writing&corpus=book&view=material'%server.server_port,'primary':payload['primary'],'reference':payload['references'][0],'support':S.support(root,'book'),'synthetic':True,'provider_processes':0}
if seed:info.update(seed=seed,url='http://127.0.0.1:%d/project?workspace=writing&corpus=book&session=%s'%(server.server_port,seed['session_id']))
(HOME/'service.json').write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n');print(json.dumps(info,ensure_ascii=False),flush=True)
try:sys.stdin.read()
finally:
 server.shutdown();server.server_close()
 from laplace.writing import turn_control
 for proof in starts:
  job=turn_jobs._JOBS.get(proof['turn_id'])
  if job and not job['done']:turn_control.interrupt_turn(root,{'project':'book','turn_id':proof['turn_id']})
 for thread in workers:thread.join(timeout=2)
 try:next(fixture)
 except StopIteration:pass
 patch.undo()
 origins={name:str(Path(module.__file__).resolve()) for name,module in sys.modules.items() if (name in ('laplace','atlas') or name.startswith(('laplace.','atlas.'))) and getattr(module,'__file__',None)}
 assert all(Path(path).is_relative_to(SOURCE/'src') for path in origins.values())
 (HOME/'guard.json').write_text(json.dumps({'source':str(SOURCE),'origins':origins,'runtime_refusals':runtime_guard.DENIALS,'write_refusals':refusals,'requests':requests,'execution_substitute_calls':len(starts),'provider_processes':0},indent=2)+'\n')
