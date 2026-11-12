import json
from laplace.research import visuals_surface as vs

def test_house_style_uses_runtime_root_when_module_is_installed(tmp_path,monkeypatch):
 from laplace.pipeline import visual_production as vp
 root=tmp_path/'selected-checkout';manuscript=root/'project'/'manuscript'
 manuscript.mkdir(parents=True);(root/'profiles').mkdir()
 style={
  'font_family':'serif','diagram_font':'DejaVu Serif','font_size':9,
  'width_inches':6.4,'height_inches':3.9,'line_width':1.5,'marker_size':4,
  'tick_direction':'in','grid':False,'palette':['#0072B2'],'ink':'#243039',
  'background':'#ffffff','diagram_fill':'#f1f5f3','diagram_border':'#477363',
  'preview_dpi':170,'embedded_title':False}
 (root/'profiles'/'visual_style.json').write_text(json.dumps(style))
 monkeypatch.setenv('LAPLACE_REPO_ROOT',str(root))
 monkeypatch.setattr(vp,'__file__','/usr/local/lib/python3.12/site-packages/laplace/pipeline/visual_production.py')

 loaded=vp.house_style(manuscript,{})

 assert loaded['font_family']=='serif'
 assert vp._style_path()==root/'profiles'/'visual_style.json'

def _post(path,payload):
 s,_,b=vs.handle(path,{},'POST',json.dumps(payload).encode());return s,json.loads(b)
def _registered_visual_fixture(root,monkeypatch):
 (root/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'x','kind':'conceptric',
  'project_dir':'.','tex_root':'.','manuscript_dir':'.'}]}))
 (root/'main.tex').write_text('\\documentclass{article}\n\\begin{document}\nGeneric visual fixture.\n\\end{document}\n')
 monkeypatch.setattr(vs,'_r',lambda:root)
def test_create_render_plot_and_diagram_with_real_vectors(tmp_path,monkeypatch):
 _registered_visual_fixture(tmp_path,monkeypatch)
 (tmp_path/'data.csv').write_text('x,score\n1,0.2\n2,0.6\n3,0.8\n')
 plot={'id':'synthetic-plot','title':'Synthetic fixture plot','question':'Does the fixture trend rise?','kind':'plot','caption':'Synthetic fixture data; not a scientific result.','source_data':'data.csv','x':'x','series':['score']}
 assert _post('/visuals/create',{'project':'x','spec':plot})[0]==201
 s,out=_post('/visuals/render',{'project':'x','id':'synthetic-plot'});assert s==200 and out['render']['renderer']=='matplotlib'
 assert (tmp_path/'figures/generated/synthetic-plot.svg').stat().st_size>500
 diagram={'id':'synthetic-diagram','title':'Synthetic evidence relation','question':'How does a claim meet evidence?','kind':'diagram','caption':'Synthetic relation fixture; arrows state declared relations.','nodes':[{'id':'claim','label':'Claim'},{'id':'evidence','label':'Evidence'}],'edges':[{'source':'evidence','target':'claim','rel':'validated_by'}]}
 assert _post('/visuals/create',{'project':'x','spec':diagram})[0]==201
 s,out=_post('/visuals/render',{'project':'x','id':'synthetic-diagram'});assert s==200 and out['render']['renderer']=='graphviz-dot'
 assert (tmp_path/'figures/generated/synthetic-diagram.pdf').stat().st_size>500
 # Same source/style reuses output; a changed input invalidates it.
 assert _post('/visuals/render',{'project':'x','id':'synthetic-plot'})[1]['render'].get('reused') is True
 (tmp_path/'data.csv').write_text('x,score\n1,0.3\n2,0.7\n')
 assert not _post('/visuals/render',{'project':'x','id':'synthetic-plot'})[1]['render'].get('reused',False)
def test_plot_path_escape_refuses(tmp_path):
 spec={'id':'bad','title':'Bad','question':'q','kind':'plot','caption':'c','source_data':'../x.csv','x':'x','series':['y']}
 from laplace.pipeline import visual_production as vp
 try:vp.render(tmp_path,spec);assert False
 except ValueError as e:assert 'project-confined' in str(e)

