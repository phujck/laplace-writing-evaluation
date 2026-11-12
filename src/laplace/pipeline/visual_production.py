"""Typed, explicit visual rendering with Matplotlib's vector backends."""
from __future__ import annotations
from laplace.core.checkout import source_tree
import csv, hashlib, json, re, shutil, subprocess, math, threading
from pathlib import Path
from typing import Any

def _inside(base:Path, raw:str)->Path|None:
 p=(base/raw).resolve()
 try:p.relative_to(base.resolve());return p
 except ValueError:return None
def digest(value:Any)->str:return hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest()
def load(manuscript:Path)->dict:
 """Read canonical figure_specs; legacy visual_specs stays a compatibility input."""
 try:
  canonical=json.loads((manuscript/'manuscript_spec.json').read_text())
  if isinstance(canonical,dict) and isinstance(canonical.get('figure_specs'),list):return {'schema_version':'laplace.visual-specs/2','specs':list(canonical['figure_specs']),'authority':'manuscript_spec.json'}
 except Exception:pass
 try:return {'schema_version':'laplace.visual-specs/1','specs':list(json.loads((manuscript/'visual_specs.json').read_text()).get('specs') or []),'authority':'visual_specs.json (legacy)'}
 except Exception:return {'schema_version':'laplace.visual-specs/2','specs':[],'authority':'manuscript_spec.json'}
def save(manuscript:Path,data:dict,mutation_root:Path|None=None):
 """All new writes migrate to the canonical manuscript spec, once."""
 from laplace.pipeline import projection_spec
 def update(existing):
  rows=existing.get('figure_specs')
  if not isinstance(rows,list):rows=load(manuscript)['specs']
  specs={row['id']:row for row in rows if isinstance(row,dict) and row.get('id')}
  specs.update({row['id']:row for row in data.get('specs',[]) if isinstance(row,dict) and row.get('id')})
  existing['figure_specs']=list(specs.values());return existing
 path=manuscript/'manuscript_spec.json'
 revised,before,intended=projection_spec.update_file_with_receipt(path,update)
 if mutation_root is None:return revised
 from laplace.core.receipts import file_receipt
 return {'spec':revised,'file_receipt':file_receipt(mutation_root,path,before,intended)}

def _validation_issues(spec:dict)->list[dict]:
 """The one renderer-input validator, shared by create, state and render."""
 issues=[]
 if not isinstance(spec.get('id'),str) or not spec['id'].replace('-','').replace('_','').isalnum():issues.append({'field':'id','reason':'safe spec id required'})
 kind=spec.get('kind')
 if kind not in {'plot','diagram','tikz','artifact'}:issues.append({'field':'kind','reason':'kind must be plot, diagram, tikz, or artifact'})
 for field in ('title','question','caption'):
  if not isinstance(spec.get(field),str) or not spec[field].strip():issues.append({'field':field,'reason':field+' is required'})
 if 'result_ids' in spec and (not isinstance(spec['result_ids'],list) or any(not isinstance(value,str) or not value for value in spec['result_ids'])):issues.append({'field':'result_ids','reason':'result_ids must be an array of stable research result ids'})
 if kind=='plot':
  for field in ('source_data','x'):
   if not isinstance(spec.get(field),str) or not spec[field].strip():issues.append({'field':field,'reason':'plot '+field+' is required'})
  if not isinstance(spec.get('series'),list) or not spec['series'] or any(not isinstance(v,str) or not v for v in spec['series']):issues.append({'field':'series','reason':'plot needs at least one named series'})
 elif kind=='diagram':
  nodes=spec.get('nodes');edges=spec.get('edges')
  if not isinstance(nodes,list) or not nodes:issues.append({'field':'nodes','reason':'diagram needs at least one typed node'})
  elif any(not isinstance(node,dict) or not isinstance(node.get('id'),str) or not node['id'] for node in nodes):issues.append({'field':'nodes','reason':'diagram nodes require stable ids'})
  if not isinstance(edges,list):issues.append({'field':'edges','reason':'diagram needs a typed edges array'})
  elif any(not isinstance(edge,dict) or not all(isinstance(edge.get(key),str) and edge[key] for key in ('source','target','rel')) for edge in edges):issues.append({'field':'edges','reason':'diagram edges require source, target, and rel'})
 elif kind=='tikz':
  inline,source=spec.get('tikz'),spec.get('source')
  if bool(isinstance(inline,str) and inline.strip())==bool(isinstance(source,str) and source.strip()):issues.append({'field':'tikz','reason':'tikz visual requires exactly one of tikz or source'})
 elif kind=='artifact' and not all(isinstance(spec.get(k),str) and spec[k].strip() for k in ('run_id','artifact_id')):
  issues.append({'field':'run_id,artifact_id','reason':'artifact visual requires run_id and artifact_id from one completed supervised run'})
 return issues

def validate(spec:dict)->str|None:
 issues=_validation_issues(spec)
 return issues[0]['reason'] if issues else None

