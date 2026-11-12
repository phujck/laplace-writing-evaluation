import {fileURLToPath} from 'node:url';
import test from 'node:test';import assert from 'node:assert/strict';import {execFileSync} from 'node:child_process';
import {readManuscriptSource,saveManuscriptSource,readHistoricalSource} from '../src/laplace/web/static_shared/manuscript-source-client.mjs';
import {documentPdfURL,documentPdfNotice} from '../src/laplace/web/static_shared/manuscript-document-view.mjs';
import {sourceDraftBelongs} from '../src/laplace/web/static_shared/manuscript-editor.mjs';
// Produce representative values through the actual Python owners, not a second
// JavaScript imitation of their schema. All effects live in a disposable root.
const fixture=JSON.parse(execFileSync(fileURLToPath(new URL('../scripts/laplace-python',import.meta.url)),['-c',String.raw`
import tempfile,json
from pathlib import Path
from laplace.manuscript import projection_viewer as pv, manuscript_source as ms, manuscript_versions; from laplace.web import shared_ui; from laplace.work import history as author_history
from laplace.manuscript.document import current
with tempfile.TemporaryDirectory(prefix='editor-wire-fixture-') as temp:
 root=Path(temp);md=root/'paper';md.mkdir()
 main='\\documentclass{article}\n\\begin{document}\n\\input{body}\n\\end{document}\n'.replace('\\\\','\\')
 (md/'main.tex').write_text(main);(md/'other.tex').write_text(main)
 (md/'body.tex').write_text('Observed owner source.\n')
 config={'projects':[{'name':'paper','project_dir':'paper','tex_root':'paper','manifest':{'document':{'root':'main.tex','edition':'same-label'}}}]}
 registry=root/'registry_projects.json';registry.write_text(json.dumps(config));pv._repo_root=lambda:root
 def query(v):return {k:[str(x)] for k,x in v.items()}
 code,_,raw=pv.handle('/projection/tex',query({'corpus':'paper','file':'paper/body.tex','view':'source'}),'GET',b'');assert code==200
 observed=json.loads(raw);first=current('paper',root)
 code,_,raw=pv.handle(observed['save_handle']['route'],query({**observed['save_handle']['query'],'author':'fixture'}),'POST',b'Actual owner save.\n');assert code==200
 receipt=json.loads(raw)
 historical=('Archived unicode \U0001f30d.\n'*3000).encode('utf8')
 stored=pv.bank_editor_save(md,md/'body.tex',historical,author='fixture',surface='test')
 rows=manuscript_versions.versions_payload('paper',root)['rows'];row=next(r for r in rows if r['id']==stored['version_id']);handle=row['source_read'];pages=[];next_read=handle
 while next_read:
  page=author_history.source('paper',next_read['query'],root);pages.append(page);next_read=page['next_read']
 (md/'main.pdf').write_bytes(b'%PDF-1.4 fixture output')
 pdf=current('paper',root)
 config['projects'][0]['manifest']['document']['root']='other.tex';registry.write_text(json.dumps(config));second=current('paper',root)
 print(json.dumps({'observed':observed,'receipt':receipt,'history_handle':handle,'history_pages':pages,'history_text':historical.decode(),'pdf':pdf,'first':first,'second':second}))
`],{cwd:new URL('..',import.meta.url),env:{...process.env,PYTHONPATH:'src'},encoding:'utf8',maxBuffer:2000000}));
test('shared source client consumes actual owner read/save guards and receipt',async()=>{const observed=await readManuscriptSource({project:'paper',file:fixture.observed.file,transport:async()=>fixture.observed});const result=await saveManuscriptSource({project:'paper',observed,content:'Actual owner save.\n',transport:async(route,options)=>{assert.equal(route,observed.save_handle.route);assert.equal(options.params.expected_selection,observed.selection_identity);assert.equal(options.params.file,observed.file);return fixture.receipt;}});assert.equal(result.source_committed,true);});
test('exact historical source consumer follows actual owner Unicode pagination and never uses current source route',async()=>{let index=0;const result=await readHistoricalSource(fixture.history_handle,{project:'paper',file:fixture.history_handle.query.file,transport:async(route,options)=>{assert.equal(route,'/authoring/history');const page=fixture.history_pages[index++];assert.equal(options.params.offset,page.offset);if(index>1)assert.equal(options.params.expected_content_revision,page.content_revision);return page;}});assert.equal(result.content,fixture.history_text);assert.equal(result.archive_identity.verification,'VERIFIED');assert.equal(index,fixture.history_pages.length);assert.ok(index>1);});
test('canonical PDF URL and unverified provenance are consumed from the actual document owner',()=>{const url=documentPdfURL(fixture.pdf),q=new URL(url,'http://fixture').searchParams;assert.equal(q.get('expected_content_revision'),fixture.pdf.pdf_identity.content_revision);assert.match(documentPdfNotice(fixture.pdf,true),/Unsaved edits are not included/);assert.match(documentPdfNotice(fixture.pdf),/build basis is unverified/);assert.throws(()=>documentPdfURL({...fixture.pdf,project:'different-project'}),/does not match/);});
test('same-label roots sharing an included file have distinct draft authority',()=>{assert.equal(fixture.first.selected_source.edition,fixture.second.selected_source.edition);assert.notEqual(fixture.first.selection_identity,fixture.second.selection_identity);const draft={file:fixture.observed.file,base:'old',content:'draft',observed:fixture.observed};assert.equal(sourceDraftBelongs(draft,fixture.first),true);assert.equal(sourceDraftBelongs(draft,fixture.second),false);assert.ok(fixture.second.files.some(row=>row.file===draft.file));});