def test_registered_render_is_asset_and_can_be_placed(tmp_path):
 import shutil,subprocess
 from laplace.pipeline import asset_model
 root=tmp_path; m=root/'proj/manuscript';m.mkdir(parents=True)
 (root/'registry_projects.json').write_text('{"projects":[{"name":"p","kind":"conceptric","project_dir":"proj","tex_root":"proj/manuscript"}]}')
 (m/'main.tex').write_text('\\documentclass{article}\n\\begin{document}\nText.\n\\end{document}\n')
 (root/'proj/data.csv').write_text('x,y\n1,2\n2,3\n')
 spec={'id':'live','title':'Fixture','question':'q?','kind':'plot','caption':'Synthetic fixture.','source_data':'data.csv','x':'x','series':['y']}
 s,_,_=vs.handle('/visuals/create',{},'POST',json.dumps({'project':'p','spec':spec}).encode(),repo_root=root);assert s==201
 s,_,_=vs.handle('/visuals/render',{},'POST',json.dumps({'project':'p','id':'live'}).encode(),repo_root=root);assert s==200
 old=asset_model._repo_root;asset_model._repo_root=lambda:root
 from laplace.pipeline.asset_model import AssetRoots
 asset_model.ASSET_ROOTS['p']=AssetRoots(figures=('proj/manuscript/figures',),derivations=())
 try: assert any(a.id=='figure:live' for a in asset_model.enumerate_assets('p'))
 finally: asset_model._repo_root=old;asset_model.ASSET_ROOTS.pop('p',None)
 s,_,body=vs.handle('/visuals/place',{},'POST',json.dumps({'project':'p','id':'live','section':'main.tex'}).encode(),repo_root=root);assert s==200
 assert '\\label{fig:live}' in (m/'main.tex').read_text()
 # Canonical store owns new specs and placement is idempotent (one label).
 assert (m/'manuscript_spec.json').is_file() and not (m/'visual_specs.json').exists()
 s,_,_=vs.handle('/visuals/place',{},'POST',json.dumps({'project':'p','id':'live','section':'main.tex'}).encode(),repo_root=root);assert s==200
 assert (m/'main.tex').read_text().count('\\label{fig:live}')==1
 if shutil.which('pdflatex'):
  compiled=subprocess.run(['pdflatex','-interaction=nonstopmode','main.tex'],cwd=m,capture_output=True,timeout=30)
  assert (m/'main.pdf').is_file() and b'Fatal error' not in compiled.stdout


def test_legacy_specs_survive_canonical_manifest_without_figure_specs(tmp_path):
 from laplace.pipeline import visual_production as vp
 legacy={'id':'legacy','title':'Legacy','question':'Why?','kind':'diagram','caption':'Legacy diagram.'}
 (tmp_path/'manuscript_spec.json').write_text(json.dumps({'manuscript':{'genre':'book'}}))
 (tmp_path/'visual_specs.json').write_text(json.dumps({'specs':[legacy]}))

 loaded=vp.load(tmp_path)

 assert loaded['authority']=='visual_specs.json (legacy)'
 assert loaded['specs']==[legacy]


def test_legacy_incomplete_diagram_is_visible_but_never_advertised_renderable(tmp_path,monkeypatch):
 from laplace.pipeline import visual_production as vp
 monkeypatch.setattr(vs,'_m',lambda p,*args:tmp_path)
 legacy={'id':'legacy-map','title':'Legacy map','question':'What is related?','kind':'diagram',
         'caption':'A retained legacy brief.','result_ids':['result:one']}
 (tmp_path/'visual_specs.json').write_text(json.dumps({'specs':[legacy]}))
 status,_,body=vs.handle('/visuals/state',{'project':['x']},'GET',b'')
 assert status==200
 row=json.loads(body)['specs'][0]
 readiness=row['render_readiness']
 assert readiness['status']=='INCOMPLETE' and readiness['can_render'] is False
 assert {issue['field'] for issue in readiness['issues']}=={'nodes','edges'}
 assert readiness['current_revision']==vp.digest(legacy)
 status,_,body=vs.handle('/visuals/render',{},'POST',json.dumps({'project':'x','id':'legacy-map'}).encode())
 assert status==422 and json.loads(body)['render_readiness']['can_render'] is False