def render_readiness(spec:dict, observed:dict|None=None)->dict:
 """Read-only render preflight; legacy briefs remain visible but cannot lie ready."""
 issues=_validation_issues(spec)
 if issues:return {'status':'INCOMPLETE','can_render':False,'issues':issues,
                   'help':{'operation':'help','payload':{'operation':'visual_create'}},
                   'current_revision':digest(spec)}
 if observed and observed.get('input_error'):
  return {'status':'BLOCKED','can_render':False,
          'issues':[{'field':'renderer_input','reason':observed['input_error']}],
          'help':{'operation':'help','payload':{'operation':'visual_render'}},
          'current_revision':digest(spec)}
 return {'status':'READY','can_render':True,'issues':[],
         'help':{'operation':'help','payload':{'operation':'visual_render'}},
         'current_revision':digest(spec)}

def update_transport_fields()->dict:
 """Existing protected receipts and echoed read views, not authored metadata."""
 return {'protected':{
   'render':{'type':['object','null']},
   **{key:{'type':['string','null']} for key in ('section','section_scope','section_repo_file')}},
  'read':{
   **{key:{'type':'string'} for key in ('spec_revision','input_scope','render_freshness')},
   **{key:{'type':'object'} for key in ('currentness','placement_caption','render_readiness')}}}


def authoring_contract()->dict:
 """Inputs actually consumed by the three deployed visual producers."""
 text={'type':'string','minLength':1}
 def obj(required,properties):return {'type':'object','required':required,'properties':properties,'additionalProperties':False}
 common={key:text for key in ('id','title','question','caption')}
 common['id']={'type':'string','pattern':r'^(?=.*[A-Za-z0-9])[A-Za-z0-9_-]+$'}
 common['result_ids']={'type':'array','items':text}
 common['style']=obj([],{
  **{key:{'type':'number','exclusiveMinimum':0,'exclusiveMaximum':100} for key in
     ('font_size','width_inches','height_inches','line_width','marker_size')},
  'grid':{'type':'boolean'},'preview_dpi':{'type':'number','minimum':72,'maximum':600},
  'palette':{'type':'array','minItems':1,'items':{'type':'string','pattern':'^#[0-9A-Fa-f]{6}$'}}})
 required=['id','title','question','caption','kind']
 variants={
  'plot':obj(required+['source_data','x','series'],{**common,'kind':{'const':'plot'},
    'source_data':text,'x':text,'series':{'type':'array','minItems':1,'items':text},'x_label':text,'y_label':text}),
  'diagram':obj(required+['nodes','edges'],{**common,'kind':{'const':'diagram'},
    'nodes':{'type':'array','minItems':1,'items':obj(['id'],{'id':text,'label':text})},
    'edges':{'type':'array','items':obj(['source','target','rel'],{key:text for key in ('source','target','rel','label')})}}),
  'tikz':obj(required,{**common,'kind':{'const':'tikz'},'tikz':text,'source':text}),
  'artifact':obj(required+['run_id','artifact_id'],{**common,'kind':{'const':'artifact'},
    'run_id':text,'artifact_id':text})}
 variants['tikz']['oneOf']=[{'required':['tikz'],'not':{'required':['source']}},
                          {'required':['source'],'not':{'required':['tikz']}}]
 examples={
  'plot':{'spec':{'id':'sample-trend','kind':'plot','title':'Illustrative trend',
   'question':'How does the illustrative response vary with input?',
   'caption':'Illustrative fixture values, not an empirical finding.',
   'source_data':'data/observations.csv','x':'input','series':['response'],'x_label':'Input','y_label':'Response'}},
  'diagram':{'spec':{'id':'reasoning-map','kind':'diagram','title':'Declared reasoning structure',
   'question':'Which assumption does this claim require?',
   'caption':'A declared logical relationship; the arrow does not certify the claim.',
   'nodes':[{'id':'claim','label':'Claim'},{'id':'assumption','label':'Assumption'}],
   'edges':[{'source':'claim','target':'assumption','rel':'requires'}]}},
  'tikz':{'spec':{'id':'authored-schematic','kind':'tikz','title':'Authored schematic',
   'question':'How are the two stated objects related?',
   'caption':'An illustrative authored connection, not measured evidence.',
   'tikz':r'\begin{tikzpicture}\node (a) at (0,0) {A};\node (b) at (2,0) {B};\draw[->] (a) -- (b);\end{tikzpicture}'}},
  'artifact':{'spec':{'id':'supervised-figure','kind':'artifact','title':'Supervised figure output',
   'question':'What does the completed supervised calculation show?',
   'caption':'A current vector output named by the completed supervised run; scientific interpretation remains bound separately.',
   'run_id':'run-copy-from-run_status','artifact_id':'copy-from-run-result-artifacts'}}}
 patch_fields={key:value for variant in variants.values() for key,value in variant['properties'].items()}
 patch_fields['kind']={'enum':['plot','diagram','tikz','artifact']}
 for group in update_transport_fields().values():
  patch_fields.update({key:{**shape,'readOnly':True} for key,shape in group.items()})
 return {'variants':variants,'patch':obj(['id'],patch_fields),'examples':examples}

