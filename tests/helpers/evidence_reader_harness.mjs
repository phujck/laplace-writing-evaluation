// Local DOM/transport double; production adapter and research-card logic run unchanged.
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const shared=new URL('../../src/laplace/web/static_shared/',import.meta.url);
export const sha=text=>createHash('sha256').update(text).digest('hex');
export class Node{
 constructor(tag){this.tag=tag;this.tagName=tag.toUpperCase();this.localName=tag;this.children=[];this.style={};this.dataset={};this.attrs={};this._text='';this.className='';this.value='';this.isConnected=true;
  this.classList={contains:v=>this.className.split(' ').includes(v),add:v=>this.className+=' '+v,remove:v=>this.className=this.className.split(' ').filter(x=>x!==v).join(' '),toggle:(v,on)=>on?this.classList.add(v):this.classList.remove(v)};}
 set textContent(v){this._text=String(v??'');this.children=[];}get textContent(){return this._text+this.children.map(n=>n.textContent||'').join('');}
 get parentElement(){return this.parent;}set parentElement(value){this.parent=value;}
 get childNodes(){return this.children;}get lastElementChild(){return this.children.at(-1)||null;}get firstElementChild(){return this.children[0]||null;}
 append(...nodes){for(let n of nodes){if(typeof n==='string'){const t=new Node('#text');t.textContent=n;n=t;}n.parent=this;n.isConnected=true;this.children.push(n);}}
 appendChild(n){this.append(n);return n;}prepend(...nodes){for(const n of nodes)n.parent=this;this.children.unshift(...nodes);}
 replaceChildren(...nodes){this.children=[];this._text='';this.append(...nodes);}
 setAttribute(k,v){this.attrs[k]=String(v);if(k==='id')this.id=String(v);}getAttribute(k){return this.attrs[k]??null;}
 showModal(){this.open=true;}close(){this.open=false;this.onclose?.();}
 remove(){if(this.parent)this.parent.children=this.parent.children.filter(n=>n!==this);this.isConnected=false;}
 insertBefore(node,ref){const at=ref?this.children.indexOf(ref):-1;node.parent=this;node.isConnected=true;if(at<0)this.children.push(node);else this.children.splice(at,0,node);return node;}
 contains(node){for(let at=node;at;at=at.parent)if(at===this)return true;return false;}
 closest(selector){for(let n=this;n;n=n.parent)if(n.matches?.(selector))return n;return null;}
 replaceWith(node){if(!this.parent)return;const at=this.parent.children.indexOf(this);node.parent=this.parent;node.isConnected=true;this.parent.children.splice(at,1,node);this.isConnected=false;}
 focus(options){this.focusOptions=options;globalThis.document.activeElement=this;}scrollIntoView(options){this.revealed=(this.revealed||0)+1;this.revealOptions=options;}
 all(){return [this,...this.children.flatMap(n=>n.all?.()||[])];}
 matches(selector){if(selector.startsWith('.'))return this.classList.contains(selector.slice(1));
  const match=/^([\w-]+)?\[([^\]=]+)(?:="([^"]*)")?\]$/.exec(selector);
  if(match){if(match[1]&&this.tag!==match[1])return false;const key=match[2];const value=key.startsWith('data-')?this.dataset[key.slice(5).replace(/-([a-z])/g,(_,x)=>x.toUpperCase())]:this.attrs[key];return match[3]===undefined?value!==undefined:value===match[3];}
  return this.tag===selector;}
 querySelectorAll(selector){return this.all().slice(1).filter(n=>n.matches(selector));}
 querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
 async click(){this.focus();return this.onclick?.({preventDefault(){},stopPropagation(){}});}
}
export function installDOM(){
 const old=globalThis.document,body=new Node('body'),head=new Node('head'),editor=new Node('textarea'),iframe=new Node('iframe');
 editor.value='UNSAVED manuscript';body.append(editor,iframe);
 globalThis.document={body,head,activeElement:editor,createElement:t=>new Node(t),createTextNode:text=>{const n=new Node('#text');n.textContent=text;return n;},
 querySelector:s=>head.querySelector(s)||body.querySelector(s)};
 return {body,head,editor,iframe,dialogs:()=>body.children.filter(n=>n.tag==='dialog'),restore:()=>globalThis.document=old};
}
export function transport(text,{extra=null}={}){
 const chars=Array.from(text),hash=sha(text),calls=[];
 return {calls,request:async url=>{
  calls.push(url);const q=new URL(url,'http://local').searchParams;
  if(extra){const value=await extra(url,q);if(value!==undefined)return value;}
  const offset=Number(q.get('offset')||0),limit=Number(q.get('limit')||32768),content=chars.slice(offset,offset+limit).join(''),end=offset+Array.from(content).length;
  return {path:q.get('path'),scope:q.get('scope'),content,offset,total_chars:chars.length,bytes:Buffer.byteLength(text),sha256:hash,next_offset:end<chars.length?end:null};
 }};
}
export const bodyOf=dialog=>dialog.querySelector('.artifact-body');
export const statusOf=dialog=>dialog.children.find(n=>n.attrs.role==='status'||n.attrs.role==='alert');
export const findButton=(host,label)=>host.all().find(n=>n.tag==='button'&&(typeof label==='string'?n.textContent===label:label.test(n.textContent)));
export async function loadReader(){
 const cardsSource=(await readFile(new URL('research-card.mjs',shared),'utf8'))
  .replace("from '/shared/writing-pdf.mjs'","from '"+new URL('writing-pdf.mjs',shared).href+"'")
  .replace("from '/shared/concept-reader.mjs'","from '"+new URL('concept-reader.mjs',shared).href+"'");
 const cards=await import('data:text/javascript;base64,'+Buffer.from(cardsSource).toString('base64'));
 const snapshots=[],pdfCalls=[];const key='__evidenceReviewHarness'+Date.now()+Math.random().toString().slice(2);
 globalThis[key]={cards,graph:{mountArgumentOverview:async(_host,options)=>{snapshots.push(options.snapshot);return {destroy(){}};}},
  pdf:{openPdf:async(...args)=>{pdfCalls.push(args);}}};
 const code=(await readFile(new URL('writing-artifact.mjs',shared),'utf8'))
  .replace(/from (['"])\.\/([^'"]+)\1/g,(_match,_quote,path)=>'from '+JSON.stringify(new URL(path,shared).href))
  .replaceAll("await import('/shared/research-card.mjs')","globalThis['"+key+"'].cards")
  .replaceAll("await import('/shared/concept-explorer.mjs')","globalThis['"+key+"'].graph")
  .replaceAll("await import('/shared/writing-pdf.mjs')","globalThis['"+key+"'].pdf");
 const reader=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
 return {...reader,cards,snapshots,pdfCalls,destroy:()=>delete globalThis[key]};
}
