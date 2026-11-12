from pathlib import Path
import json,os,sys,subprocess,socket,time,urllib.request,urllib.parse,hashlib,signal
v=json.loads(Path('/tmp/laplace-final-packaging-smoke-location.json').read_text());base=Path(v['base']);root=Path(v['relocated']);installed=Path(v['installed']);python='/tmp/laplace-evaluation-corrected-1sh0z3go/venv/bin/python'
sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
wrapper=base/'serve.py';wrapper.write_text('import sys\nfrom pathlib import Path\nsys.path.insert(0,'+repr(str(installed))+')\nimport laplace,atlas\nassert Path(laplace.__file__).is_relative_to('+repr(str(installed))+')\nassert Path(atlas.__file__).is_relative_to('+repr(str(installed))+')\nfrom laplace.web.writing_server import main\nraise SystemExit(main())\n')
env={k:x for k,x in os.environ.items() if not k.startswith('LAPLACE_') and k!='PYTHONPATH'};env['PYTHONNOUSERSITE']='1'
log=(base/'server.log').open('w');proc=subprocess.Popen([python,str(wrapper),'--root',str(root),'--state',str(base/'state'),'--session-workspaces',str(base/'provider-cwd'),'--port',str(port)],cwd=base,env=env,stdout=log,stderr=subprocess.STDOUT)
report={'scope':'Relocated selected data with newly built local packages installed into a separate target, using previously clean Python3.12 dependency environment. No Main data, model or new scientific execution. Not a repeated clean dependency install.','selected_base_commit':'97a4e0c885a09b586bc9d617bb0e54c86e7c04db','source_commit':'fd71f1010668ce6b1f640251c9e2b510790bf97e','checks':[],'errors':[]}
def get(path):
 with urllib.request.urlopen('http://127.0.0.1:'+str(port)+path,timeout=90) as f:return f.status,f.read()
def q(route,**kw):return route+'?'+urllib.parse.urlencode(kw)
try:
 for _ in range(120):
  if proc.poll() is not None:raise RuntimeError('server exited: '+(base/'server.log').read_text()[-2000:])
  try:status,body=get('/authoring/health');break
  except OSError:time.sleep(.25)
 else:raise RuntimeError('startup timeout')
 health=json.loads(body);assert health['active_runs']==0,health.get('active_work');report['checks'].append({'check':'no unresolved run indexes','http':status,'active_runs':health['active_runs'],'active_work':health['active_work']})
 m=json.loads((root/'release/selection-manifest.json').read_text())
 for paper in m['papers']:
  project=paper['project'];status,b=get(q('/walk/doc',corpus=project));d=json.loads(b);assert d.get('ok') and d['citations'] and d['refs'] and not d.get('citations_note') and not d.get('refs_note'),(project,d.get('citations_note'),d.get('refs_note'))
  report['checks'].append({'check':'built reference companions used by actual reader owner','project':project,'http':status,'citations':len(d['citations']),'refs':len(d['refs'])})
  status,b=get(q('/projection/pdf',file=paper['pdf'],corpus=project));h=hashlib.sha256(b).hexdigest();expected=paper['final_build']['outputs'][paper['pdf']];assert h==expected,(project,h,expected);report['checks'].append({'check':'exact final PDF served','project':project,'http':status,'bytes':len(b),'sha256':h})
 for project,ident in [('memory-in-pieces','run-d2f6d3cff17f0fbe'),('adaptive-normal-form-aek9','run-68cbc97a85ad2f23')]:
  status,b=get(q('/research/run/status',project=project,id=ident));d=json.loads(b);run=d.get('run',d);assert run['state']=='COMPLETE',(project,d);report['checks'].append({'check':'retained run located through HTTP owner','project':project,'http':status,'id':ident,'state':run['state'],'location_resolution':run.get('location_resolution')})
 rel='evidence/DYNAMIC_MEMORY_REWRITE_2026-11-11/source-to-message-final.tikz';raw=(root/'writing_projects/memory-in-pieces'/rel).read_bytes();pin=hashlib.sha256(raw).hexdigest();status,b=get(q('/research/artifact',project='memory-in-pieces',scope='project',path=rel,expected_sha256=pin,limit=32768,format='json'));d=json.loads(b);assert d['sha256']==pin and d['content']==raw.decode();strings=[]
 def walk(x):
  if isinstance(x,str):strings.append(x)
  elif isinstance(x,dict):
   for y in x.values():walk(y)
  elif isinstance(x,list):
   for y in x:walk(y)
 walk(d);assert any('\\begin{tikzpicture}' in s for s in strings),d;report['checks'].append({'check':'original missing diagram source opened by actual pinned artifact owner','http':status,'sha256':pin,'source_body_present':True})
 report['status']='PASS'
except Exception as e:report['status']='FAIL';report['errors'].append(type(e).__name__+': '+str(e));raise
finally:
 proc.send_signal(signal.SIGINT)
 try:proc.wait(timeout=15)
 except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
 log.close();report['server_stopped']=proc.poll() is not None;report['server_exit']=proc.returncode
 (base/'packaging-owner-smoke-v3.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