class SpecRevisionConflict(ValueError):pass

def upsert(manuscript:Path,spec:dict,expected_revision,mutation_root:Path)->dict:
 """Guard same-ID edits under the canonical spec lock, preserving other owners."""
 from laplace.pipeline import projection_spec
 from laplace.core.receipts import file_receipt
 from laplace.core.identity import revision_matches
 result={}
 def update(current):
  rows=current.get('figure_specs')
  if not isinstance(rows,list):rows=load(manuscript)['specs']
  prior=next((row for row in rows if row.get('id')==spec.get('id')),None)
  revision=digest(prior) if prior is not None else None
  if (prior is not None and not revision_matches(expected_revision,revision)) or (prior is None and expected_revision is not None):
   raise SpecRevisionConflict('Visual spec revision conflict: read visuals and reuse this spec.spec_revision as expected_revision; no visual changed.')
  # Rendering/placement are owner receipts, never caller-authored replacements.
  transport=update_transport_fields()
  owner_fields=set(transport['protected']);read_fields=set(transport['read'])
  for key in owner_fields:
   if key in spec and spec[key]!=(prior or {}).get(key):raise ValueError(key+' is owner-managed; use visual_render or visual_place')
  changes={key:value for key,value in spec.items() if key not in owner_fields|read_fields}
  # Guard against the actual old row first, then remove historical read-view
  # pollution without dropping authored metadata or another owner's receipts.
  merged={**{key:value for key,value in (prior or {}).items() if key not in read_fields},**changes}
  issue=validate(merged)
  if issue:raise ValueError(issue)
  current['figure_specs']=[row for row in rows if row.get('id')!=merged['id']]+[merged]
  result.update(spec=merged,before_revision=revision,spec_revision=digest(merged))
  return current
 path=manuscript/'manuscript_spec.json'
 _current,before,intended=projection_spec.update_file_with_receipt(path,update)
 return {**result,'file_receipt':file_receipt(mutation_root,path,before,intended)}
def _clean_spec(spec:dict)->dict:
 return {k:v for k,v in spec.items() if k not in {'render','section','section_scope','section_repo_file','render_readiness'} and not str(k).startswith('_')}
def _render_spec(spec:dict)->dict:
 """Only values the renderer actually reads when producing image bytes."""
 common={'id':spec.get('id'),'kind':spec.get('kind')}
 if spec.get('kind')=='plot':
  return {**common,**{key:spec.get(key) for key in
      ('x','series','x_label','y_label')}}
 if spec.get('kind')=='diagram':
  nodes=[{key:row.get(key) for key in ('id','label')} for row in spec.get('nodes') or [] if isinstance(row,dict)]
  edges=[{key:row.get(key) for key in ('source','target','rel','label')} for row in spec.get('edges') or [] if isinstance(row,dict)]
  return {**common,'nodes':nodes,'edges':edges}
 if spec.get('kind')=='artifact':
  return {**common,'run_id':spec.get('run_id'),'artifact_id':spec.get('artifact_id')}
 # TikZ bytes are hashed separately; path/inline storage identity is evidence,
 # not a pixel difference when the exact snippet is unchanged.
 return common
def _presentation_metadata(spec:dict)->dict:
 return {key:spec.get(key) for key in ('title','question','caption','source_data','source')}


def _supervised_artifact(manuscript:Path,base:Path,spec:dict)->dict:
 """Resolve current bytes explicitly named by one completed supervised result."""
 from laplace.research import research_records, research_runs
 run_id,artifact_id=spec.get('run_id'),spec.get('artifact_id')
 run=research_runs._run_status(manuscript,run_id) if isinstance(run_id,str) else None
 if not run or run.get('state')!='COMPLETE' or run.get('exit_code')!=0:
  raise ValueError('artifact visual requires a completed successful supervised run')
 result_rel=run.get('result_path');result=_inside(manuscript,result_rel) if isinstance(result_rel,str) else None
 if result is None or not result.is_file():raise ValueError('supervised run result is missing or escapes the manuscript')
 result_sha=hashlib.sha256(result.read_bytes()).hexdigest()
 if result_sha!=run.get('result_sha256'):raise ValueError('supervised run result changed after its completion receipt')
 try:result_data=json.loads(result.read_text())
 except (OSError,ValueError,TypeError):raise ValueError('supervised run result is not readable JSON')
 artifact=next((row for row in result_data.get('artifacts') or []
                if isinstance(row,dict) and row.get('id')==artifact_id),None)
 if artifact is None:raise ValueError('artifact_id is not declared by the supervised run result')
 sources={};digests={}
 for fmt in ('pdf','svg','png'):
  raw=artifact.get(fmt)
  if not isinstance(raw,str):continue
  path=Path(raw);path=path.resolve() if path.is_absolute() else (base/path).resolve()
  if not path.is_relative_to(base.resolve()) or not path.is_file() or path.suffix.lower()!='.'+fmt:
   raise ValueError('supervised '+fmt+' artifact is missing, mismatched, or escapes the project')
  sources[fmt]=path;digests[fmt]=hashlib.sha256(path.read_bytes()).hexdigest()
 if 'pdf' not in sources:raise ValueError('supervised artifact must declare an existing PDF for manuscript placement')
 return {'run_id':run_id,'producer_id':run.get('producer_id'),'result_path':result_rel,
  'result_sha256':result_sha,'artifact_id':artifact_id,'sources':sources,'source_digests':digests,
  'source_paths':{fmt:path.relative_to(base).as_posix() for fmt,path in sources.items()},
  'output_observation':'CURRENT_BYTES_NAMED_BY_SUPERVISED_RESULT',
  'historical_output_verification':'NOT_ESTABLISHED'}
