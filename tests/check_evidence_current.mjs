// Explicit current-artifact check, separate from the self-contained ordinary suite.
// Usage: node tests/check_evidence_current.mjs ARGUMENT_JSON VISUAL_JSON
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {installDOM,loadReader,transport,bodyOf,findButton,sha} from './helpers/evidence_reader_harness.mjs';
const [argumentPath,visualPath]=process.argv.slice(2);
assert.ok(argumentPath&&visualPath,'Supply exact saved argument and visual index paths; no implicit campaign setup.');
const sources=await Promise.all([argumentPath,visualPath].map(path=>readFile(path,'utf8')));
const [map,visual]=sources.map(text=>JSON.parse(text));
const dom=installDOM(),reader=await loadReader();
try{
 const request=transport(sources[0]);
 const argument=await reader.openArtifact({project:map.project,path:'argument-map.json',request:request.request});
 assert.equal(reader.snapshots.length,1);
 const detail=new (await import('./helpers/evidence_reader_harness.mjs')).Node('section');bodyOf(argument).append(detail);
 const declaredSections=new Set();let recordedOutputs=0;
 for(const node of map.nodes){
  await reader.snapshots[0].renderNode(detail,node.id);
  for(const key of node.sources||[]){
   const source=reader.recordedSource(map,key);
   if(source){assert.ok(detail.textContent.includes(source.path));assert.ok(detail.textContent.includes(source.sha256));
    assert.ok(findButton(detail,'Read pinned source snapshot '+key));
    if(source.lineRange)assert.ok(detail.textContent.includes('Recorded lines '+source.lineRange.join('–')));
    if(key.startsWith('@'))declaredSections.add(key);
   }
  }
  for(const binding of map.research_bindings||[])if(binding.claim===node.id){
   const result=map.results[binding.result];
   assert.ok(detail.textContent.includes(result.run));
   for(const file of reader.recordedResultFiles(result)){assert.ok(findButton(detail,'Open '+file.role+' '+file.path));if(file.role==='recorded output')recordedOutputs++;}
  }
 }
 assert.ok(declaredSections.has('@formal')&&declaredSections.has('@diamond'));
 assert.ok(recordedOutputs>=2);argument.close();
 const visualRequest=transport(sources[1]);
 const view=await reader.openArtifact({project:visual.project,path:'visual-index.json',request:visualRequest.request}),body=bodyOf(view);
 const outputs=visual.figures.flatMap(f=>reader.visualOutputs(f)).filter(o=>['pdf','svg'].includes(o.format));
 assert.ok(outputs.length>0);
 assert.equal(body.all().filter(n=>n.tag==='button'&&/^Open recorded (pdf|svg)$/.test(n.textContent)).length,outputs.length);
 for(const output of outputs)assert.ok(body.textContent.includes(output.sha256));
 for(const figure of visual.figures){assert.ok(body.textContent.includes(figure.caption));if(figure.placement){assert.ok(body.textContent.includes(figure.placement.source));assert.ok(body.textContent.includes('PDF page '+figure.placement.pdf_page));}}
 assert.equal(dom.editor.value,'UNSAVED manuscript');view.close();assert.deepEqual(dom.body.children,[dom.editor,dom.iframe]);
 const canonicalFetches=[...request.calls,...visualRequest.calls].filter(url=>!url.startsWith('/research/artifact?')).length;
 assert.equal(canonicalFetches,0,'saved-artifact checks must not query current canonical owners');
 console.log(JSON.stringify({status:'PASS',argument_sha256:sha(sources[0]),visual_sha256:sha(sources[1]),
  nodes:map.nodes.length,declared_mechanism_sections:[...declaredSections].sort(),recorded_output_controls:recordedOutputs,
  figures:visual.figures.length,vector_controls:outputs.length,argument_chunks:request.calls.length,visual_chunks:visualRequest.calls.length,
  canonical_fetches:canonicalFetches,qualification:'Current saved bytes through actual adapter/card renderer with local DOM/transport doubles; not real browser acceptance.'},null,2));
}finally{reader.destroy();dom.restore();}
