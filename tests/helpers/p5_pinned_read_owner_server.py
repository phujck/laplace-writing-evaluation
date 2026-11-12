"""Tiny public Material read owner and exact existing reader component; no provider."""
import os,sys,json,threading,importlib.machinery
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlsplit,parse_qs
SOURCE=Path(__file__).resolve().parents[2];HOME=Path(os.environ['P5_PINNED_EVIDENCE_HOME']).resolve()
assert HOME.is_relative_to(Path('/tmp/laplace-programme-20261025/p5-pinned-read-consumer'));HOME.mkdir(parents=True,exist_ok=False)
os.environ.update(TMPDIR=str(HOME/'tmp'),LAPLACE_STATE=str(HOME/'state'),LAPLACE_SESSION_WORKSPACES=str(HOME/'sessions'),LAPLACE_NO_PREWARM='1');(HOME/'tmp').mkdir()
assert not any(n=='laplace' or n.startswith('laplace.') for n in sys.modules)
sys.path.insert(0,str(SOURCE/'tests'));import runtime_guard
runtime_guard.install();runtime_guard.ARMED=True
class SelectedSource:
 def find_spec(self,name,path=None,target=None):
  if name in ('laplace','atlas') or name.startswith(('laplace.','atlas.')):
   spec=importlib.machinery.PathFinder.find_spec(name,path)
   if spec and spec.origin:assert Path(spec.origin).resolve().is_relative_to(SOURCE/'src'),(name,spec.origin)
   return spec
sys.meta_path.insert(0,SelectedSource())
refusals=[]
def fence(event,args):
 targets=[]
 if event=='open' and args and not isinstance(args[0],int):
  mode,flags=args[1:3]
  if isinstance(mode,str) and any(c in mode for c in 'wax+') or isinstance(flags,int) and flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT):targets=[(args[0],None)]
 elif event in ('os.remove','os.rmdir'):targets=[(args[0],args[1])]
 elif event=='os.mkdir':targets=[(args[0],args[2])]
 elif event=='os.rename':targets=[(args[0],args[2]),(args[1],args[3])]
 for value,dir_fd in targets:
  if isinstance(value,(str,bytes,os.PathLike)):
   p=Path(os.fsdecode(value))
   if not p.is_absolute() and isinstance(dir_fd,int) and dir_fd>=0:p=Path(os.readlink('/proc/self/fd/%d'%dir_fd))/p
   p=p.resolve()
   if not p.is_relative_to(HOME) and p!=Path('/dev/null'):refusals.append([event,str(p)]);raise RuntimeError('P5 fixture write outside owned HOME')
sys.addaudithook(fence)
from laplace.core import checkout
assert checkout.source_tree()==SOURCE and checkout.state_root()==HOME/'state'
from laplace.projects import library
root=HOME/'workspace';root.mkdir();(root/'registry_projects.json').write_text('{"projects":[]}');library.create({'name':'book','title':'Public read fixture','kind':'general'},root);(root/'profiles').mkdir(exist_ok=True);(root/'inputs').mkdir();(root/'profiles/writing_sources.json').write_text('{"repositories":{"public":"inputs"}}');source=root/'inputs/plain.txt';source.write_text('é中🌱Old complete public source.\n')
os.environ.update(LAPLACE_REPO_ROOT=str(root),LAPLACE_ROOT=str(root));requests=[]
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  parsed=urlsplit(self.path);requests.append(self.path)
  if parsed.path=='/':
   raw=b'''<!doctype html><html><meta charset="utf-8"><title>Public Material read component</title><body><main id="reading"></main><script type="module">import {renderMaterialObservation} from '/shared/workspace-material-observation.mjs';const request=async url=>{const r=await fetch(url),v=await r.json();if(!r.ok)throw Error(v.error||'Read refused');return v;};const initial=await request('/initial');window.readInitial=initial;renderMaterialObservation(document.querySelector('#reading'),initial,{request,consumedRevision:initial.current_revision,workEvidence:true});document.body.dataset.ready='true';</script></body></html>''';code=200;kind='text/html'
  elif parsed.path=='/shared/workspace-material-observation.mjs':raw=(SOURCE/'src/laplace/web/static_shared/workspace-material-observation.mjs').read_bytes();code=200;kind='text/javascript'
  elif parsed.path=='/initial':
   value=library.material_references('book',root,view='preview',target={'owner':'repository','repository':'public','path':'plain.txt'},limit=3);raw=json.dumps(value,ensure_ascii=False).encode();code=200;kind='application/json'
  else:
   result=library.handle(parsed.path,parse_qs(parsed.query,keep_blank_values=True),'GET',b'',repo_root=root)
   if result:code,kind,raw=result
   else:code,kind,raw=404,'application/json',b'{"error":"Unknown public fixture route"}'
  self.send_response(code);self.send_header('Content-Type',kind+'; charset=utf-8');self.end_headers();self.wfile.write(raw)
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start();print(json.dumps({'port':server.server_port,'source_file':str(source),'root':str(root)}),flush=True)
try:sys.stdin.read()
finally:
 server.shutdown();server.server_close();origins={n:str(Path(m.__file__).resolve()) for n,m in sys.modules.items() if (n in ('laplace','atlas') or n.startswith(('laplace.','atlas.'))) and getattr(m,'__file__',None)};assert all(p.startswith(str(SOURCE/'src')+'/') for p in origins.values());(HOME/'guard.json').write_text(json.dumps({'origins':origins,'runtime_refusals':runtime_guard.DENIALS,'write_refusals':refusals,'requests':requests,'provider_calls':0},indent=2)+'\n')