_TIKZ_FORBIDDEN_WORDS=frozenset({'documentclass','usepackage','input','include',
 'includegraphics','pgfplotstableread','openin','read','write'})
_TIKZ_CONTROL_TOKEN=re.compile(r"\\([A-Za-z]+|[\s\S])")
def _tikz_forbidden_control(text:str)->bool:
 """Standard control-token starts, consuming a paired rowbreak as one symbol.

 This is deliberately conservative about comments/custom catcodes, not a TeX
 sandbox claim. Existing forbidden families still refuse at active starts;
 digits after write are arguments to that primitive, not part of its name.
 """
 for token in _TIKZ_CONTROL_TOKEN.finditer(text):
  word=token.group(1).lower()
  if word in _TIKZ_FORBIDDEN_WORDS:return True
  if word in {'begin','end'} and re.match(r'\s*\{document\}',text[token.end():],re.I):return True
 return False
def _tikz_snippet(base:Path,spec:dict)->tuple[str,str]:
 inline=spec.get('tikz'); source=spec.get('source')
 if bool(isinstance(inline,str) and inline.strip())==bool(isinstance(source,str) and source.strip()):
  raise ValueError('tikz visual requires exactly one of tikz or source')
 if isinstance(source,str) and source.strip():
  path=_inside(base,source)
  if path is None or not path.is_file() or path.suffix.lower() not in {'.tex','.tikz'}:raise ValueError('tikz source must be a project-confined .tex or .tikz file')
  text=path.read_text(encoding='utf8')
 else:text=str(inline)
 if len(text.encode('utf8'))>500_000:raise ValueError('tikz source is too large')
 if _tikz_forbidden_control(text):raise ValueError('tikz source may contain a tikzpicture only; document and file primitives are forbidden')
 if text.count('\\begin{tikzpicture}')!=1 or text.count('\\end{tikzpicture}')!=1:raise ValueError('tikz source must contain exactly one tikzpicture')
 return text,hashlib.sha256(text.encode('utf8')).hexdigest()
