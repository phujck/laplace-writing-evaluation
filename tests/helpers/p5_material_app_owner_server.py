"""Actual existing Writing app, fresh linked public Material source; no provider."""
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
root=HOME/'workspace';root.mkdir();(root/'registry_projects.json').write_text('{"projects":[]}')
created=library.create({'name':'p5-public','title':'Public pinned Unicode material','kind':'general'},root);assert created[0]==200 or created[0]==201,created
(root/'profiles').mkdir(exist_ok=True);(root/'inputs').mkdir()
(root/'profiles/writing_sources.json').write_text('{"repositories":{"public":"inputs"}}')
source=root/'inputs/public-unicode.txt'
initial=('INITIAL PUBLIC SOURCE · é中🌱\n'+''.join('Public line %03d · é中🌱 · stable observed source.\n'%i for i in range(360)))
assert len(initial)>16000
source.write_text(initial,encoding='utf-8')
os.environ.update(LAPLACE_REPO_ROOT=str(root),LAPLACE_ROOT=str(root),LAPLACE_TEST_PROCESS='1')
assert checkout.repo_root()==root
cache=root/'.laplace-cache';cache.mkdir()
(cache/'writing-provider-catalogue.json').write_text(json.dumps({'schema_version':'laplace.provider-catalogue/1','observed_at':99999999999,'providers':[{'id':'codex','available':False,'models':[]},{'id':'claude','available':False,'models':[]}]}))
preview=library.material_references('p5-public',root,view='preview',target={'owner':'repository','repository':'public','path':'public-unicode.txt'},limit=16000)
attached=library.change_material_reference('p5-public',{'action':'attach','target':preview['target'],'consumed_revision':preview['current_revision'],'expected_revision':preview['revision'],'reason':'Public synthetic Root interaction fixture'},root)
binding=attached['reference']['id']
first=library.material_references('p5-public',root,view='source',id=binding,limit=16000)
assert first['read_handle'] and first['page_read'] and first['restart_read']
import hashlib
baseline={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'registry_sha256':hashlib.sha256((root/'registry_projects.json').read_bytes()).hexdigest(),'binding':attached['reference'],'first_read':first,'source_characters':len(initial),'source_bytes':source.stat().st_size}
(HOME/'initial-basis.json').write_text(json.dumps(baseline,ensure_ascii=False,indent=2)+'\n')
from laplace.web import scanner
requests=[]
Base=scanner.make_handler()
class Handler(Base):
 def do_GET(self):
  requests.append(self.path)
  return super().do_GET()
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
url='http://127.0.0.1:%d/project?workspace=writing&corpus=p5-public&view=material'%server.server_port
info={'pid':os.getpid(),'port':server.server_port,'url':url,'source':str(SOURCE),'root':str(root),'state':str(HOME/'state'),'source_file':str(source),'binding_id':binding,'initial_basis':str(HOME/'initial-basis.json'),'initial_source_characters':len(initial),'page_limit':16000,'mutation_text':'CURRENT PUBLIC SOURCE · externally changed once · é中🌱\nThis is the current source after explicit owner restart.\n'}
(HOME/'service.json').write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(info,ensure_ascii=False),flush=True)
try:sys.stdin.read()
finally:
 server.shutdown();server.server_close()
 origins={n:str(Path(m.__file__).resolve()) for n,m in sys.modules.items() if (n in ('laplace','atlas') or n.startswith(('laplace.','atlas.'))) and getattr(m,'__file__',None)}
 assert all(Path(p).is_relative_to(SOURCE/'src') for p in origins.values())
 (HOME/'guard.json').write_text(json.dumps({'origins':origins,'runtime_refusals':runtime_guard.DENIALS,'write_refusals':refusals,'requests':requests,'provider_calls':0},indent=2)+'\n')