def test_render_readiness_keeps_valid_renderer_variants_available():
 from laplace.pipeline import visual_production as vp
 common={'title':'T','question':'Q?','caption':'C'}
 specs=[{**common,'id':'plot','kind':'plot','source_data':'data.csv','x':'x','series':['y']},
        {**common,'id':'diagram','kind':'diagram','nodes':[{'id':'a'}],'edges':[]},
        {**common,'id':'tikz','kind':'tikz','tikz':'\\begin{tikzpicture}\\end{tikzpicture}'},
        {**common,'id':'artifact','kind':'artifact','run_id':'run-one','artifact_id':'panel'}]
 assert all(vp.render_readiness(spec)['can_render'] for spec in specs)


def test_missing_data_and_tampered_outputs_are_never_current_or_reused(tmp_path,monkeypatch):
 _registered_visual_fixture(tmp_path,monkeypatch)
 missing={'id':'missing','title':'Missing','question':'Where?','kind':'plot','caption':'Missing data.','source_data':'absent.csv','x':'x','series':['y']}
 assert _post('/visuals/create',{'project':'x','spec':missing})[0]==201
 s,_,body=vs.handle('/visuals/state',{'project':['x']},'GET',b'');assert s==200
 row=json.loads(body)['specs'][0];assert row['render_freshness']=='UNRENDERED' and row['currentness']['input_error']
 assert _post('/visuals/render',{'project':'x','id':'missing'})[0]==422

 (tmp_path/'data.csv').write_text('x,y\n1,2\n2,3\n')
 good={'id':'fresh','title':'Fresh','question':'Trend?','kind':'plot','caption':'Fixture.','source_data':'data.csv','x':'x','series':['y']}
 assert _post('/visuals/create',{'project':'x','spec':good})[0]==201
 assert _post('/visuals/render',{'project':'x','id':'fresh'})[0]==200
 target=tmp_path/'figures/generated/fresh.png';target.write_bytes(b'tampered')
 s,_,body=vs.handle('/visuals/state',{'project':['x']},'GET',b'');row=next(x for x in json.loads(body)['specs'] if x['id']=='fresh')
 assert row['render_freshness']=='STALE' and 'changed' in row['currentness']['output_error']
 assert vs.handle('/visuals/asset',{'project':['x'],'id':['fresh'],'format':['png']},'GET',b'')[0]==409
 s,out=_post('/visuals/render',{'project':'x','id':'fresh'});assert s==200 and not out['render'].get('reused',False)
 assert target.read_bytes()!=b'tampered'
 (tmp_path/'data.csv').write_text('x,y\n1,8\n2,13\n')
 s,_,body=vs.handle('/visuals/state',{'project':['x']},'GET',b'');row=next(x for x in json.loads(body)['specs'] if x['id']=='fresh')
 assert row['render_freshness']=='STALE'
 assert row['currentness']['changed_dependencies'][0]['path']=='data.csv'
 assert row['currentness']['changed_dependencies'][0]['reason']=='plot data bytes changed'
 assert vs.handle('/visuals/asset',{'project':['x'],'id':['fresh'],'format':['png'],'inspect':['1']},'GET',b'')[0]==200