def provenance(manuscript:Path,spec:dict,project_root:Path|None=None,*,
               research_records_snapshot=None,research_currentness_snapshot=None,
               research_run_cache=None,research_digest_cache=None,
               research_visual_specs=None)->dict:
 """Separate drawing-byte freshness from the linked scientific basis.

 A result-record revision can change interpretation, notes, or provenance
 coverage without changing a plotted CSV, TikZ source, visual specification,
 style, or rendered output.  Those are different facts and stay different in
 this projection.
 """
 base=(project_root or manuscript).resolve(); style=house_style(manuscript,spec,project_root)
 inputs={'spec':_render_spec(spec)}; presentation=_presentation_metadata(spec);input_error=None;input_files=[]
 if spec.get('kind')=='plot':
  raw=spec.get('source_data'); path=_inside(base,raw) if isinstance(raw,str) else None
  if path is None or not path.is_file():input_error='plot source_data must be a project-confined existing file'
  else:inputs['data']=hashlib.sha256(path.read_bytes()).hexdigest()
  if isinstance(raw,str):input_files.append({'role':'Input data','path':raw,
      'scope':'manuscript' if base==manuscript.resolve() else 'project',
      'status':'PRESENT' if path is not None and path.is_file() else 'MISSING',
      'identity':'sha256:'+hashlib.sha256(str(path or (base/raw).resolve()).encode()).hexdigest()})
 elif spec.get('kind')=='tikz':
  try:_text,inputs['tikz']=_tikz_snippet(base,spec)
  except ValueError as exc:input_error=str(exc)
  raw=spec.get('source');path=_inside(base,raw) if isinstance(raw,str) else None
  if isinstance(raw,str):input_files.append({'role':'Diagram source','path':raw,
      'scope':'manuscript' if base==manuscript.resolve() else 'project',
      'status':'PRESENT' if path is not None and path.is_file() else 'MISSING',
      'identity':'sha256:'+hashlib.sha256(str(path or (base/raw).resolve()).encode()).hexdigest()})
 elif spec.get('kind')=='artifact':
  try:
   artifact=_supervised_artifact(manuscript,base,spec)
   inputs['supervised_run']={key:artifact.get(key) for key in
       ('run_id','producer_id','result_path','result_sha256','artifact_id','source_paths','source_digests',
        'output_observation','historical_output_verification')}
   input_files.append({'role':'Supervised run result','path':artifact['result_path'],
       'scope':'manuscript','status':'PRESENT','identity':'sha256:'+artifact['result_sha256']})
   input_files.extend({'role':'Supervised '+fmt.upper()+' output',
       'path':str(path.relative_to(base)),'scope':'project','status':'PRESENT',
       'identity':'sha256:'+artifact['source_digests'][fmt]}
       for fmt,path in artifact['sources'].items())
  except ValueError as exc:input_error=str(exc)
 result_ids=spec.get('result_ids') or []
 if result_ids:
  from laplace.research import research_records, research_runs
  research_binding=research_records.result_bindings(
      manuscript,result_ids,project_root or manuscript,
      records_snapshot=research_records_snapshot,
      currentness_snapshot=research_currentness_snapshot,
      run_cache=research_run_cache,digest_cache=research_digest_cache,
      visual_specs=research_visual_specs)
  evidence_gap='; '.join(research_binding['gaps']) or None
 else:
  research_binding={'status':'THEORY_ONLY','bindings':[],'gaps':[]}
  evidence_gap=None
 stored=spec.get('render') if isinstance(spec.get('render'),dict) else {}
 outputs=list(stored.get('outputs') or []); actual={}; output_error=None
 if outputs:
  for rel in outputs:
   path=_inside(manuscript,rel) if isinstance(rel,str) else None
   if path is None or not path.is_file():output_error='a rendered output is missing or escapes the manuscript';break
   actual[rel]=hashlib.sha256(path.read_bytes()).hexdigest()
  if output_error is None and actual!=stored.get('output_digests',{}):output_error='a rendered output changed after its receipt'
 elif stored:output_error='the render receipt names no outputs'
 input_digest=digest(inputs); style_version=digest(style)
 changed=[]
 recorded_inputs=stored.get('drawing_inputs') if isinstance(stored.get('drawing_inputs'),dict) else None
 if recorded_inputs is not None:
  if recorded_inputs.get('spec')!=inputs.get('spec'):
   changed.append({'kind':'visual-spec','state':'CHANGED','reason':'visual specification changed'})
  for key,label in (('data','plot data'),('tikz','TikZ source'),('supervised_run','supervised run artifact')):
   if recorded_inputs.get(key)!=inputs.get(key):
    path=(spec.get('source_data') if key=='data' else spec.get('source') if key=='tikz'
          else spec.get('run_id'))
    changed.append({'kind':key,'path':path,'state':'CHANGED',
                    'recorded_sha256':recorded_inputs.get(key),'current_sha256':inputs.get(key),
                    'reason':label+' bytes changed'})
 elif stored and stored.get('input_digest') not in {input_digest,
       digest({**inputs,'spec':_clean_spec(spec),'research_results':research_binding.get('bindings') or []})}:
  # Old receipts mixed result metadata into input_digest, so a mismatch cannot
  # honestly be called a changed drawing after migration.
  changed.append({'kind':'legacy-receipt','state':'UNKNOWN',
                  'reason':'legacy receipt does not separate drawing inputs from result metadata'})
 if stored and spec.get('kind')!='artifact' and stored.get('style_version')!=style_version:
  changed.append({'kind':'style','state':'CHANGED','reason':'visual style changed',
                  'recorded':stored.get('style_version'),'current':style_version})
 recorded_outputs=stored.get('output_digests') if isinstance(stored.get('output_digests'),dict) else {}
 for path in sorted(set(recorded_outputs)|set(actual)):
  if recorded_outputs.get(path)!=actual.get(path):
   changed.append({'kind':'rendered-output','path':path,'state':'MISSING' if path not in actual else 'CHANGED',
                   'recorded_sha256':recorded_outputs.get(path),'current_sha256':actual.get(path),
                   'reason':'rendered output is missing or changed'})
 if input_error: changed.append({'kind':'drawing-input','state':'MISSING','reason':input_error})
 drawing_unknown=any(row.get('state')=='UNKNOWN' for row in changed)
 drawing_changed=any(row.get('state') in {'CHANGED','MISSING'} for row in changed)
 drawing_status=('UNRENDERED' if not stored else 'UNKNOWN' if drawing_unknown and not drawing_changed
                 else 'STALE' if drawing_changed or output_error else 'CURRENT')
 current_basis=[{key:row.get(key) for key in ('id','revision','currentness')}
                for row in research_binding.get('bindings') or []]
 recorded_basis=stored.get('research_bindings') if isinstance(stored.get('research_bindings'),list) else None
 basis_changes=[]
 if not result_ids:
  basis_status='THEORY_ONLY'
 elif evidence_gap:
  basis_status='STALE';basis_changes.append({'kind':'research-binding','state':'STALE','reason':evidence_gap})
 elif not stored:
  basis_status='UNRENDERED'
 elif recorded_basis is None:
  # A matching legacy digest establishes that these exact bindings were part
  # of that receipt. A mismatch stays unknown rather than being mislabelled as
  # a changed image.
  legacy_digest=digest({**inputs,'spec':_clean_spec(spec),'research_results':research_binding.get('bindings') or []})
  if stored.get('input_digest')==legacy_digest:
   basis_status='CURRENT'
  else:
   basis_status='UNKNOWN';basis_changes.append({'kind':'research-binding','state':'UNKNOWN',
       'reason':'legacy receipt does not expose the prior result binding separately'})
 elif recorded_basis==current_basis:
  basis_status='CURRENT'
 else:
  basis_status='CHANGED';before={row.get('id'):row for row in recorded_basis};now={row.get('id'):row for row in current_basis}
  for ident in sorted(set(before)|set(now)):
   if before.get(ident)!=now.get(ident):basis_changes.append({'kind':'research-binding','id':ident,'state':'CHANGED','recorded':before.get(ident),'current':now.get(ident),'reason':'linked result record revision or currentness changed'})
 recorded_presentation=stored.get('presentation_metadata') if isinstance(stored.get('presentation_metadata'),dict) else None
 if not stored:presentation_status='UNRENDERED'
 elif recorded_presentation is None:presentation_status='UNKNOWN'
 elif recorded_presentation==presentation:presentation_status='CURRENT'
 else:presentation_status='CHANGED'
 metadata_changes=[] if presentation_status in {'CURRENT','UNRENDERED'} else [{
     'kind':'presentation-metadata','state':presentation_status,
     'recorded':recorded_presentation,'current':presentation,
     'reason':('legacy receipt did not pin title, question, caption, or source locator; no metadata change is inferred'
               if presentation_status=='UNKNOWN' else
               'title, scientific question, caption, or source locator changed without changing rendered image bytes')}]
 return {'status':drawing_status,'drawing_freshness':drawing_status,
         'evidence_binding_status':basis_status,
         'presentation_status':presentation_status,'presentation_metadata':presentation,
         'metadata_changes':metadata_changes,
         'input_files':input_files,
         'input_digest':input_digest,'drawing_inputs':inputs,'style_version':style_version,'style':style,
         'input_error':input_error,'evidence_gap':evidence_gap,'research_binding':research_binding,
         'research_bindings':current_basis,'basis_changes':basis_changes,
         'changed_dependencies':changed,'output_error':output_error,'output_digests':actual,'outputs':outputs}
