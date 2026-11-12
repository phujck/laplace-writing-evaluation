// RETENTION PROBE (Sol 2026-10-13, second form). Run under `node --expose-gc`.
//
// Route: the ACTUAL owner-read door opens a template-preview `preview-output` read (the
// callback-bearing branch: it hands its nested opener to the PDF viewer), which opens the
// REAL PDF viewer (PDF 1, replacing the owner dialog); a companion link in PDF 1 opens a
// second REAL viewer (PDF 2, replacing PDF 1). After a forced GC a V8 heap snapshot is
// searched by OBJECT/PROPERTY-EDGE reachability: every live node carries its edges, so an
// object marked with a unique property name is retained iff some node has an edge of that
// name. A million-character payload is marked the same way through an object that owns it.
// NEGATIVE CONTROL: the probe first retains the owner dialog deliberately on globalThis and
// must report it retained; it then drops that reference and measures again.
import v8 from 'node:v8';import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
import {readFile} from 'node:fs/promises';
import {installDOM} from './evidence_reader_harness.mjs';
import {installPdfGlobals,loadRealPdf} from './real_pdf_environment.mjs';
import {templateWire as wire} from './document_template_fixture.mjs';
import {templateOutputURL} from '../../src/laplace/web/static_shared/document-template.mjs';
import {sharedInspector,resetSharedInspector} from '../../src/laplace/web/static_shared/workspace-inspector.mjs';
const shared=new URL('../../src/laplace/web/static_shared/',import.meta.url);
// the real artifact door, its relative imports resolved to files and its PDF import bound to the real viewer
const pdfModule=await loadRealPdf();globalThis.__pdfArtifactModule=null;
const artifactSource=(await readFile(new URL('writing-artifact.mjs',shared),'utf8'))
  .replace(/from (['"])\.\/([^'"]+)\1/g,(_m,_q,rel)=>'from '+JSON.stringify(new URL(rel,shared).href))
  .replaceAll("await import('/shared/writing-pdf.mjs')",'globalThis.__pdfModule');
globalThis.__pdfModule=pdfModule;
const artifactModule=await import('data:text/javascript;base64,'+Buffer.from(artifactSource).toString('base64'));
globalThis.__pdfArtifactModule=artifactModule;
const {openArtifact}=artifactModule;

const d=installDOM();resetSharedInspector();const inspector=sharedInspector();
const artifactPdf='/research/artifact?project=book&path=figures%2Fplot.pdf&scope=project';
const env=installPdfGlobals(d,{annotations:()=>[{rect:[10,20,110,35],unsafeUrl:artifactPdf}]});
const DIALOG_MARK='probe_dialog_'+Math.random().toString(36).slice(2),PAYLOAD_MARK='probe_payload_'+Math.random().toString(36).slice(2);
const built=wire.built,ref=built.reviewed.candidate_ref,proof=built.finished.preview_ref;
const previewURL=templateOutputURL(built.reviewed.preview_pdf_read,'book',ref,proof);
const request=async()=>{throw Error('neither the preview-output branch nor a PDF artifact performs an owner JSON read');};
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const refs={};   // weak only: the probe itself must not retain what it measures
// 1. the owner dialog (callback-bearing preview-output branch) → REAL PDF 1 replaces it, retaining the nested opener in its reopen args
async function stage1(){
  const owner=await openArtifact({ownerRead:{http:{method:'GET',url:previewURL}},label:'Exact template preview',request});
  owner[DIALOG_MARK]=true;owner.probePayload={[PAYLOAD_MARK]:'x'.repeat(1_000_000)};refs.owner=new WeakRef(owner);
  await tick();const pdf1=d.body.children.at(-1);refs.pdf1=new WeakRef(pdf1);
  return {ownerReplaced:owner.dataset?.inspectorReplaced==='true',current:inspector.current?.kind,trail:inspector.trail.map(e=>[e.kind,e.title,e.descriptor,e.retainsDialog])};
}
// 2. a PDF artifact link in PDF 1 → the retained nested opener → the artifact door's PDF shortcut → REAL PDF 2 replaces PDF 1
async function stage2(){
  const sheet=await env.renderLatest();sheet.querySelector('.wp-annotation-layer').children[0].click();
  for(let n=0;n<6;n++)await tick();
  const pdf2=d.body.children.at(-1);refs.pdf2=new WeakRef(pdf2);
  return {pdf1Replaced:refs.pdf1.deref()?.dataset?.inspectorReplaced==='true',pdf2IsNew:pdf2!==refs.pdf1.deref(),pdf2Current:inspector.current?.dialog===pdf2,trail:inspector.trail.map(e=>[e.kind,e.title,e.descriptor,e.retainsDialog])};
}
const afterPdf1=await stage1();const afterPdf2=await stage2();
const gc=async()=>{await new Promise(resolve=>setTimeout(resolve,0));for(let n=0;n<3;n++){globalThis.gc();await new Promise(resolve=>setTimeout(resolve,10));}};
function retained(){
  const file=path.join(os.tmpdir(),'laplace-inspector-retention-'+process.pid+'.heapsnapshot');v8.writeHeapSnapshot(file);
  const snap=JSON.parse(fs.readFileSync(file,'utf8'));fs.rmSync(file,{force:true});
  const nf=snap.snapshot.meta.node_fields,ef=snap.snapshot.meta.edge_fields,N=nf.length,E=ef.length,edgeTypes=snap.snapshot.meta.edge_types[0];
  const nodes=snap.nodes,edges=snap.edges,strings=snap.strings,count=nodes.length/N,edgeCountIndex=nf.indexOf('edge_count'),typeIndex=ef.indexOf('type'),nameIndex=ef.indexOf('name_or_index');
  let dialog=false,payload=false,edge=0;
  for(let i=0;i<count;i++){const n=nodes[i*N+edgeCountIndex];for(let j=0;j<n;j++,edge+=E){const type=edgeTypes[edges[edge+typeIndex]];if(type!=='property')continue;const name=strings[edges[edge+nameIndex]];if(name===DIALOG_MARK)dialog=true;else if(name===PAYLOAD_MARK)payload=true;}}
  return {dialogRetained:dialog,payloadRetained:payload};
}
// NEGATIVE CONTROL: retain the owner dialog deliberately; the probe must see it
(function keep(){globalThis.__probeKeep=refs.owner.deref();})();
await gc();const negativeControl=retained();
delete globalThis.__probeKeep;await gc();const released=retained();
console.log(JSON.stringify({afterPdf1,afterPdf2,negativeControl,released,pdf2Alive:refs.pdf2.deref()?.open===true,heapMB:Math.round(process.memoryUsage().heapUsed/1048576)}));
env.restore();d.restore();
