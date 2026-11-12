import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {pdfAnnotationRect,pdfAnnotationAction,pdfDestination,appendPdfAnnotations} from '../src/laplace/web/static_shared/writing-pdf.mjs';
const require=createRequire(import.meta.url);let canvasAvailable=true;try{require.resolve('@napi-rs/canvas');}catch{canvasAvailable=false;}
// A complete two-page PDF with real URI/internal annotations; no renderer/viewport mock.
function fixturePdf(){
 const artifact='/research/artifact?project=book&path=development/proof.json&scope=project&owner=writing-artifact&artifact_id=ART-proof&expected_sha256='+'a'.repeat(64),material='/projects/material-references?project=book&view=source&id=edition-map';
 const objects=[
  '<< /Type /Catalog /Pages 2 0 R >>',
  '<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>',
  '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 300] /Resources << >> /Annots [5 0 R 7 0 R 8 0 R] >>',
  '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 300] /Rotate 90 /Resources << >> /Annots [6 0 R] >>',
  '<< /Type /Annot /Subtype /Link /Rect [10 20 60 40] /A << /S /URI /URI (notes.md) >> >>',
  '<< /Type /Annot /Subtype /Link /Rect [10 20 60 40] /Dest [3 0 R /XYZ 0 250 null] >>',
  '<< /Type /Annot /Subtype /Link /Rect [10 60 60 80] /A << /S /URI /URI ('+artifact+') >> >>',
  '<< /Type /Annot /Subtype /Link /Rect [10 100 60 120] /A << /S /URI /URI ('+material+') >> >>'
 ];let text='%PDF-1.7\n',offsets=[0];for(const [i,object]of objects.entries()){offsets.push(text.length);text+=(i+1)+' 0 obj\n'+object+'\nendobj\n';}const xref=text.length;text+='xref\n0 '+offsets.length+'\n0000000000 65535 f \n'+offsets.slice(1).map(offset=>String(offset).padStart(10,'0')+' 00000 n \n').join('')+'trailer\n<< /Root 1 0 R /Size '+offsets.length+' >>\nstartxref\n'+xref+'\n%%EOF\n';return new TextEncoder().encode(text);
}
test('actual vendored PDF.js viewport supports URI and internal annotation bounds at scale and rotation',{skip:!canvasAvailable&&'Node PDF.js runtime needs @napi-rs/canvas; use the configured workspace NODE_PATH'},async()=>{
 const lib=await import('../src/laplace/web/static_shared/pdfjs/pdf.min.mjs');lib.GlobalWorkerOptions.workerSrc=new URL('../src/laplace/web/static_shared/pdfjs/pdf.worker.min.mjs',import.meta.url).href;
 const task=lib.getDocument({data:fixturePdf(),isEvalSupported:false});try{const pdf=await task.promise;assert.equal(pdf.numPages,2);const first=await pdf.getPage(1),second=await pdf.getPage(2),a=(await first.getAnnotations({intent:'display'}))[0],b=(await second.getAnnotations({intent:'display'}))[0];
 assert.equal(typeof first.getViewport({scale:1}).convertToViewportPoint,'function');
 assert.deepEqual(pdfAnnotationRect(a.rect,first.getViewport({scale:2})),{left:20,top:520,width:100,height:40});
 assert.deepEqual(pdfAnnotationRect(b.rect,second.getViewport({scale:2})),{left:40,top:20,width:40,height:100});
 assert.equal(pdfAnnotationAction(a,'/research/artifact?project=book&path=main.pdf&scope=project','http://localhost/project').kind,'companion');
 const oldDocument=globalThis.document,host={children:[],append(node){this.children.push(node);}},activated=[];
 globalThis.document={createElement:()=>({style:{},setAttribute(){}})};
 try{appendPdfAnnotations(host,await first.getAnnotations({intent:'display'}),first.getViewport({scale:2}),{url:'/research/artifact?project=book&path=main.pdf&scope=project',base:'http://localhost/project',onAction:action=>activated.push(action)});
 assert.equal(host.children.length,3);host.children[1].onclick({preventDefault(){}});host.children[2].onclick({preventDefault(){}});
 assert.equal(activated[0].kind,'artifact');assert.equal(activated[0].artifactId,'ART-proof');assert.equal(activated[0].expectedSha256,'a'.repeat(64));assert.equal(activated[0].artifactOwner,'writing-artifact');assert.equal(activated[1].ownerRead.id,'edition-map');
 }finally{globalThis.document=oldDocument;}
 const destination=await pdfDestination(pdf,b.dest);assert.equal(destination.page,1);assert.equal(destination.destination[1].name,'XYZ');
 }finally{await task.destroy();}
});
