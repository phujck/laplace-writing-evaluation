"""Exact public fault actor: terminate after first publication rename, no provider execution."""
from pathlib import Path
import sys,os,json,importlib.machinery
S=Path(__file__).resolve().parents[2];root=Path(sys.argv[1]).resolve();wire=root/'crash-wire.json'
assert root.is_relative_to(Path('/tmp')) and wire.is_file()
os.environ.update(TMPDIR=str(root),TMP=str(root),TEMP=str(root),LAPLACE_REEMBED_ROOT=str(root),PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
sys.dont_write_bytecode=True;sys.path[:0]=[str(S/'src'),str(S/'scripts')]
denials=[]
class Owned:
 def find_spec(self,name,path=None,target=None):
  if name in ('laplace','atlas') or name.startswith(('laplace.','atlas.')):
   spec=importlib.machinery.PathFinder.find_spec(name,path)
   if spec and spec.origin:assert Path(spec.origin).resolve().is_relative_to(S/'src')
   return spec
sys.meta_path.insert(0,Owned())
def guard(event,args):
 if event in {'subprocess.Popen','os.system','os.spawn','os.posix_spawn','os.exec','os.fork','socket.connect','socket.getaddrinfo','socket.sendto','urllib.Request'}:
  denials.append(event);raise PermissionError('Child actor has no process/network/provider authority')
 if event=='open' and args and not isinstance(args[0],int):
  p=Path(os.fsdecode(args[0])).resolve();mode=args[1];flags=args[2]
  writing=isinstance(mode,str) and any(c in mode for c in 'wax+') or isinstance(flags,int) and bool(flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC))
  if writing and not (p.is_relative_to(root) or p==Path('/dev/null')):denials.append('write');raise PermissionError('Only this public actor root')
  if not writing and p.is_relative_to(Path('/home/phujck')):
   admitted=(p.is_relative_to(S) and (p==S/'runtime_profiles.toml' or p.relative_to(S).parts[0] in {'src','scripts','tests','docs','profiles','deploy'})) or p.is_relative_to(Path('/home/phujck/.local/share/laplace/runtime')) or p.is_relative_to(Path('/home/phujck/.cache/laplace/fastembed/fast-bge-small-en-v1.5'))
   if not admitted:denials.append('read');raise PermissionError('No private/Main/external root')
sys.addaudithook(guard)
if os.environ.get('LAPLACE_ASSERT_STREAM_TIMING')=='1':
 original_read_bytes=Path.read_bytes
 def bounded_read_bytes(self):
  if '.reembed_timing.jsonl' in self.name:raise AssertionError('Child whole timing history read_bytes forbidden')
  return original_read_bytes(self)
 Path.read_bytes=bounded_read_bytes
from laplace.representation import source_publication as P
import reembed
from laplace.representation import embed_router as E
factory=E.FastEmbedBackend
def observed_backend():
 try:return factory()
 except Exception as exc:
  (root/'actor-backend-error.json').write_text(json.dumps({'error':repr(exc),'denials':denials}))
  raise
E.FastEmbedBackend=observed_backend
replace=P.os.replace
once=[]
def crash(source,target):
 result=replace(source,target)
 if Path(target)==root/'.self_graded.json' and str(source).endswith('.stage'):
  (root/'crash-actor-proof.json').write_text(json.dumps({'pid':os.getpid(),'first_rename':True,'denials':denials,'provider_network':0}))
  os._exit(88)
 return result
P.os.replace=crash
raise SystemExit(reembed.main(['--source-publication',str(wire)]))