def test_tikz_render_uses_bounded_snippet_and_shared_receipt(tmp_path,monkeypatch):
 from laplace.pipeline import tikz_render,visual_production as vp
 def fake(snippet,*,style,out_dir,timeout=45):
  out=__import__('pathlib').Path(out_dir);out.mkdir(parents=True,exist_ok=True)
  (out/'diagram.pdf').write_bytes(b'%PDF-tikz');(out/'diagram.png').write_bytes(b'png')
  (out/'diagram.tikz').write_text(snippet)
  return {'status':'READY','pdf_path':str(out/'diagram.pdf'),'png_path':str(out/'diagram.png'),'svg_path':None,'source_path':str(out/'diagram.tikz')}
 monkeypatch.setattr(tikz_render,'render',fake)
 snippet='\\begin{tikzpicture}\\node {A};\\end{tikzpicture}'
 spec={'id':'tikz-one','title':'TikZ','question':'Structure?','kind':'tikz','caption':'Authored TikZ.','tikz':snippet}

 result=vp.render(tmp_path,spec,project_root=tmp_path)

 assert result['renderer']=='tikz-pdf' and result['output_digests']
 assert (tmp_path/'figures/generated/tikz-one.tikz').read_text()==snippet
 assert vp.provenance(tmp_path,spec,tmp_path)['status']=='CURRENT'
 (tmp_path/'authored.tikz').write_text(snippet)
 sourced={**spec,'id':'tikz-source','source':'authored.tikz'};sourced.pop('tikz');sourced.pop('render',None)
 assert vp.render(tmp_path,sourced,project_root=tmp_path)['renderer']=='tikz-pdf'
 bad={**spec,'id':'tikz-bad','tikz':'\\input{/etc/passwd} '+snippet};bad.pop('render',None)
 try:vp.render(tmp_path,bad,project_root=tmp_path);assert False
 except ValueError as exc:assert 'forbidden' in str(exc)
 escaped={**sourced,'id':'tikz-escape','source':'../outside.tikz'};escaped.pop('render',None)
 try:vp.render(tmp_path,escaped,project_root=tmp_path);assert False
 except ValueError as exc:assert 'project-confined' in str(exc)


def test_nonrendering_caption_metadata_changes_without_staling_drawing(tmp_path,monkeypatch):
 from laplace.pipeline import visual_production as vp
 def fake_render(base,spec):
  out=base/'figures/generated';out.mkdir(parents=True,exist_ok=True);target=out/(spec['id']+'.pdf');target.write_bytes(b'%PDF-same-drawing')
  return {'outputs':[str(target.relative_to(base))],'renderer':'fixture'}
 monkeypatch.setattr(vp,'_render',fake_render)
 (tmp_path/'data-a.csv').write_text('x,y\n1,2\n')
 (tmp_path/'data-b.csv').write_text('x,y\n1,2\n')
 spec={'id':'caption-only','title':'Original title','question':'Original question?',
       'kind':'plot','caption':'Original caption.','source_data':'data-a.csv','x':'x','series':['y']}
 vp.render(tmp_path,spec,project_root=tmp_path)

 spec['caption']='Revised explanatory caption.';spec['source_data']='data-b.csv'
 observed=vp.provenance(tmp_path,spec,tmp_path)

 assert observed['drawing_freshness']=='CURRENT'
 assert observed['presentation_status']=='CHANGED'
 assert observed['changed_dependencies']==[]
 refreshed=vp.render(tmp_path,spec,project_root=tmp_path)
 assert refreshed['reused'] is True and refreshed['basis_refreshed'] is True
 assert vp.provenance(tmp_path,spec,tmp_path)['presentation_status']=='CURRENT'