def _render(manuscript:Path,spec:dict)->dict:
 import matplotlib.pyplot as plt
 issue=validate(spec)
 if issue:raise ValueError(issue)
 out=manuscript/'figures'/'generated';out.mkdir(parents=True,exist_ok=True)
 stem=out/spec['id']; house=spec['_house_style']
 base=Path(spec.get('_input_base') or manuscript)
 if spec['kind']=='artifact':
  artifact=_supervised_artifact(manuscript,base,spec);outputs=[]
  for fmt,path in artifact['sources'].items():
   target=stem.with_suffix('.'+fmt)
   if path.resolve()!=target.resolve():shutil.copy2(path,target)
   outputs.append(str(target.relative_to(manuscript)))
  return {'outputs':outputs,'renderer':'supervised-run-artifact',
          'source_provenance':{key:value for key,value in artifact.items() if key!='sources'}}
 if spec['kind']=='tikz':
  from laplace.pipeline import tikz_render
  snippet,_=_tikz_snippet(base,spec); work=out/('.'+spec['id']+'-tikz')
  shutil.rmtree(work,ignore_errors=True)
  rendered=tikz_render.render(snippet,style=house,out_dir=work)
  if rendered.get('status')!='READY':raise ValueError(rendered.get('reason') or 'TikZ render failed')
  outputs=[]
  for key,suffix in (('pdf_path','.pdf'),('png_path','.png'),('svg_path','.svg'),('source_path','.tikz')):
   value=rendered.get(key)
   if value:
    target=stem.with_suffix(suffix);shutil.copy2(value,target);outputs.append(str(target.relative_to(manuscript)))
  shutil.rmtree(work,ignore_errors=True)
  return {'outputs':outputs,'renderer':'tikz-pdf'}
 fig,ax=plt.subplots(figsize=(house['width_inches'],house['height_inches']),layout='constrained')
 if spec['kind']=='plot':
  src=spec.get('source_data'); path=_inside(base,src) if isinstance(src,str) else None
  if path is None or not path.is_file():raise ValueError('plot source_data must be a project-confined file')
  if path.suffix=='.json': rows=json.loads(path.read_text())
  else: rows=list(csv.DictReader(path.open()))
  x=spec.get('x'); series=spec.get('series') or []
  if not isinstance(x,str) or not isinstance(series,list) or not series or not rows:raise ValueError('plot needs x, at least one series and data rows')
  for y in series:
   if not isinstance(y,str):raise ValueError('series values must be fields')
   xs,ys=[float(r[x]) for r in rows],[float(r[y]) for r in rows]
   if not all(math.isfinite(v) for v in xs+ys):raise ValueError('non-finite data needs an explicit treatment')
   ax.plot(xs,ys,marker='o',label=y)
  ax.set_xlabel(spec.get('x_label') or x)
  ax.set_ylabel(spec.get('y_label') or (series[0] if len(series)==1 else 'Value'))
  if len(series)>1:ax.legend(frameon=False)
 else:
  nodes=spec.get('nodes') or []; edges=spec.get('edges') or []
  if spec['kind']=='tikz':raise ValueError('TikZ requires its authored source renderer; it cannot be rendered as a graph diagram')
  if not isinstance(nodes,list) or not nodes or not isinstance(edges,list):raise ValueError('diagram needs typed nodes and edges')
  pos={n['id'] for n in nodes if isinstance(n,dict) and n.get('id')}
  if not shutil.which('dot'): raise ValueError('Graphviz dot is unavailable for semantic diagrams')
  for e in edges:
   if e.get('source') not in pos or e.get('target') not in pos or not e.get('rel'):raise ValueError('edges need existing source,target,rel')
  # Graphviz carries the relation structure itself; labels are semantic relation
  # names, never decorative arrows inferred from proximity.
  esc=lambda x:str(x).replace('\\','\\\\').replace('"','\\"').replace('\n','\\n')
  dot=(f'digraph G {{ graph [rankdir=LR,bgcolor="{house["background"]}",pad=0.22,nodesep=0.5,ranksep=0.7]; '
       f'node [shape=box,style="rounded,filled",fillcolor="{house["diagram_fill"]}",color="{house["diagram_border"]}",fontname="{house["diagram_font"]}",fontsize={house["font_size"]},margin="0.18,0.12"]; '
       f'edge [fontname="{house["diagram_font"]}",fontsize={house["font_size"]},color="{house["ink"]}",penwidth={house["line_width"]}]; '
       +''.join(f'"{esc(n["id"])}" [label="{esc(n.get("label") or n["id"])}"];' for n in nodes)
       +' '.join(f'"{esc(e["source"])}" -> "{esc(e["target"])}" [label="{esc(e.get("label") or e["rel"].replace("_"," "))}"];' for e in edges)+' }')
  for suffix,fmt in (('.svg','svg'),('.pdf','pdf'),('.png','png')):
   subprocess.run(['dot','-T'+fmt,'-o',str(stem.with_suffix(suffix))],input=dot,text=True,check=True,capture_output=True,timeout=30)
  plt.close(fig)
  prov={'outputs':[str(stem.with_suffix(x).relative_to(manuscript)) for x in ('.svg','.pdf','.png')],'renderer':'graphviz-dot'}
  spec['render']=prov;return prov
 fig.savefig(stem.with_suffix('.svg'));fig.savefig(stem.with_suffix('.pdf'));fig.savefig(stem.with_suffix('.png'),dpi=house['preview_dpi']);plt.close(fig)
 prov={'outputs':[str(stem.with_suffix(x).relative_to(manuscript)) for x in ('.svg','.pdf','.png')],'renderer':'matplotlib'}
 spec['render']=prov;return prov


