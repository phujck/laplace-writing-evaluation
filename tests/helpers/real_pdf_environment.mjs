// The REAL PDF viewer in node: loads writing-pdf.mjs with its relative imports resolved to
// files (so it shares the one workspace-inspector module instance with the other doors), a
// PDF-library double and the globals the viewer touches, on top of the evidence reader DOM
// (installDOM). Used by the template workflow test and the retention probe; the viewer's own
// unit tests keep their local double.
import {readFile} from 'node:fs/promises';
const shared=new URL('../../src/laplace/web/static_shared/',import.meta.url);

export async function loadRealPdf(){
  const source=(await readFile(new URL('writing-pdf.mjs',shared),'utf8'))
    .replace("from './writing-owner-read.mjs'",`from '${new URL('writing-owner-read.mjs',shared).href}'`)
    .replace("from './workspace-inspector.mjs'",`from '${new URL('workspace-inspector.mjs',shared).href}'`)
    .replace("await import('/shared/pdfjs/pdf.min.mjs')",'globalThis.__pdfTestLibrary')
    .replace("await import('/shared/writing-artifact.mjs')",'globalThis.__pdfArtifactModule');
  return import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
}

// Installs the viewer's globals over an installDOM() page and teaches its Node double the few
// members the viewer needs (controls created by innerHTML, after, geometry). Returns the
// observers list (IntersectionObserver doubles) so a test can declare a page visible, which
// renders it and fires onRendered exactly as the browser would.
export function installPdfGlobals(dom,{annotations=()=>[],companion=null,pages=2}={}){
  const original={};for(const key of ['window','location','devicePixelRatio','getComputedStyle','IntersectionObserver','fetch','__pdfTestLibrary'])original[key]=globalThis[key];
  const {Node}=dom;const observers=[];let destroyed=0;
  // the evidence Node has no listeners: chain close listeners (door + shared inspector) and ignore the rest
  const proto=Object.getPrototypeOf(dom.body),hadListener=Object.hasOwn(proto,'addEventListener'),priorAdd=proto.addEventListener,priorRemove=proto.removeEventListener;
  if(!hadListener){proto.addEventListener=function(name,fn){if(name!=='close')return;const prior=this.onclose;this.onclose=prior?(...args)=>{prior(...args);fn(...args);}:fn;};proto.removeEventListener=function(){};}
  const controls=['.wp-back','.wp-forward','h2','.wp-pages','.wp-status','.wp-download','.wp-tools','.wp-page','.wp-count','.wp-zoom','.wp-prev','.wp-next','.wp-minus','.wp-plus','.wp-fit','.wp-close','.wp-go'];
  const previousCreate=globalThis.document.createElement;
  const create=tag=>{const node=previousCreate(tag);node.style=Object.assign(node.style||{},{setProperty(key,value){node.style[key]=value;}});node.clientWidth=800;node.clientHeight=850;node.offsetHeight=100;node.getBoundingClientRect=()=>({top:100,bottom:900,height:800});node.getContext=()=>({});
    Object.defineProperty(node,'innerHTML',{set(_){for(const selector of controls){const child=create(selector==='h2'?'h2':selector==='.wp-page'?'input':selector==='.wp-download'?'a':'div');if(selector!=='h2')child.className=selector.slice(1);node.append(child);}}});
    node.after=other=>{node.parent?.append(other);};return node;};
  globalThis.document.createElement=create;
  const page={getViewport:({scale})=>({width:600*scale,height:800*scale,scale,rawDims:{pageWidth:600,pageHeight:800},convertToViewportPoint:(x,y)=>[x,y].map(value=>value*scale)}),render:()=>({promise:Promise.resolve(),cancel(){}}),getTextContent:async()=>({items:[{str:'Statement'}]}),getAnnotations:async()=>annotations()};
  globalThis.location={href:'http://127.0.0.1:8771/project?corpus=book',origin:'http://127.0.0.1:8771'};globalThis.window={addEventListener(){},removeEventListener(){}};globalThis.devicePixelRatio=1;globalThis.getComputedStyle=()=>({paddingTop:'0',paddingBottom:'0'});
  globalThis.IntersectionObserver=class{constructor(callback){this.callback=callback;observers.push(this);this.items=[];}observe(node){this.items.push(node);}disconnect(){}};
  globalThis.__pdfTestLibrary={GlobalWorkerOptions:{},getDocument:()=>({promise:Promise.resolve({numPages:pages,getPage:async()=>page,getMetadata:async()=>({info:{}})}),destroy:async()=>{destroyed++;}}),TextLayer:class{constructor({container,textContentSource}){this.container=container;this.text=textContentSource.items[0].str;}async render(){this.container.textContent=this.text;}cancel(){}}};
  if(companion)globalThis.fetch=async()=>({ok:true,json:async()=>companion});
  const tick=()=>new Promise(resolve=>setImmediate(resolve));
  // declare the newest viewer's first page visible: the real render path runs and onRendered fires
  const renderLatest=async()=>{const observer=observers.at(-1);const sheet=observer.items[0];observer.callback([{target:sheet,isIntersecting:true}]);await tick();await tick();await tick();return sheet;};
  return {observers,renderLatest,destroyed:()=>destroyed,restore(){globalThis.document.createElement=previousCreate;if(!hadListener){if(priorAdd)proto.addEventListener=priorAdd;else delete proto.addEventListener;if(priorRemove)proto.removeEventListener=priorRemove;else delete proto.removeEventListener;}for(const [key,value]of Object.entries(original)){if(value===undefined)delete globalThis[key];else globalThis[key]=value;}}};
}