def test_new_book_visual_roundtrip_is_registry_discovered_walk_served_and_compilable(tmp_path,monkeypatch):
 import shutil,subprocess
 from urllib.parse import parse_qs,urlparse
 from laplace.manuscript import manuscript_source, review_surface, walk
 from laplace.projects import library as writing_projects
 from laplace.pipeline import asset_model,registry

 status,created=writing_projects.create({'name':'visual-book','title':'Visual Book','kind':'book'},tmp_path)
 assert status==201,created
 project=tmp_path/'synthetics papers/visual-book';manuscript=project/'manuscript'
 chapter_path=manuscript/'chapters/chapter-01.tex'
 chapter_path.write_text('\\chapter{First}\nFirst section prose.\n\\section{Second}\nSecond section prose.\n')
 (project/'data.csv').write_text('x,y\n1,2\n2,4\n')
 spec={'id':'book-plot','title':'Book plot','question':'Does y rise?','kind':'plot','caption':'A bounded fixture plot.','source_data':'data.csv','x':'x','series':['y']}
 assert vs.handle('/visuals/create',{},'POST',json.dumps({'project':'visual-book','spec':spec}).encode(),repo_root=tmp_path)[0]==201
 assert vs.handle('/visuals/render',{},'POST',json.dumps({'project':'visual-book','id':'book-plot'}).encode(),repo_root=tmp_path)[0]==200

 monkeypatch.setattr(asset_model,'_repo_root',lambda:tmp_path)
 monkeypatch.setattr(registry,'_repo_root',lambda:tmp_path)
 monkeypatch.setattr(review_surface,'_repo_root',lambda:tmp_path)
 monkeypatch.setattr(walk,'_repo_root',lambda:tmp_path)
 assets=asset_model.enumerate_assets('visual-book')
 assert any(a.id=='figure:book-plot' for a in assets)
 s,ctype,pdf=vs.handle('/visuals/asset',{'project':['visual-book'],'id':['book-plot'],'format':['pdf']},'GET',b'',repo_root=tmp_path)
 assert s==200 and ctype=='application/pdf' and pdf.startswith(b'%PDF')

 chapter='synthetics papers/visual-book/manuscript/chapters/chapter-01.tex'
 original=(tmp_path/chapter).read_bytes()
 invalid=vs.handle('/visuals/place',{},'POST',json.dumps({'project':'visual-book','id':'book-plot','file':chapter,'after_line':0}).encode(),repo_root=tmp_path)
 assert invalid[0]==422 and (tmp_path/chapter).read_bytes()==original
 conflict=vs.handle('/visuals/place',{},'POST',json.dumps({'project':'visual-book','id':'book-plot','file':chapter,'after_line':2,'base_revision':'0'*64}).encode(),repo_root=tmp_path)
 assert conflict[0]==409 and (tmp_path/chapter).read_bytes()==original
 stale_source=vs.handle('/visuals/place',{},'POST',json.dumps({'project':'visual-book','id':'book-plot','file':chapter,'after_line':2,'expected_source_revision':'stale'}).encode(),repo_root=tmp_path)
 assert stale_source[0]==409 and 'manuscript revision conflict' in json.loads(stale_source[2])['error']
 assert (tmp_path/chapter).read_bytes()==original
 expected_source=manuscript_source.resolve('visual-book',repo_root=tmp_path)['revision']
 placed=vs.handle('/visuals/place',{},'POST',json.dumps({'project':'visual-book','id':'book-plot','file':chapter,'after_line':2,'expected_source_revision':expected_source}).encode(),repo_root=tmp_path)
 assert placed[0]==200,json.loads(placed[2])
 assert json.loads(placed[2])['source_revision']==manuscript_source.resolve('visual-book',repo_root=tmp_path)['revision']
 placed_text=(tmp_path/chapter).read_text()
 assert '\\label{fig:book-plot}' in placed_text
 assert placed_text.index('First section prose.') < placed_text.index('\\label{fig:book-plot}') < placed_text.index('\\section{Second}')
 assert 'graphicx' in (manuscript/'Visual-Book.tex').read_text()
 assert (manuscript/'feedback/feedback.jsonl').is_file()
 assert (manuscript/'editor_saves/index.json').is_file()
 feedback=[json.loads(line) for line in (manuscript/'feedback/feedback.jsonl').read_text().splitlines()]
 assert any(row.get('kind')=='author-rewrite' and 'Placed generated visual' in row.get('comment','') for row in feedback)
 saves=json.loads((manuscript/'editor_saves/index.json').read_text())['saves']
 assert any(row.get('source')=='rewrite' and row.get('file')=='chapter-01.tex' for row in saves)

 model=walk.doc('visual-book');encoded=json.dumps(model)
 assert '/walk/asset?' in encoded and 'book-plot' in encoded
 def routes(value):
  if isinstance(value,dict):
   if value.get('route'):yield value['route']
   for child in value.values():yield from routes(child)
  elif isinstance(value,list):
   for child in value:yield from routes(child)
 route=next(x for x in routes(model) if x.startswith('/walk/asset?'))
 query=parse_qs(urlparse(route).query)
 served=walk.handle('/walk/asset',query,'GET',b'')
 assert served[0]==200 and served[2]
 if shutil.which('pdflatex'):
  compiled=subprocess.run(['pdflatex','-interaction=nonstopmode','-halt-on-error','Visual-Book.tex'],cwd=manuscript,capture_output=True,timeout=30)
  assert compiled.returncode==0,compiled.stdout[-2000:]
  assert (manuscript/'Visual-Book.pdf').is_file()