_RENDER_LOCK = threading.RLock()

def _style_path(project_root: Path | None = None) -> Path:
    """Resolve the shared style through the selected runtime checkout.

    An installed wheel lives under ``site-packages`` and therefore cannot use
    this module's parents as the project root.  The registry root honors the
    foreground server's ``LAPLACE_REPO_ROOT`` binding.
    """
    from laplace.pipeline import registry
    roots = ([Path(project_root).resolve()] if project_root is not None else [])
    roots.append(registry._repo_root().resolve())
    # Source-checkout compatibility for isolated unit fixtures whose temporary
    # registry intentionally contains no shared profiles.  Installed runtimes
    # cannot satisfy this candidate and must supply their selected root.
    roots.append(source_tree())
    for root in dict.fromkeys(roots):
        candidate = root / 'profiles/visual_style.json'
        if candidate.is_file():
            return candidate
    return roots[0] / 'profiles/visual_style.json'

def house_style(manuscript: Path, spec: dict, project_root: Path | None = None) -> dict:
    style = json.loads(_style_path(project_root).read_text())
    allowed = {'font_size', 'width_inches', 'height_inches', 'line_width', 'marker_size', 'grid', 'palette', 'preview_dpi'}
    from laplace.manuscript import document_style
    defaults = document_style.defaults_at(manuscript / 'manuscript_spec.json', manuscript / 'document_style.json', project_root or manuscript)
    document = defaults['values']
    for key, value in (document.get('visuals') or {}).items():
        if key in allowed: style[key] = value
    style['document_defaults_input'] = {key:defaults[key] for key in ('effective_origin','revision','consumed_source')}
    for key, value in (spec.get('style') or {}).items():
        if key not in allowed: raise ValueError(f'Unsupported figure style override: {key}')
        style[key] = value
    for key in allowed - {'grid', 'palette', 'preview_dpi'}:
        if not isinstance(style[key], (int,float)) or not 0 < style[key] < 100:
            raise ValueError(f'Invalid visual style value: {key}')
    if not isinstance(style['preview_dpi'], (int,float)) or not 72 <= style['preview_dpi'] <= 600:
        raise ValueError('Invalid visual preview resolution')
    if not isinstance(style['palette'],list) or not style['palette'] or any(not re.fullmatch(r'#[0-9A-Fa-f]{6}', str(c)) for c in style['palette']):
        raise ValueError('Invalid visual palette')
    return style

