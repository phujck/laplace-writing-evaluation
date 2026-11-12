"""Full app with real public action/context/admission owners; execution-only substitute."""
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
HOME = Path(os.environ['HUMAN_ACTION_EVIDENCE_HOME']).resolve()
assert HOME.is_relative_to(Path('/tmp/laplace-programme-20261025/human-action-context-consumer'))
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
from laplace.projects import library
from laplace.pipeline import registry,workflow_definitions as D
from laplace.work import owner_discovery as O,project_work as W
from laplace.writing import records,child_hosts,turn_execution,workflow_dispatch as A
from test_app_workflow_dispatch import prepared
from test_failed_review_continuation import partial
patch=pytest.MonkeyPatch()
def register(path,name):
 assert library.create({'name':name,'title':'Public action context fixture','kind':'general'},path)[0]==201
 patch.setattr(registry,'_repo_root',lambda:path)
case=partial.__wrapped__(prepared.__wrapped__(root,patch,register));ident=case[1]
child_hosts._finish_child_execution(root,'WS-parent','prepare-turn','completed')
records.bank(root,{'record':'writing-reply','id':'WR-original-parent','session_id':'WS-parent','turn_id':'prepare-turn','project':'book','status':'completed','text':'Public synthetic preparation retained. No provider was invoked.'})
records.bank(root,{'record':'writing-session-settings','id':'WSS-parent','session_id':'WS-parent','project':'book','provider':'codex','model':'fixture-model','effort':'low','settings_revision':1})
voice=root/'profiles/voice/gerard-technical-v1.md';voice.parent.mkdir(parents=True);voice.write_text('# Public fixture voice v1\n\nUse clear public synthetic prose. No author profile is copied.\n')
cache=root/'.laplace-cache';cache.mkdir(exist_ok=True)
from laplace.writing import provider
catalogue=provider.capabilities(root);(cache/'writing-provider-catalogue.json').write_text(json.dumps(catalogue))
task=W._tasks('book',root)[ident]
action=D.read(root,O.project_scope('book','sdk'),{'reference':task['prepared_workflow']['reference'],'facet':'app-continue-compose','work_id':ident,'step_id':'Review','request_id':'child-human-fixture'})['action']
(HOME/'initial-action.json').write_text(json.dumps(action,ensure_ascii=False,indent=2)+'\n')
starts=[]
def execute_fixture(launch):
 proof={'turn_id':launch.turn_id,'session_id':launch.session_id,'prompt':launch.prompt,'workspace_context':launch.workspace_context,'provider_started':False}
 starts.append(proof)
 with (HOME/'admissions.jsonl').open('a') as stream:stream.write(json.dumps(proof,ensure_ascii=False)+'\n')
 turn_execution._bank_reply(launch,{'status':'completed','text':'Public fixture admitted the selected action. The execution boundary was substituted; no provider or dispatch continuation ran.','provider_stage':'pre-inference'})
 turn_execution._finish(launch,{'status':'completed'})
patch.setattr(turn_execution,'start',execute_fixture)
from laplace.web import scanner
requests=[];Base=scanner.make_handler()
class Handler(Base):
 def do_GET(self):requests.append({'method':'GET','path':self.path});return super().do_GET()
 def do_POST(self):requests.append({'method':'POST','path':self.path});return super().do_POST()
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
info={'port':server.server_port,'pid':os.getpid(),'source':str(SOURCE),'root':str(root),'project':'book','work_id':ident,'definition_id':action['action_context']['reference']['identity']['definition_id'],'version':action['action_context']['reference']['version']['definition_revision'],'url':'http://127.0.0.1:%d'%server.server_port+action['project_url']+'&app_return='+__import__('urllib.parse',fromlist=['quote']).quote('/project?workspace=writing&app=workflows',safe=''),'action':action,'worker_report':str(root/'writing_projects/book/development/report.md')}
(HOME/'service.json').write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n');print(json.dumps(info,ensure_ascii=False),flush=True)
try:sys.stdin.read()
finally:
 server.shutdown();server.server_close();patch.undo()
 origins={name:str(Path(module.__file__).resolve()) for name,module in sys.modules.items() if (name in ('laplace','atlas') or name.startswith(('laplace.','atlas.'))) and getattr(module,'__file__',None)}
 assert all(Path(path).is_relative_to(SOURCE/'src') for path in origins.values())
 (HOME/'guard.json').write_text(json.dumps({'source':str(SOURCE),'origins':origins,'runtime_refusals':runtime_guard.DENIALS,'write_refusals':refusals,'requests':requests,'execution_substitute_calls':len(starts),'provider_calls':0},indent=2)+'\n')