def test_nested_selected_edition_uses_relative_asset_and_preserves_placement_on_rerender(tmp_path,monkeypatch):
 import shutil,subprocess
 from urllib.parse import parse_qs,urlparse
 from laplace.manuscript import review_surface, walk
 from laplace.pipeline import asset_model,registry

 project=tmp_path/'nested';manuscript=project/'manuscript';source=manuscript/'tex';chapters=source/'chapters'
 chapters.mkdir(parents=True)
 (source/'main.tex').write_text('\\documentclass{book}\n\\usepackage{graphicx}\n\\begin{document}\n\\input{chapters/one}\n\\end{document}\n')
 chapter=chapters/'one.tex';chapter.write_text('\\chapter{One}\nNested prose.\n')
 (project/'data.csv').write_text('x,y\n1,2\n2,3\n')
 (tmp_path/'registry_projects.json').write_text(json.dumps({'projects':[{
  'name':'nested','kind':'conceptric','project_dir':'nested','tex_root':'nested/manuscript',
  'manifest':{'document':{'root':'nested/manuscript/tex/main.tex','manuscript_dir':'nested/manuscript/tex','edition':'nested'}}}]}))
 spec={'id':'nested-plot','title':'Nested plot','question':'Nested?','kind':'plot','caption':'Nested edition plot.','source_data':'data.csv','x':'x','series':['y']}
 assert vs.handle('/visuals/create',{},'POST',json.dumps({'project':'nested','spec':spec}).encode(),repo_root=tmp_path)[0]==201
 assert vs.handle('/visuals/render',{},'POST',json.dumps({'project':'nested','id':'nested-plot'}).encode(),repo_root=tmp_path)[0]==200

 monkeypatch.setattr(asset_model,'_repo_root',lambda:tmp_path);monkeypatch.setattr(registry,'_repo_root',lambda:tmp_path)
 monkeypatch.setattr(review_surface,'_repo_root',lambda:tmp_path);monkeypatch.setattr(walk,'_repo_root',lambda:tmp_path)
 repo_file='nested/manuscript/tex/chapters/one.tex'
 placed=vs.handle('/visuals/place',{},'POST',json.dumps({'project':'nested','id':'nested-plot','file':repo_file,'after_line':2}).encode(),repo_root=tmp_path)
 assert placed[0]==200,json.loads(placed[2])
 assert '\\includegraphics[width=\\linewidth]{../figures/generated/nested-plot}' in chapter.read_text()
 manifest=json.loads((manuscript/'figure_manifest.json').read_text());row=manifest['placed'][0]
 assert row['placed_at']=='tex/chapters/one.tex' and row['placed_at_scope']=='manuscript'
 assert row['placed_repo_file']==repo_file

 (project/'data.csv').write_text('x,y\n1,5\n2,8\n')
 rerender=vs.handle('/visuals/render',{},'POST',json.dumps({'project':'nested','id':'nested-plot'}).encode(),repo_root=tmp_path)
 assert rerender[0]==200 and not json.loads(rerender[2])['render'].get('reused',False)
 row=json.loads((manuscript/'figure_manifest.json').read_text())['placed'][0]
 assert row['placed_at']=='tex/chapters/one.tex' and row['placed_repo_file']==repo_file

 assert any(a.id=='figure:nested-plot' for a in asset_model.enumerate_assets('nested'))
 model=walk.doc('nested');routes=[]
 def collect(value):
  if isinstance(value,dict):
   if value.get('route'):routes.append(value['route'])
   for child in value.values():collect(child)
  elif isinstance(value,list):
   for child in value:collect(child)
 collect(model);route=next(x for x in routes if 'nested-plot' in x);query=parse_qs(urlparse(route).query)
 assert walk.handle('/walk/asset',query,'GET',b'')[0]==200
 if shutil.which('pdflatex'):
  compiled=subprocess.run(['pdflatex','-interaction=nonstopmode','-halt-on-error','main.tex'],cwd=source,capture_output=True,timeout=30)
  assert compiled.returncode==0,compiled.stdout[-2000:]
  assert (source/'main.pdf').is_file()