def render(manuscript: Path, spec: dict, project_root: Path | None = None) -> dict:
    """Apply the shared house style and bank the produced asset for existing consumers."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from cycler import cycler
    from filelock import FileLock
    observed = provenance(manuscript, spec, project_root)
    readiness=render_readiness(spec,observed)
    if not readiness['can_render']:
        raise ValueError(readiness['issues'][0]['reason'])
    if observed['status'] == 'CURRENT':
        if ((observed['evidence_binding_status'] == 'CHANGED' or observed['presentation_status']=='CHANGED' or
             'drawing_inputs' not in spec['render'] or 'research_bindings' not in spec['render'] or
             'presentation_metadata' not in spec['render'])
                and observed['research_binding']['status'] in {'CURRENT','THEORY_ONLY'}):
            spec['render'].update(research_bindings=observed['research_bindings'],
                                  drawing_inputs=observed['drawing_inputs'],
                                  drawing_input_digest=observed['input_digest'],
                                  presentation_metadata=observed['presentation_metadata'])
            return {**spec['render'], 'reused': True, 'basis_refreshed': True,
                    '_manifest_record':_record_manifest(manuscript,spec,spec['render'],observed)}
        return {**spec['render'], 'reused': True}
    style = observed['style']
    working = dict(spec)
    working['_input_base'] = str((project_root or manuscript).resolve())
    working['_house_style'] = style
    rc = {'font.family':style['font_family'], 'font.size':style['font_size'],
          'pdf.fonttype':42, 'svg.fonttype':'none',
          'axes.prop_cycle':cycler(color=style['palette']),
          'axes.spines.top':False, 'axes.spines.right':False,
          'xtick.direction':style['tick_direction'], 'ytick.direction':style['tick_direction'],
          'axes.axisbelow':True, 'axes.grid':bool(style['grid']),
          'lines.linewidth':style['line_width'], 'lines.markersize':style['marker_size']}
    with _RENDER_LOCK, plt.rc_context(rc):
        prior_figures = set(plt.get_fignums())
        try:
            result = _render(manuscript, working)
        finally:
            for figure in set(plt.get_fignums()) - prior_figures: plt.close(figure)
    result.update(input_digest=observed['input_digest'],drawing_input_digest=observed['input_digest'],
                  drawing_inputs=observed['drawing_inputs'],research_bindings=observed['research_bindings'],
                  presentation_metadata=observed['presentation_metadata'],
                  style_version=observed['style_version'],
                  style_profile=None if spec.get('kind')=='artifact' else 'profiles/visual_style.json',
                  visual_review='pending')
    result['output_digests']={p:hashlib.sha256((manuscript/p).read_bytes()).hexdigest() for p in result['outputs']}
    spec['render'] = {k:v for k,v in result.items() if k!='reused'}
    return {**result, '_manifest_record':_record_manifest(manuscript,spec,result,observed)}


def _record_manifest(manuscript:Path,spec:dict,result:dict,observed:dict)->dict:
    from filelock import FileLock
    manifest = manuscript/'figure_manifest.json'
    with FileLock(str(manifest)+'.lock'):
        value=json.loads(manifest.read_text()) if manifest.exists() else {'placed':[]}
        asset='figure:'+spec['id']
        previous=next((r for r in value.get('placed',[]) if r.get('asset_id')==asset),{})
        placed_at=previous.get('placed_at')
        placed_file=_inside(manuscript,placed_at) if isinstance(placed_at,str) else None
        if placed_file is None or not placed_file.is_file() or ('\\label{fig:'+spec['id']+'}') not in placed_file.read_text(encoding='utf8'):
            placed_at=None
        placement = ({'placed_at': placed_at,
                      'placed_at_scope': previous.get('placed_at_scope') or 'manuscript',
                      'placed_repo_file': previous.get('placed_repo_file')}
                     if placed_at else {'placed_at': None})
        row={'asset_id':asset,'label':'fig:'+spec['id'],'artefact':next(p for p in result['outputs'] if p.endswith('.pdf')),
             'generator':'manuscript_spec.json','spec_id':spec['id'],'promise':spec['question'],'matched':True,
             'caption':spec['caption'],'result_ids':spec.get('result_ids') or [],**placement,
             'research_binding':observed['research_binding'],
             'render':spec['render'],'visual_review':'pending',
             'source_kind':('data' if spec['kind']=='plot' else
                            'supervised-run-artifact' if spec['kind']=='artifact' else 'schematic')}
        value['placed']=[r for r in value.get('placed',[]) if r.get('asset_id')!=asset]+[row]
        temp=manifest.with_name(manifest.name+'.pending');temp.write_text(json.dumps(value,indent=2)+'\n');temp.replace(manifest)
    return row