def test_visual_consumes_only_linked_research_result_revision_and_currentness(tmp_path, monkeypatch):
 from laplace.research import research_records
 from laplace.pipeline import visual_production as vp
 root=tmp_path;manuscript=root/'proj/manuscript';manuscript.mkdir(parents=True)
 (root/'registry_projects.json').write_text(json.dumps({'projects':[{
  'name':'p','kind':'conceptric','project_dir':'proj','tex_root':'proj/manuscript'}]}))
 linked=manuscript/'linked.json';linked.write_text('{"value":1}\n')
 other=manuscript/'other.json';other.write_text('{"value":2}\n')
 _,linked_created=research_records.record('p',{'kind':'result','id':'result:linked','result':'linked.json'},root)
 assert research_records.record('p',{'kind':'result','id':'result:other','result':'other.json'},root)[0]==201

 def fake_render(base,spec):
  out=base/'figures/generated';out.mkdir(parents=True,exist_ok=True);stem=out/spec['id']
  for suffix in ('.svg','.pdf','.png'):stem.with_suffix(suffix).write_bytes(('asset'+suffix).encode())
  return {'outputs':[str(stem.with_suffix(s).relative_to(base)) for s in ('.svg','.pdf','.png')],
          'renderer':'fixture'}
 monkeypatch.setattr(vp,'_render',fake_render)
 spec={'id':'linked-figure','title':'Linked','question':'What changed?','kind':'diagram',
       'caption':'Linked result.','nodes':[{'id':'a'}],'edges':[],
       'result_ids':['result:linked']}
 assert vp.render(manuscript,spec,project_root=root/'proj')['renderer']=='fixture'
 current=vp.provenance(manuscript,spec,root/'proj')
 assert current['status']=='CURRENT'
 assert current['research_binding']['bindings'][0]['id']=='result:linked'

 other.write_text('{"value":9}\n')
 assert vp.provenance(manuscript,spec,root/'proj')['status']=='CURRENT'
 linked.write_text('{"value":3}\n')
 stale=vp.provenance(manuscript,spec,root/'proj')
 assert stale['drawing_freshness']=='CURRENT'
 assert stale['evidence_binding_status']=='STALE' and 'result:linked' in stale['evidence_gap']
 assert stale['changed_dependencies']==[]

 renewed_status,renewed=research_records.record('p',{
  'record':{'kind':'result','id':'result:linked','result':'linked.json'},
  'expected_revision':linked_created['record']['revision']},root)
 assert renewed_status==200
 refreshed=vp.provenance(manuscript,spec,root/'proj')
 assert refreshed['drawing_freshness']=='CURRENT' and refreshed['evidence_gap'] is None
 assert refreshed['evidence_binding_status']=='CHANGED'
 assert refreshed['basis_changes'][0]['id']=='result:linked'
 assert refreshed['research_binding']['bindings'][0]['revision']==renewed['record']['revision']
 rerender=vp.render(manuscript,spec,project_root=root/'proj')
 assert rerender['renderer']=='fixture' and rerender['reused'] and rerender['basis_refreshed']
 assert vp.provenance(manuscript,spec,root/'proj')['evidence_binding_status']=='CURRENT'
 vp.save(manuscript,{'specs':[spec]})
 s,_,body=vs.handle('/visuals/state',{'project':['p']},'GET',b'',repo_root=root)
 surfaced=next(row for row in json.loads(body)['specs'] if row['id']=='linked-figure')
 assert s==200 and surfaced['currentness']['research_binding']['status']=='CURRENT'

 theory={**spec,'id':'theory-figure'};theory.pop('result_ids');theory.pop('render',None)
 vp.render(manuscript,theory,project_root=root/'proj')
 assert vp.provenance(manuscript,theory,root/'proj')['research_binding']['status']=='THEORY_ONLY'
 assert vp.provenance(manuscript,theory,root/'proj')['status']=='CURRENT'
 unresolved={**spec,'id':'unresolved-figure','result_ids':['result:missing']};unresolved.pop('render',None)
 vp.render(manuscript,unresolved,project_root=root/'proj')
 gap=vp.provenance(manuscript,unresolved,root/'proj')
 assert gap['drawing_freshness']=='CURRENT' and gap['evidence_binding_status']=='STALE'
 assert 'unresolved' in gap['evidence_gap']
